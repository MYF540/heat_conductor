"""Comfort and eco temperatures per room."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator, RoomConfig
from .core.models import RoomKind
from .entity import RoomEntity

LIMITS = {"comfort": (12.0, 28.0), "eco": (10.0, 24.0)}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatConductorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the room temperature numbers."""
    coordinator = entry.runtime_data
    for room in coordinator.rooms:
        if room.kind is RoomKind.REGULATED:
            async_add_entities(
                [RoomTemperatureNumber(coordinator, room, key) for key in LIMITS],
                config_subentry_id=room.room_id,
            )


class RoomTemperatureNumber(RoomEntity, NumberEntity):
    """Comfort or eco temperature of a room."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: HeatConductorCoordinator, room: RoomConfig, key: str) -> None:
        super().__init__(coordinator, room, f"{key}_temperature")
        self._key = key
        self._attr_native_min_value, self._attr_native_max_value = LIMITS[key]

    @property
    def native_value(self) -> float:
        """Current value."""
        return float(getattr(self.coordinator.engine.runtime(self.room.room_id), self._key))

    async def async_set_native_value(self, value: float) -> None:
        """Change the value."""
        await self.coordinator.async_set_room_value(self.room.room_id, self._key, value)
