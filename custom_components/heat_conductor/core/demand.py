"""Per-room heat demand and its aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import ControlParams, Reading, RoomKind, RoomStatus


@dataclass(frozen=True, slots=True)
class RoomInput:
    """Raw inputs of one room at a point in time."""

    room_id: str
    name: str
    kind: RoomKind
    weight: float
    room_temperature: Reading | None
    thermostat_temperatures: tuple[Reading, ...]
    targets: tuple[Reading, ...]
    valves: tuple[Reading, ...]
    windows_open: tuple[bool | None, ...]
    # Target from room control; None = use the thermostats' own targets.
    effective_target: float | None = None
    # Strong sun on a room with large glass area: ignore the temperature deficit.
    solar_active: bool = False


@dataclass(frozen=True, slots=True)
class RoomDemand:
    """Evaluated state of one room."""

    room_id: str
    name: str
    kind: RoomKind
    status: RoomStatus
    weight: float
    demand: float | None
    temperature: float | None
    target: float | None
    deficit: float | None
    valve: float | None


@dataclass(frozen=True, slots=True)
class DemandSummary:
    """Aggregated demand of all regulated rooms."""

    total: float | None
    max_deficit: float | None
    min_temperature: float | None
    rooms_valid: int
    rooms_regulated: int
    top_rooms: tuple[str, ...]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def evaluate_room(room: RoomInput, now: datetime, params: ControlParams) -> RoomDemand:
    """Compute demand (0..1) of a single room."""
    age = params.stale_after

    external = room.room_temperature.valid_value(now, age) if room.room_temperature else None
    trv_temps = [
        v for r in room.thermostat_temperatures if (v := r.valid_value(now, age)) is not None
    ]
    temperature = external if external is not None else _mean(trv_temps)

    targets = [v for r in room.targets if (v := r.valid_value(now, age)) is not None]
    target = max(targets) if targets else None
    if room.effective_target is not None:
        target = room.effective_target

    valves = [v for r in room.valves if (v := r.valid_value(now, age)) is not None]
    valve = _mean([0.0 if v < params.valve_noise else v for v in valves])

    deficit = target - temperature if target is not None and temperature is not None else None

    def result(status: RoomStatus, demand: float | None) -> RoomDemand:
        return RoomDemand(
            room_id=room.room_id,
            name=room.name,
            kind=room.kind,
            status=status,
            weight=room.weight,
            demand=demand,
            temperature=temperature,
            target=target,
            deficit=deficit,
            valve=valve,
        )

    if room.kind is RoomKind.MONITOR:
        return result(RoomStatus.MONITOR_ONLY, None)
    if any(room.windows_open):
        return result(RoomStatus.WINDOW_OPEN, 0.0)

    components: list[float] = []
    if valve is not None:
        components.append(valve)
    if deficit is not None and params.deficit_full_scale > 0 and not room.solar_active:
        components.append(min(max(deficit / params.deficit_full_scale, 0.0), 1.0))
    if not components:
        return result(RoomStatus.STALE, None)

    if room.room_temperature is not None:
        temperature_missing = external is None
    else:
        temperature_missing = len(trv_temps) < len(room.thermostat_temperatures)
    degraded = (
        temperature_missing
        or (room.effective_target is None and len(targets) < len(room.targets))
        or len(valves) < len(room.valves)
    )
    return result(RoomStatus.DEGRADED if degraded else RoomStatus.OK, max(components))


def summarize(rooms: tuple[RoomDemand, ...]) -> DemandSummary:
    """Weighted mean demand over regulated rooms with usable data."""
    regulated = [r for r in rooms if r.kind is RoomKind.REGULATED]
    usable = [r for r in regulated if r.demand is not None and r.weight > 0]
    weight_sum = sum(r.weight for r in usable)
    total = sum(r.weight * r.demand for r in usable) / weight_sum if weight_sum > 0 else None  # type: ignore[operator]

    deficits = [
        r.deficit
        for r in usable
        if r.deficit is not None and r.status is not RoomStatus.WINDOW_OPEN
    ]
    temperatures = [r.temperature for r in rooms if r.temperature is not None]
    top = sorted((r for r in usable if r.demand), key=lambda r: r.demand or 0.0, reverse=True)

    return DemandSummary(
        total=total,
        max_deficit=max(deficits) if deficits else None,
        min_temperature=min(temperatures) if temperatures else None,
        rooms_valid=len(usable),
        rooms_regulated=len(regulated),
        top_rooms=tuple(r.name for r in top[:3]),
    )
