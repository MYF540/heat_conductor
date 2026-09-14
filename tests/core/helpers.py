"""Builders for core test data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.heat_conductor.core.demand import DemandSummary, RoomInput
from custom_components.heat_conductor.core.models import Reading, RoomKind

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


def fresh(value: float, now: datetime = T0) -> Reading:
    """A reading reported just now."""
    return Reading(value, now)


def old(value: float, now: datetime = T0, hours: float = 10) -> Reading:
    """A reading that is far too old."""
    return Reading(value, now - timedelta(hours=hours))


def room(
    name: str = "Bad",
    *,
    kind: RoomKind = RoomKind.REGULATED,
    weight: float = 1.0,
    room_temperature: Reading | None = None,
    thermostat_temperatures: tuple[Reading, ...] = (),
    targets: tuple[Reading, ...] = (),
    valves: tuple[Reading, ...] = (),
    windows_open: tuple[bool | None, ...] = (),
) -> RoomInput:
    """Build a room input."""
    return RoomInput(
        room_id=name.lower(),
        name=name,
        kind=kind,
        weight=weight,
        room_temperature=room_temperature,
        thermostat_temperatures=thermostat_temperatures,
        targets=targets,
        valves=valves,
        windows_open=windows_open,
    )


def demand(
    total: float | None,
    *,
    max_deficit: float | None = 0.0,
    min_temperature: float | None = 20.0,
) -> DemandSummary:
    """Build a demand summary."""
    return DemandSummary(
        total=total,
        max_deficit=max_deficit,
        min_temperature=min_temperature,
        rooms_valid=1 if total is not None else 0,
        rooms_regulated=1,
        top_rooms=(),
    )
