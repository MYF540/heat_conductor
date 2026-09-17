"""Binary sensors of HeatConductor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator, RoomConfig
from .core.models import BoilerState, RoomKind, RoomStatus
from .entity import HeatConductorEntity, RoomEntity


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
    if coordinator.has_gas_source or coordinator.burner_sensor is not None:
        entities.append(BurnerActiveSensor(coordinator))
        if coordinator.return_temperature is not None:
            entities.append(CondensingSensor(coordinator))
    if coordinator.entities.watchdog_url is not None:
        entities.append(WatchdogSensor(coordinator))
    async_add_entities(entities)
    for room in coordinator.rooms:
        if room.kind is RoomKind.REGULATED and room.usage_entities:
            async_add_entities(
                [RoomInUseSensor(coordinator, room)], config_subentry_id=room.room_id
            )


class RoomInUseSensor(RoomEntity, BinarySensorEntity):
    """On while the room counts as in use (activity or hold time)."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator: HeatConductorCoordinator, room: RoomConfig) -> None:
        super().__init__(coordinator, room, "room_in_use")

    @property
    def is_on(self) -> bool | None:
        """Return whether the room is in use."""
        setpoint = (
            self.coordinator.data.setpoint(self.room.room_id) if self.coordinator.data else None
        )
        return setpoint.room_active if setpoint else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Last detected activity and the configured entities."""
        runtime = self.coordinator.engine.runtime(self.room.room_id)
        last = runtime.last_active_at
        return {
            "last_activity": last.isoformat() if last else None,
            "detection_enabled": runtime.usage_enabled,
            "activity_entities": list(self.room.usage_entities),
        }


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


class CondensingSensor(HeatConductorEntity, BinarySensorEntity):
    """On while the burner fires with a return temperature low enough to condense."""

    def __init__(self, coordinator: HeatConductorCoordinator) -> None:
        super().__init__(coordinator, "condensing")

    @property
    def is_on(self) -> bool | None:
        """Return whether the boiler currently condenses."""
        return self.coordinator.data.energy.condensing

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show the configured limit."""
        return {"return_temperature_limit": self.coordinator.energy_params.condensing_return_limit}


class WatchdogSensor(HeatConductorEntity, BinarySensorEntity):
    """On while the relay watchdog accepts heartbeats."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HeatConductorCoordinator) -> None:
        super().__init__(coordinator, "watchdog")

    @property
    def is_on(self) -> bool | None:
        """Return whether the watchdog is reachable."""
        return self.coordinator.watchdog_connected()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Last successful heartbeat and whether the watchdog is armed."""
        last = self.coordinator.watchdog_ok_at
        return {
            "last_heartbeat": last.isoformat() if last else None,
            "armed": self.coordinator.actuator_active,
        }


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
