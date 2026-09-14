"""Tests for room demand evaluation."""

from __future__ import annotations

import pytest

from custom_components.heat_conductor.core.demand import evaluate_room, summarize
from custom_components.heat_conductor.core.models import ControlParams, RoomKind, RoomStatus

from .helpers import T0, fresh, old, room

PARAMS = ControlParams()


def test_valve_open_drives_demand() -> None:
    result = evaluate_room(
        room(
            thermostat_temperatures=(fresh(20.5),),
            targets=(fresh(21.0),),
            valves=(fresh(0.8),),
        ),
        T0,
        PARAMS,
    )
    assert result.status is RoomStatus.OK
    assert result.demand == pytest.approx(0.8)
    assert result.deficit == pytest.approx(0.5)


def test_external_sensor_preferred_and_deficit_drives_demand() -> None:
    result = evaluate_room(
        room(
            room_temperature=fresh(19.0),
            thermostat_temperatures=(fresh(22.0),),
            targets=(fresh(21.0),),
            valves=(fresh(0.1),),
        ),
        T0,
        PARAMS,
    )
    assert result.temperature == 19.0
    assert result.demand == 1.0


def test_valve_noise_is_ignored() -> None:
    result = evaluate_room(
        room(thermostat_temperatures=(fresh(21.0),), targets=(fresh(21.0),), valves=(fresh(0.02),)),
        T0,
        PARAMS,
    )
    assert result.demand == 0.0


def test_stale_inputs_make_room_stale() -> None:
    result = evaluate_room(
        room(thermostat_temperatures=(old(21.4),), targets=(old(20.0),), valves=(old(0.25),)),
        T0,
        PARAMS,
    )
    assert result.status is RoomStatus.STALE
    assert result.demand is None


def test_partially_stale_room_is_degraded() -> None:
    result = evaluate_room(
        room(
            room_temperature=old(18.0),
            thermostat_temperatures=(fresh(20.0),),
            targets=(fresh(21.0),),
            valves=(fresh(0.4),),
        ),
        T0,
        PARAMS,
    )
    assert result.status is RoomStatus.DEGRADED
    assert result.temperature == 20.0
    assert result.demand == pytest.approx(1.0)


def test_window_open_forces_zero_demand() -> None:
    result = evaluate_room(
        room(
            thermostat_temperatures=(fresh(17.0),),
            targets=(fresh(21.0),),
            valves=(fresh(1.0),),
            windows_open=(True,),
        ),
        T0,
        PARAMS,
    )
    assert result.status is RoomStatus.WINDOW_OPEN
    assert result.demand == 0.0


def test_monitor_room_has_no_demand_but_temperature() -> None:
    result = evaluate_room(
        room("Schlafzimmer", kind=RoomKind.MONITOR, room_temperature=fresh(16.5)),
        T0,
        PARAMS,
    )
    assert result.status is RoomStatus.MONITOR_ONLY
    assert result.demand is None
    assert result.temperature == 16.5


def test_summary_weighted_mean_excludes_stale_and_monitor() -> None:
    rooms = (
        evaluate_room(
            room(
                "A",
                weight=2.0,
                targets=(fresh(21),),
                thermostat_temperatures=(fresh(21),),
                valves=(fresh(1.0),),
            ),
            T0,
            PARAMS,
        ),
        evaluate_room(
            room(
                "B",
                weight=1.0,
                targets=(fresh(21),),
                thermostat_temperatures=(fresh(21),),
                valves=(fresh(0.0),),
            ),
            T0,
            PARAMS,
        ),
        evaluate_room(room("C", valves=(old(1.0),)), T0, PARAMS),
        evaluate_room(room("D", kind=RoomKind.MONITOR, room_temperature=fresh(5.0)), T0, PARAMS),
    )
    summary = summarize(rooms)
    assert summary.total == pytest.approx(2 / 3)
    assert summary.rooms_valid == 2
    assert summary.rooms_regulated == 3
    assert summary.min_temperature == 5.0
    assert summary.top_rooms == ("A",)


def test_summary_without_usable_rooms_has_no_total() -> None:
    summary = summarize((evaluate_room(room(valves=(old(1.0),)), T0, PARAMS),))
    assert summary.total is None
