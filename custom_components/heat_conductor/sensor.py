"""Sensors of HeatConductor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator, RoomConfig
from .core.demand import RoomDemand
from .core.engine import EngineResult
from .core.models import BoilerState, Reason, RoomKind, RoomStatus
from .entity import HeatConductorEntity, RoomEntity


def _percent(value: float | None) -> float | None:
    return round(value * 100, 1) if value is not None else None


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _minutes(result: EngineResult, burner: bool) -> float | None:
    stats = result.burner_stats if burner else result.boiler_stats
    return round(stats.runtime.total_seconds() / 60, 1) if stats else None


@dataclass(frozen=True, kw_only=True)
class HeatConductorSensorDescription(SensorEntityDescription):
    """Describes a central sensor."""

    value_fn: Callable[[EngineResult], Any]
    attributes_fn: Callable[[EngineResult], dict[str, Any]] | None = None
    exists_fn: Callable[[HeatConductorCoordinator], bool] = lambda _: True


def _reason_attributes(result: EngineResult) -> dict[str, Any]:
    decision = result.decision
    return {
        "remaining_minutes": (
            round(decision.remaining.total_seconds() / 60, 1) if decision.remaining else None
        ),
        "starts_last_hour": decision.starts_last_hour,
        "top_rooms": list(result.demand.top_rooms),
        "max_deficit": _round(result.demand.max_deficit),
    }


CENTRAL_SENSORS: tuple[HeatConductorSensorDescription, ...] = (
    HeatConductorSensorDescription(
        key="total_demand",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda r: _percent(r.demand.total),
        attributes_fn=lambda r: {
            "rooms_valid": r.demand.rooms_valid,
            "rooms_regulated": r.demand.rooms_regulated,
        },
    ),
    HeatConductorSensorDescription(
        key="boiler_state",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in BoilerState],
        value_fn=lambda r: r.decision.state.value,
    ),
    HeatConductorSensorDescription(
        key="decision_reason",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in Reason],
        value_fn=lambda r: r.decision.reason.value,
        attributes_fn=_reason_attributes,
    ),
    HeatConductorSensorDescription(
        key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: _round(r.outdoor.value),
        attributes_fn=lambda r: {
            "source": r.outdoor.source,
            "sensors_used": r.outdoor.sensors_used,
        },
    ),
    HeatConductorSensorDescription(
        key="outdoor_temperature_smoothed",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: _round(r.outdoor_smoothed),
    ),
    HeatConductorSensorDescription(
        key="boiler_starts_today",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda r: r.boiler_stats.starts,
    ),
    HeatConductorSensorDescription(
        key="boiler_runtime_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda r: _minutes(r, burner=False),
    ),
    HeatConductorSensorDescription(
        key="burner_starts_today",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda r: r.burner_stats.starts if r.burner_stats else None,
        exists_fn=lambda c: c.gas_flow is not None or c.burner_sensor is not None,
    ),
    HeatConductorSensorDescription(
        key="burner_runtime_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda r: _minutes(r, burner=True),
        exists_fn=lambda c: c.gas_flow is not None or c.burner_sensor is not None,
    ),
    HeatConductorSensorDescription(
        key="temperature_spread",
        native_unit_of_measurement="K",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: _round(r.spread),
        attributes_fn=lambda r: {
            "flow_temperature": _round(r.flow_temperature),
            "return_temperature": _round(r.return_temperature),
        },
        exists_fn=lambda c: c.flow_temperature is not None and c.return_temperature is not None,
    ),
)


@dataclass(frozen=True, kw_only=True)
class RoomSensorDescription(SensorEntityDescription):
    """Describes a room sensor."""

    value_fn: Callable[[RoomDemand], Any]
    attributes_fn: Callable[[RoomDemand], dict[str, Any]] | None = None
    regulated_only: bool = False


ROOM_SENSORS: tuple[RoomSensorDescription, ...] = (
    RoomSensorDescription(
        key="room_demand",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        regulated_only=True,
        value_fn=lambda r: _percent(r.demand),
        attributes_fn=lambda r: {
            "target_temperature": _round(r.target),
            "deficit": _round(r.deficit),
            "valve": _percent(r.valve),
            "weight": r.weight,
        },
    ),
    RoomSensorDescription(
        key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: _round(r.temperature),
    ),
    RoomSensorDescription(
        key="room_status",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in RoomStatus],
        value_fn=lambda r: r.status.value,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatConductorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        CentralSensor(coordinator, d) for d in CENTRAL_SENSORS if d.exists_fn(coordinator)
    )
    for room in coordinator.rooms:
        async_add_entities(
            (
                RoomSensor(coordinator, room, d)
                for d in ROOM_SENSORS
                if not d.regulated_only or room.kind is RoomKind.REGULATED
            ),
            config_subentry_id=room.room_id,
        )


class CentralSensor(HeatConductorEntity, SensorEntity):
    """A sensor of the central device."""

    entity_description: HeatConductorSensorDescription

    def __init__(
        self, coordinator: HeatConductorCoordinator, description: HeatConductorSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class RoomSensor(RoomEntity, SensorEntity):
    """A sensor of a room device."""

    entity_description: RoomSensorDescription

    def __init__(
        self,
        coordinator: HeatConductorCoordinator,
        room: RoomConfig,
        description: RoomSensorDescription,
    ) -> None:
        super().__init__(coordinator, room, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the state."""
        data = self.room_data
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        data = self.room_data
        if data is None or self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(data)
