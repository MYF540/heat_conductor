"""Coordinator: reads Home Assistant states, runs the engine, applies decisions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ALL_DEFAULTS,
    CHANGELOG_MAX_ENTRIES,
    COMMAND_RETRY_INTERVAL,
    DOMAIN,
    FORECAST_INTERVAL,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
    WATCHDOG_INTERVAL,
)
from .core.energy import EnergyParams
from .core.engine import EngineResult, HeatingEngine
from .core.models import ControlParams, OperatingMode
from .core.setpoint import SetpointParams, TrvCommand
from .helpers import IssueTracker, async_fetch_forecast, async_send_heartbeat
from .inputs import ControlState, EntityConfig, InputReader, RoomConfig, build_snapshot
from .params import control_params, energy_params, setpoint_params, solar_reference

_LOGGER = logging.getLogger(__name__)

type HeatConductorConfigEntry = ConfigEntry[HeatConductorCoordinator]

__all__ = ["HeatConductorConfigEntry", "HeatConductorCoordinator", "RoomConfig", "Settings"]


@dataclass(slots=True)
class Settings:
    """User-controlled switches, persisted in storage."""

    mode: OperatingMode = OperatingMode.AUTO
    automation_enabled: bool = True
    observation_mode: bool = True
    room_control_enabled: bool = False
    learned_schedule_enabled: bool = False
    vacation_start: datetime | None = None
    vacation_end: datetime | None = None
    vacation_temp: float | None = None

    def vacation_active(self, now: datetime) -> bool:
        """Whether a scheduled vacation is running."""
        if self.vacation_end is None or now >= self.vacation_end:
            return False
        return self.vacation_start is None or now >= self.vacation_start

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "mode": self.mode.value,
            "automation_enabled": self.automation_enabled,
            "observation_mode": self.observation_mode,
            "room_control_enabled": self.room_control_enabled,
            "learned_schedule_enabled": self.learned_schedule_enabled,
            "vacation_start": _iso(self.vacation_start),
            "vacation_end": _iso(self.vacation_end),
            "vacation_temp": self.vacation_temp,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore."""
        try:
            self.mode = OperatingMode(data.get("mode", OperatingMode.AUTO))
        except ValueError:
            self.mode = OperatingMode.AUTO
        self.automation_enabled = bool(data.get("automation_enabled", True))
        self.observation_mode = bool(data.get("observation_mode", True))
        self.room_control_enabled = bool(data.get("room_control_enabled", False))
        self.learned_schedule_enabled = bool(data.get("learned_schedule_enabled", False))
        self.vacation_start = _parse(data.get("vacation_start"))
        self.vacation_end = _parse(data.get("vacation_end"))
        temp = data.get("vacation_temp")
        self.vacation_temp = float(temp) if isinstance(temp, (int, float)) else None


class HeatConductorCoordinator(DataUpdateCoordinator[EngineResult]):
    """Runs an evaluation every 30 s and on every relevant state change."""

    config_entry: HeatConductorConfigEntry

    def __init__(self, hass: HomeAssistant, entry: HeatConductorConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._options: dict[str, Any] = dict(entry.options)
        self.entities = EntityConfig.from_entry(entry)
        self.params: ControlParams = control_params(self._options)
        self.energy_params: EnergyParams = energy_params(self._options)
        self.setpoint_params: SetpointParams = setpoint_params(self._options)
        self.engine = HeatingEngine(
            self.params, self.energy_params, self.setpoint_params, solar_reference(self._options)
        )
        self.settings = Settings()
        self.changelog: list[dict[str, Any]] = []
        self.watchdog_ok_at: datetime | None = None
        self.forecast_6h: float | None = None
        self.forecast_12h: float | None = None

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._issues = IssueTracker(hass)
        self._started_at = dt_util.now()
        self._last_command: bool | None = None
        self._last_command_at: datetime | None = None
        self._last_heartbeat: datetime | None = None
        self._last_forecast: datetime | None = None
        self._trv_lock = asyncio.Lock()

    # -- configuration shortcuts ---------------------------------------------

    @property
    def rooms(self) -> tuple[RoomConfig, ...]:
        """Configured rooms."""
        return self.entities.rooms

    @property
    def boiler_switch(self) -> str | None:
        """Relay entity."""
        return self.entities.boiler_switch

    @property
    def flow_temperature(self) -> str | None:
        """Flow temperature entity."""
        return self.entities.flow_temperature

    @property
    def return_temperature(self) -> str | None:
        """Return temperature entity."""
        return self.entities.return_temperature

    @property
    def gas_flow(self) -> str | None:
        """Gas flow entity."""
        return self.entities.gas_flow

    @property
    def burner_sensor(self) -> str | None:
        """Burner sensor entity."""
        return self.entities.burner_sensor

    @property
    def has_gas_source(self) -> bool:
        """Whether gas consumption can be measured."""
        return self.entities.has_gas_source

    @property
    def tracked_entities(self) -> set[str]:
        """All input entities."""
        return self.entities.tracked_entities

    @property
    def options(self) -> dict[str, Any]:
        """Current options."""
        return self._options

    @property
    def actuator_active(self) -> bool:
        """Whether HeatConductor may switch the boiler relay."""
        return (
            self.entities.boiler_switch is not None
            and self.settings.automation_enabled
            and not self.settings.observation_mode
        )

    def watchdog_connected(self, now: datetime | None = None) -> bool | None:
        """Heartbeat accepted recently (None without watchdog)."""
        if self.entities.watchdog_url is None:
            return None
        now = now or dt_util.now()
        return (
            self.watchdog_ok_at is not None and now - self.watchdog_ok_at <= WATCHDOG_INTERVAL * 3
        )

    # -- lifecycle ---------------------------------------------------------

    async def _async_setup(self) -> None:
        """Load persisted state before the first refresh."""
        stored = await self._store.async_load() or {}
        self.settings.restore(stored.get("settings", {}))
        self.engine.restore(stored.get("engine", {}))
        self.changelog = list(stored.get("changelog", []))[-CHANGELOG_MAX_ENTRIES:]

    @callback
    def async_start_tracking(self) -> CALLBACK_TYPE:
        """Re-evaluate whenever an input entity changes."""

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        return async_track_state_change_event(self.hass, sorted(self.tracked_entities), _changed)

    async def async_persist_now(self) -> None:
        """Write state to storage immediately and clear repair issues."""
        await self._store.async_save(self._data_to_store())
        self._issues.clear()

    @callback
    def async_apply_options(self, entry: ConfigEntry) -> bool:
        """Apply changed parameters live. Returns False if a reload is needed."""
        new = dict(entry.options)
        changed = {k for k in set(self._options) | set(new) if self._options.get(k) != new.get(k)}
        if not changed or not changed <= set(ALL_DEFAULTS):
            return False
        self._options = new
        self.params = control_params(new)
        self.energy_params = energy_params(new)
        self.setpoint_params = setpoint_params(new)
        self.engine.update_params(
            self.params, self.energy_params, self.setpoint_params, solar_reference(new)
        )
        self.hass.async_create_task(self.async_request_refresh())
        return True

    # -- user settings -----------------------------------------------------

    async def async_set_mode(self, mode: OperatingMode) -> None:
        """Change the operating mode."""
        self.settings.mode = mode
        await self._settings_changed()

    async def async_set_automation(self, enabled: bool) -> None:
        """Enable or disable automatic control."""
        self.settings.automation_enabled = enabled
        await self._settings_changed(heartbeat=True)

    async def async_set_observation(self, enabled: bool) -> None:
        """Enable or disable observation mode."""
        self.settings.observation_mode = enabled
        await self._settings_changed(heartbeat=True)

    async def async_set_room_control(self, enabled: bool) -> None:
        """Enable or disable writing setpoints to thermostats."""
        self.settings.room_control_enabled = enabled
        await self._settings_changed()

    async def async_set_learned_schedule(self, enabled: bool) -> None:
        """Let rooms without a schedule helper follow the learned presence schedule."""
        self.settings.learned_schedule_enabled = enabled
        await self._settings_changed()

    async def async_set_room_usage(self, room_id: str, enabled: bool) -> None:
        """Enable or disable usage detection for one room."""
        self.engine.runtime(room_id).usage_enabled = enabled
        await self._settings_changed()

    async def async_set_room_value(self, room_id: str, key: str, value: float) -> None:
        """Set comfort or eco temperature of a room."""
        if key not in ("comfort", "eco"):
            raise ValueError(key)
        setattr(self.engine.runtime(room_id), key, float(value))
        await self._settings_changed()

    async def async_set_room_enabled(self, room_id: str, enabled: bool) -> None:
        """Switch a room on (automatic) or off (frost protection)."""
        self.engine.runtime(room_id).enabled = enabled
        await self._settings_changed()

    async def async_set_room_target(self, room_id: str, temperature: float) -> None:
        """Temporary manual target for a room."""
        self.engine.set_override(room_id, dt_util.now(), temperature)
        await self._settings_changed()

    async def async_boost(
        self, room_id: str, duration: timedelta | None = None, temperature: float | None = None
    ) -> None:
        """Boost a room."""
        self.engine.set_boost(room_id, dt_util.now(), duration, temperature)
        await self._settings_changed()

    async def async_clear_override(self, room_id: str) -> None:
        """Return a room to automatic operation."""
        self.engine.clear_override(room_id)
        await self._settings_changed()

    async def async_set_vacation(
        self, start: datetime | None, end: datetime, temperature: float | None
    ) -> None:
        """Schedule a vacation."""
        self.settings.vacation_start = start
        self.settings.vacation_end = end
        self.settings.vacation_temp = temperature
        await self._settings_changed()

    async def async_clear_vacation(self) -> None:
        """End a vacation."""
        self.settings.vacation_start = None
        self.settings.vacation_end = None
        self.settings.vacation_temp = None
        await self._settings_changed()

    async def async_reset_learning(self, room_id: str | None = None) -> None:
        """Forget learned values."""
        self.engine.learner.reset(room_id)
        await self._settings_changed()

    async def async_set_params(self, values: dict[str, float | bool], user: str | None) -> None:
        """Change parameters (validated by the caller) and log the change."""
        now = dt_util.now()
        new_options = dict(self._options)
        for key, value in values.items():
            old = self._options.get(key, ALL_DEFAULTS[key])
            if old == value:
                continue
            new_options[key] = value
            self.changelog.append(
                {"time": now.isoformat(), "user": user, "key": key, "old": old, "new": value}
            )
        self.changelog = self.changelog[-CHANGELOG_MAX_ENTRIES:]
        self._store.async_delay_save(self._data_to_store, STORAGE_SAVE_DELAY)
        if new_options != self._options:
            self.hass.config_entries.async_update_entry(self.config_entry, options=new_options)

    async def _settings_changed(self, *, heartbeat: bool = False) -> None:
        if heartbeat:
            self._last_heartbeat = None
        self._store.async_delay_save(self._data_to_store, STORAGE_SAVE_DELAY)
        await self.async_refresh()

    # -- evaluation --------------------------------------------------------

    async def _async_update_data(self) -> EngineResult:
        now = dt_util.now()
        self._schedule_forecast(now)
        base_setpoint = self.setpoint_params
        if self.settings.vacation_temp is not None:
            self.engine.setpoint_params = replace(
                base_setpoint, vacation_temp=self.settings.vacation_temp
            )
        try:
            control = ControlState(
                mode=self.settings.mode,
                automation_enabled=self.settings.automation_enabled,
                actuator_active=self.actuator_active,
                room_control_enabled=self.settings.room_control_enabled,
                learned_schedule_enabled=self.settings.learned_schedule_enabled,
                vacation_active=self.settings.vacation_active(now),
                forecast_6h=self.forecast_6h,
                forecast_12h=self.forecast_12h,
            )
            snapshot = build_snapshot(
                self.entities, InputReader(self.hass.states.get), now, control
            )
            result = self.engine.evaluate(snapshot)
        except Exception as err:
            _LOGGER.exception("Evaluation failed, switching boiler off as a precaution")
            await self._command(False, now, force=True)
            raise UpdateFailed(f"Evaluation failed: {err}") from err
        finally:
            self.engine.setpoint_params = base_setpoint

        await self._apply_relay(result, snapshot.relay_on, now)
        if result.trv_commands:
            self.config_entry.async_create_background_task(
                self.hass, self._async_write_trvs(result.trv_commands), f"{DOMAIN}_trv_writes"
            )
        self._schedule_heartbeat(now)
        watchdog_problem = bool(
            self.entities.watchdog_url is not None
            and self.actuator_active
            and now - self._started_at > WATCHDOG_INTERVAL * 3
            and not self.watchdog_connected(now)
        )
        self._issues.update(result, now, watchdog_problem)
        self._store.async_delay_save(self._data_to_store, STORAGE_SAVE_DELAY)
        return result

    async def _apply_relay(
        self, result: EngineResult, relay_on: bool | None, now: datetime
    ) -> None:
        decision = result.decision
        if not self.actuator_active or not decision.command_allowed:
            return
        if relay_on is None or relay_on == decision.request_heat:
            return
        await self._command(decision.request_heat, now)

    async def _command(self, on: bool, now: datetime, *, force: bool = False) -> None:
        """Switch the relay. Never touches it in observation mode or when disabled."""
        if self.entities.boiler_switch is None or not self.actuator_active:
            return
        if (
            not force
            and self._last_command == on
            and self._last_command_at is not None
            and now - self._last_command_at < COMMAND_RETRY_INTERVAL
        ):
            return
        self._last_command = on
        self._last_command_at = now
        self.engine.boiler.note_command(on)
        _LOGGER.info("Switching boiler %s", "on" if on else "off")
        try:
            await self.hass.services.async_call(
                "homeassistant",
                SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: self.entities.boiler_switch},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not switch boiler relay %s: %s", self.entities.boiler_switch, err
            )

    async def _async_write_trvs(self, commands: tuple[TrvCommand, ...]) -> None:
        async with self._trv_lock:
            for command in commands:
                try:
                    if command.set_heat_mode:
                        await self.hass.services.async_call(
                            "climate",
                            "set_hvac_mode",
                            {ATTR_ENTITY_ID: command.entity_id, "hvac_mode": HVACMode.HEAT},
                            blocking=True,
                        )
                    await self.hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {ATTR_ENTITY_ID: command.entity_id, ATTR_TEMPERATURE: command.temperature},
                        blocking=True,
                    )
                    _LOGGER.debug("Set %s to %.1f °C", command.entity_id, command.temperature)
                except HomeAssistantError as err:
                    _LOGGER.warning("Could not set %s: %s", command.entity_id, err)
                    for runtime in self.engine.room_runtime.values():
                        if (state := runtime.trvs.get(command.entity_id)) is not None:
                            state.last_written = None
                            state.last_write_at = None

    def _schedule_heartbeat(self, now: datetime) -> None:
        url = self.entities.watchdog_url
        if url is None:
            return
        if self._last_heartbeat is not None and now - self._last_heartbeat < WATCHDOG_INTERVAL:
            return
        self._last_heartbeat = now
        armed = self.actuator_active

        async def _beat() -> None:
            if await async_send_heartbeat(self.hass, url, armed):
                self.watchdog_ok_at = dt_util.now()

        self.config_entry.async_create_background_task(self.hass, _beat(), f"{DOMAIN}_heartbeat")

    def _schedule_forecast(self, now: datetime) -> None:
        weather = self.entities.weather
        if weather is None or not self.params.use_forecast:
            return
        if self._last_forecast is not None and now - self._last_forecast < FORECAST_INTERVAL:
            return
        self._last_forecast = now

        async def _fetch() -> None:
            self.forecast_6h, self.forecast_12h = await async_fetch_forecast(
                self.hass, weather, dt_util.now()
            )

        self.config_entry.async_create_background_task(self.hass, _fetch(), f"{DOMAIN}_forecast")

    def _data_to_store(self) -> dict[str, Any]:
        return {
            "settings": self.settings.to_dict(),
            "engine": self.engine.to_dict(),
            "changelog": self.changelog,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)
