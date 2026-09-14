"""Base entities for HeatConductor."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HeatConductorCoordinator, RoomConfig
from .core.demand import RoomDemand


class HeatConductorEntity(CoordinatorEntity[HeatConductorCoordinator]):
    """Entity attached to the central HeatConductor device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HeatConductorCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="HeatConductor",
            model="Heating controller",
            entry_type=DeviceEntryType.SERVICE,
        )


class RoomEntity(CoordinatorEntity[HeatConductorCoordinator]):
    """Entity attached to a room device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HeatConductorCoordinator, room: RoomConfig, key: str) -> None:
        super().__init__(coordinator)
        self.room = room
        self._attr_translation_key = key
        self._attr_unique_id = f"{room.room_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, room.room_id)},
            name=room.name,
            manufacturer="HeatConductor",
            model="Room",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def room_data(self) -> RoomDemand | None:
        """Evaluated data of this room."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.room(self.room.room_id)

    @property
    def available(self) -> bool:
        """Available while the room has been evaluated."""
        return super().available and self.room_data is not None
