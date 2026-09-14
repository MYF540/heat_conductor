"""Coordinator: reads Home Assistant states, runs the engine, applies decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE, HVACMode
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    COMMAND_RETRY_INTERVAL,
    CONF_BOILER_SWITCH,
    CONF_BURNER_FLOW_THRESHOLD,
    CONF_BURNER_SENSOR,
    CONF_CLIMATES,
    CONF_DEFICIT_FULL_SCALE,
    CONF_FLOW_TEMPERATURE,
    CONF_FROST_LIMIT,
    CONF_GAS_FLOW,
    CONF_HEATING_LIMIT,
    CONF_IMMEDIATE_DEFICIT,
    CONF_MANUAL_OVERRIDE,
    CONF_MAX_FLOW_TEMPERATURE,
    CONF_MAX_STARTS,
    CONF_MIN_PAUSE,
    CONF_MIN_RUN,
    CONF_OUTDOOR_SENSORS,
    CONF_OUTDOOR_SMOOTHING,
    CONF_RETURN_TEMPERATURE,
    CONF_ROOM_KIND,
    CONF_ROOM_TEMPERATURE,
    CONF_STALE_AFTER,
    CONF_START_CONFIRM,
    CONF_START_THRESHOLD,
    CONF_STOP_THRESHOLD,
    CONF_VALVES,
    CONF_WEATHER,
    CONF_WEIGHT,
    CONF_WINDOWS,
    DOMAIN,
    PARAMETER_DEFAULTS,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
    SUBENTRY_ROOM,
    UPDATE_INTERVAL,
)
from .core.demand import RoomInput
from .core.engine import EngineResult, EngineSnapshot, HeatingEngine
from .core.models import MISSING, ControlParams, OperatingMode, Reading, RoomKind

_LOGGER = logging.getLogger(__name__)

type HeatConductorConfigEntry = ConfigEntry[HeatConductorCoordinator]


@dataclass(slots=True)
class Settings:
    """User-controlled switches, persisted in storage."""

    mode: OperatingMode = OperatingMode.AUTO
    automation_enabled: bool = True
    observation_mode: bool = True


@dataclass(frozen=True, slots=True)
class RoomConfig:
    """Entity configuration of one room (from a config subentry)."""

    room_id: str
    name: str
    kind: RoomKind
    weight: float
    climates: tuple[str, ...]
    valves: tuple[str, ...]
    room_temperature: str | None
    windows: tuple[str, ...] = field(default=())

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> RoomConfig:
        """Build from a room subentry."""
        data = subentry.data
        return cls(
            room_id=subentry.subentry_id,
            name=subentry.title,
            kind=RoomKind(data.get(CONF_ROOM_KIND, RoomKind.REGULATED)),
            weight=float(data.get(CONF_WEIGHT, 1.0)),
            climates=tuple(data.get(CONF_CLIMATES, [])),
            valves=tuple(data.get(CONF_VALVES, [])),
            room_temperature=data.get(CONF_ROOM_TEMPERATURE) or None,
            windows=tuple(data.get(CONF_WINDOWS, [])),
        )

    @property
    def entity_ids(self) -> set[str]:
        """All entities this room depends on."""
        ids = {*self.climates, *self.valves, *self.windows}
        if self.room_temperature:
            ids.add(self.room_temperature)
        return ids


def params_from_options(options: dict[str, Any]) -> ControlParams:
    """Translate user-facing option values into control parameters."""

    def opt(key: str) -> float:
        return float(options.get(key, PARAMETER_DEFAULTS[key]))

    return ControlParams(
        start_threshold=opt(CONF_START_THRESHOLD) / 100,
        start_confirm=timedelta(minutes=opt(CONF_START_CONFIRM)),
        stop_threshold=opt(CONF_STOP_THRESHOLD) / 100,
        immediate_start_deficit=opt(CONF_IMMEDIATE_DEFICIT),
        deficit_full_scale=opt(CONF_DEFICIT_FULL_SCALE),
        min_run=timedelta(minutes=opt(CONF_MIN_RUN)),
        min_pause=timedelta(minutes=opt(CONF_MIN_PAUSE)),
        max_starts_per_hour=int(opt(CONF_MAX_STARTS)),
        heating_limit=opt(CONF_HEATING_LIMIT),
        frost_limit=opt(CONF_FROST_LIMIT),
        max_flow_temperature=opt(CONF_MAX_FLOW_TEMPERATURE),
        stale_after=timedelta(minutes=opt(CONF_STALE_AFTER)),
        manual_override=timedelta(minutes=opt(CONF_MANUAL_OVERRIDE)),
        outdoor_smoothing=timedelta(hours=opt(CONF_OUTDOOR_SMOOTHING)),
        burner_flow_threshold=opt(CONF_BURNER_FLOW_THRESHOLD),
    )


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
        options = entry.options
        self.params = params_from_options(dict(options))
        self.engine = HeatingEngine(self.params)
        self.settings = Settings()
        self.rooms = tuple(
            RoomConfig.from_subentry(s)
            for s in entry.subentries.values()
            if s.subentry_type == SUBENTRY_ROOM
        )
        self.boiler_switch: str | None = options.get(CONF_BOILER_SWITCH) or None
        self.flow_temperature: str | None = options.get(CONF_FLOW_TEMPERATURE) or None
        self.return_temperature: str | None = options.get(CONF_RETURN_TEMPERATURE) or None
        self.gas_flow: str | None = options.get(CONF_GAS_FLOW) or None
        self.burner_sensor: str | None = options.get(CONF_BURNER_SENSOR) or None
        self.outdoor_sensors: tuple[str, ...] = tuple(options.get(CONF_OUTDOOR_SENSORS, []))
        self.weather: str | None = options.get(CONF_WEATHER) or None

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._last_command: bool | None = None
        self._last_command_at: datetime | None = None

    # -- lifecycle ---------------------------------------------------------

    async def _async_setup(self) -> None:
        """Load persisted state before the first refresh."""
        stored = await self._store.async_load() or {}
        settings = stored.get("settings", {})
        try:
            self.settings.mode = OperatingMode(settings.get("mode", OperatingMode.AUTO))
        except ValueError:
            self.settings.mode = OperatingMode.AUTO
        self.settings.automation_enabled = bool(settings.get("automation_enabled", True))
        self.settings.observation_mode = bool(settings.get("observation_mode", True))
        self.engine.restore(stored.get("engine", {}))

    @callback
    def async_start_tracking(self) -> CALLBACK_TYPE:
        """Re-evaluate whenever an input entity changes."""

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        return async_track_state_change_event(self.hass, sorted(self.tracked_entities), _changed)

    async def async_persist_now(self) -> None:
        """Write state to storage immediately (on unload)."""
        await self._store.async_save(self._data_to_store())

    @property
    def tracked_entities(self) -> set[str]:
        """All input entities."""
        ids: set[str] = {*self.outdoor_sensors}
        for entity_id in (
            self.boiler_switch,
            self.flow_temperature,
            self.return_temperature,
            self.gas_flow,
            self.burner_sensor,
            self.weather,
        ):
            if entity_id:
                ids.add(entity_id)
        for room in self.rooms:
            ids |= room.entity_ids
        return ids

    @property
    def actuator_active(self) -> bool:
        """Whether HeatConductor may switch the boiler relay."""
        return (
            self.boiler_switch is not None
            and self.settings.automation_enabled
            and not self.settings.observation_mode
        )

    # -- user settings -----------------------------------------------------

    async def async_set_mode(self, mode: OperatingMode) -> None:
        """Change the operating mode."""
        self.settings.mode = mode
        await self._settings_changed()

    async def async_set_automation(self, enabled: bool) -> None:
        """Enable or disable automatic control."""
        self.settings.automation_enabled = enabled
        await self._settings_changed()

    async def async_set_observation(self, enabled: bool) -> None:
        """Enable or disable observation mode."""
        self.settings.observation_mode = enabled
        await self._settings_changed()

    async def _settings_changed(self) -> None:
        self._store.async_delay_save(self._data_to_store, STORAGE_SAVE_DELAY)
        await self.async_refresh()

    # -- evaluation --------------------------------------------------------

    async def _async_update_data(self) -> EngineResult:
        now = dt_util.now()
        try:
            snapshot = self._build_snapshot(now)
            result = self.engine.evaluate(snapshot)
        except Exception as err:
            _LOGGER.exception("Evaluation failed, switching boiler off as a precaution")
            await self._command(False, now, force=True)
            raise UpdateFailed(f"Evaluation failed: {err}") from err

        await self._apply(result, snapshot, now)
        self._store.async_delay_save(self._data_to_store, STORAGE_SAVE_DELAY)
        return result

    async def _apply(self, result: EngineResult, snapshot: EngineSnapshot, now: datetime) -> None:
        decision = result.decision
        if not snapshot.actuator_active or not decision.command_allowed:
            return
        if snapshot.relay_on is None or snapshot.relay_on == decision.request_heat:
            return
        await self._command(decision.request_heat, now)

    async def _command(self, on: bool, now: datetime, *, force: bool = False) -> None:
        """Switch the relay. Never touches it in observation mode or when disabled."""
        if self.boiler_switch is None or not self.actuator_active:
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
                {ATTR_ENTITY_ID: self.boiler_switch},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not switch boiler relay %s: %s", self.boiler_switch, err)

    def _data_to_store(self) -> dict[str, Any]:
        return {
            "settings": {
                "mode": self.settings.mode.value,
                "automation_enabled": self.settings.automation_enabled,
                "observation_mode": self.settings.observation_mode,
            },
            "engine": self.engine.to_dict(),
        }

    # -- reading states ----------------------------------------------------

    def _build_snapshot(self, now: datetime) -> EngineSnapshot:
        return EngineSnapshot(
            now=now,
            rooms=tuple(self._room_input(room) for room in self.rooms),
            outdoor_sensors=tuple(self._temperature(e) for e in self.outdoor_sensors),
            weather_temperature=self._weather_temperature() if self.weather else None,
            flow_temperature=self._temperature(self.flow_temperature)
            if self.flow_temperature
            else None,
            return_temperature=(
                self._temperature(self.return_temperature) if self.return_temperature else None
            ),
            gas_flow=self._number(self.gas_flow) if self.gas_flow else None,
            burner_on=self._binary(self.burner_sensor) if self.burner_sensor else None,
            relay_on=self._binary(self.boiler_switch) if self.boiler_switch else None,
            mode=self.settings.mode,
            automation_enabled=self.settings.automation_enabled,
            actuator_active=self.actuator_active,
        )

    def _room_input(self, room: RoomConfig) -> RoomInput:
        climate_states = [self._state(e) for e in room.climates]
        return RoomInput(
            room_id=room.room_id,
            name=room.name,
            kind=room.kind,
            weight=room.weight,
            room_temperature=self._temperature(room.room_temperature)
            if room.room_temperature
            else None,
            thermostat_temperatures=tuple(
                _attribute_reading(s, ATTR_CURRENT_TEMPERATURE) for s in climate_states
            ),
            targets=tuple(_target_reading(s) for s in climate_states),
            valves=tuple(self._valve(e) for e in room.valves),
            windows_open=tuple(self._binary(e) for e in room.windows),
        )

    def _state(self, entity_id: str) -> State | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state

    def _number(self, entity_id: str) -> Reading:
        state = self._state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.state)
        return Reading(value, state.last_reported) if value is not None else MISSING

    def _temperature(self, entity_id: str) -> Reading:
        state = self._state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.state)
        if value is None:
            return MISSING
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit == UnitOfTemperature.FAHRENHEIT:
            value = TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
        return Reading(value, state.last_reported)

    def _valve(self, entity_id: str) -> Reading:
        """Valve position as a fraction 0..1."""
        state = self._state(entity_id)
        if state is None:
            return MISSING
        value = _to_float(state.state)
        if value is None:
            return MISSING
        if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE or value > 1:
            value /= 100
        return Reading(min(max(value, 0.0), 1.0), state.last_reported)

    def _binary(self, entity_id: str) -> bool | None:
        state = self._state(entity_id)
        if state is None:
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return None

    def _weather_temperature(self) -> Reading:
        assert self.weather is not None
        state = self._state(self.weather)
        if state is None:
            return MISSING
        value = _to_float(state.attributes.get(ATTR_TEMPERATURE))
        if value is None:
            return MISSING
        unit = state.attributes.get("temperature_unit")
        if unit == UnitOfTemperature.FAHRENHEIT:
            value = TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
        return Reading(value, state.last_reported)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _attribute_reading(state: State | None, attribute: str) -> Reading:
    if state is None:
        return MISSING
    value = _to_float(state.attributes.get(attribute))
    return Reading(value, state.last_reported) if value is not None else MISSING


def _target_reading(state: State | None) -> Reading:
    if state is None or state.state == HVACMode.OFF:
        return MISSING
    return _attribute_reading(state, ATTR_TEMPERATURE)
