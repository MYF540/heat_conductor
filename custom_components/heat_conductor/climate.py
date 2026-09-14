"""Virtual room thermostats of HeatConductor."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import voluptuous as vol

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator, RoomConfig
from .core.models import RoomKind
from .core.setpoint import MAX_TEMPERATURE, MIN_TEMPERATURE, SetpointSource
from .entity import RoomEntity

SERVICE_BOOST = "boost"
SERVICE_CLEAR_OVERRIDE = "clear_override"
ATTR_DURATION = "duration"

_SOURCE_PRESETS = {
    SetpointSource.BOOST: PRESET_BOOST,
    SetpointSource.COMFORT: PRESET_COMFORT,
    SetpointSource.SCHEDULE_COMFORT: PRESET_COMFORT,
    SetpointSource.NO_SCHEDULE: PRESET_COMFORT,
    SetpointSource.OPTIMUM_START: PRESET_COMFORT,
    SetpointSource.ECO: PRESET_ECO,
    SetpointSource.SCHEDULE_ECO: PRESET_ECO,
    SetpointSource.ABSENT: PRESET_ECO,
    SetpointSource.AWAY: PRESET_ECO,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatConductorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one virtual thermostat per regulated room."""
    coordinator = entry.runtime_data
    for room in coordinator.rooms:
        if room.kind is RoomKind.REGULATED:
            async_add_entities([RoomClimate(coordinator, room)], config_subentry_id=room.room_id)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_BOOST,
        {
            vol.Optional(ATTR_DURATION): cv.positive_time_period,
            vol.Optional(ATTR_TEMPERATURE): vol.All(
                vol.Coerce(float), vol.Range(min=MIN_TEMPERATURE, max=MAX_TEMPERATURE)
            ),
        },
        "async_boost",
    )
    platform.async_register_entity_service(SERVICE_CLEAR_OVERRIDE, None, "async_clear_override")


class RoomClimate(RoomEntity, ClimateEntity):
    """Room thermostat: shows the room temperature and the effective target."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_BOOST]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: HeatConductorCoordinator, room: RoomConfig) -> None:
        super().__init__(coordinator, room, "room_climate")

    @property
    def _setpoint(self):  # type: ignore[no-untyped-def]
        data = self.coordinator.data
        return data.setpoint(self.room.room_id) if data else None

    @property
    def current_temperature(self) -> float | None:
        """Room temperature."""
        data = self.room_data
        return round(data.temperature, 1) if data and data.temperature is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Effective target."""
        setpoint = self._setpoint
        return setpoint.target if setpoint else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Heat (automatic) or off (frost protection)."""
        return (
            HVACMode.HEAT
            if self.coordinator.engine.runtime(self.room.room_id).enabled
            else HVACMode.OFF
        )

    @property
    def hvac_action(self) -> HVACAction:
        """Whether the room is currently heated."""
        if self.hvac_mode is HVACMode.OFF:
            return HVACAction.OFF
        data = self.room_data
        result = self.coordinator.data
        if (
            data
            and result
            and (data.demand or 0) > 0.05
            and result.burner_active is not False
            and result.decision.request_heat
        ):
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        """Preset matching the current setpoint source."""
        setpoint = self._setpoint
        if setpoint is None:
            return PRESET_NONE
        return _SOURCE_PRESETS.get(setpoint.source, PRESET_NONE)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why the room has its target."""
        setpoint = self._setpoint
        runtime = self.coordinator.engine.runtime(self.room.room_id)
        result = self.coordinator.data
        return {
            "source": setpoint.source.value if setpoint else None,
            "comfort_temperature": runtime.comfort,
            "eco_temperature": runtime.eco,
            "override_until": setpoint.override_until.isoformat()
            if setpoint and setpoint.override_until
            else None,
            "boost_until": setpoint.boost_until.isoformat()
            if setpoint and setpoint.boost_until
            else None,
            "optimum_start_lead_minutes": round(setpoint.optimum_start_lead.total_seconds() / 60)
            if setpoint and setpoint.optimum_start_lead is not None
            else None,
            "room_control_active": bool(result and result.room_control_active),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Manual target until the next schedule change."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_room_target(self.room.room_id, float(temperature))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch the room on or off."""
        await self.coordinator.async_set_room_enabled(self.room.room_id, hvac_mode is HVACMode.HEAT)

    async def async_turn_on(self) -> None:
        """Room on."""
        await self.coordinator.async_set_room_enabled(self.room.room_id, True)

    async def async_turn_off(self) -> None:
        """Room off (frost protection)."""
        await self.coordinator.async_set_room_enabled(self.room.room_id, False)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Presets map to boost, temporary comfort/eco or automatic."""
        room_id = self.room.room_id
        runtime = self.coordinator.engine.runtime(room_id)
        if preset_mode == PRESET_BOOST:
            await self.coordinator.async_boost(room_id)
        elif preset_mode == PRESET_COMFORT:
            await self.coordinator.async_set_room_target(room_id, runtime.comfort)
        elif preset_mode == PRESET_ECO:
            await self.coordinator.async_set_room_target(room_id, runtime.eco)
        else:
            await self.coordinator.async_clear_override(room_id)

    async def async_boost(
        self, duration: timedelta | None = None, temperature: float | None = None
    ) -> None:
        """Entity service: boost."""
        await self.coordinator.async_boost(self.room.room_id, duration, temperature)

    async def async_clear_override(self) -> None:
        """Entity service: back to automatic."""
        await self.coordinator.async_clear_override(self.room.room_id)
