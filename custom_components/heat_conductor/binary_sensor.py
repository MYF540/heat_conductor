"""Binary sensors of HeatConductor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator
from .core.models import BoilerState, RoomKind, RoomStatus
from .entity import HeatConductorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatConductorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        HeatRequestSensor(coordinator),
        ProblemSensor(coordinator),
    ]
    if coordinator.gas_flow is not None or coordinator.burner_sensor is not None:
        entities.append(BurnerActiveSensor(coordinator))
    async_add_entities(entities)


class HeatRequestSensor(HeatConductorEntity, BinarySensorEntity):
    """On while HeatConductor requests heat (in observation mode: virtually)."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator: HeatConductorCoordinator) -> None:
        super().__init__(coordinator, "heat_request")

    @property
    def is_on(self) -> bool:
        """Return whether heat is requested."""
        return self.coordinator.data.decision.request_heat

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show whether the decision is only simulated."""
        return {"observation_mode": self.coordinator.settings.observation_mode}


class BurnerActiveSensor(HeatConductorEntity, BinarySensorEntity):
    """On while the burner actually fires (burner sensor or gas flow)."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator: HeatConductorCoordinator) -> None:
        super().__init__(coordinator, "burner_active")

    @property
    def is_on(self) -> bool | None:
        """Return whether the burner fires."""
        return self.coordinator.data.burner_active


class ProblemSensor(HeatConductorEntity, BinarySensorEntity):
    """On when the controller is in failsafe or a regulated room lacks data."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: HeatConductorCoordinator) -> None:
        super().__init__(coordinator, "problem")

    def _stale_rooms(self) -> list[str]:
        return [
            r.name
            for r in self.coordinator.data.rooms
            if r.kind is RoomKind.REGULATED and r.status in (RoomStatus.STALE, RoomStatus.DEGRADED)
        ]

    @property
    def is_on(self) -> bool:
        """Return whether there is a problem."""
        data = self.coordinator.data
        stale = any(
            r.kind is RoomKind.REGULATED and r.status is RoomStatus.STALE for r in data.rooms
        )
        return data.decision.state is BoilerState.FAILSAFE or stale

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List affected rooms."""
        return {"rooms_with_missing_data": self._stale_rooms()}
