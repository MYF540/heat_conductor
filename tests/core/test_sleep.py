"""Night setback: night window, sleep sensor and the learned night."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.heat_conductor.core.models import OperatingMode
from custom_components.heat_conductor.core.setpoint import (
    RoomRuntime,
    SetpointContext,
    SetpointParams,
    SetpointSource,
    compute_setpoint,
)
from custom_components.heat_conductor.core.sleep import (
    NightPattern,
    SleepParams,
    SleepSource,
    SleepTracker,
    parse_time_of_day,
)

from .helpers import T0

NIGHT = SleepParams(window_start=23 * 60, window_end=6 * 60 + 30)
MIDNIGHT = T0.replace(hour=0, minute=0, second=0, microsecond=0)


def at(hour: float, day: int = 0) -> datetime:
    """A time on the given day offset."""
    return MIDNIGHT + timedelta(days=day, hours=hour)


def _run(
    tracker: SleepTracker,
    start: datetime,
    *,
    sensor: bool | None,
    minutes: float,
    pattern: NightPattern | None = None,
    params: SleepParams = NIGHT,
):
    """Feed one sensor state minute by minute and return the last state."""
    moment, end, state = start, start + timedelta(minutes=minutes), None
    while moment <= end:
        state = tracker.update(moment, sensor, pattern or NightPattern(), params)
        moment += timedelta(minutes=1)
    return state


# -- night window ----------------------------------------------------------


@pytest.mark.parametrize(
    ("hour", "sleeping"),
    [(22.0, False), (23.5, True), (2.0, True), (6.0, True), (7.0, False)],
)
def test_night_window_across_midnight(hour: float, sleeping: bool) -> None:
    """The window from 23:00 to 06:30 also covers the hours after midnight."""
    state = SleepTracker().update(at(hour), None, NightPattern(), NIGHT)
    assert state.sleeping is sleeping
    assert state.source is (SleepSource.WINDOW if sleeping else SleepSource.NONE)


def test_without_a_window_and_without_a_sensor_nothing_happens() -> None:
    """The night setback is optional."""
    state = SleepTracker().update(at(2.0), None, NightPattern(), SleepParams())
    assert not state.sleeping


# -- sleep sensor ----------------------------------------------------------


def test_sensor_needs_the_confirmation_time() -> None:
    """Lying down briefly does not start the night."""
    tracker = SleepTracker()
    early = _run(tracker, at(21.0), sensor=True, minutes=19)
    assert not early.sleeping

    confirmed = _run(tracker, at(21.0) + timedelta(minutes=20), sensor=True, minutes=1)
    assert confirmed.sleeping
    assert confirmed.source is SleepSource.SENSOR
    assert confirmed.since is not None


def test_getting_up_ends_the_night_inside_the_window() -> None:
    """Awake for the wake-up time beats the night window."""
    tracker = SleepTracker()
    _run(tracker, at(23.0), sensor=True, minutes=30)
    assert tracker.sensor_sleeping

    early = _run(tracker, at(5.5, 1), sensor=False, minutes=10)
    assert early.sleeping  # still within the wake-up time
    awake = _run(tracker, at(5.5, 1) + timedelta(minutes=16), sensor=False, minutes=1)
    assert not awake.sleeping
    assert awake.sensor_sleeping is False


def test_night_trip_does_not_end_the_setback() -> None:
    """A few minutes out of bed keep the night running."""
    tracker = SleepTracker()
    _run(tracker, at(23.0), sensor=True, minutes=30)
    trip = _run(tracker, at(3.0, 1), sensor=False, minutes=10)
    assert trip.sleeping
    back = _run(tracker, at(3.2, 1), sensor=True, minutes=5)
    assert back.sleeping


# -- learned night ---------------------------------------------------------


def _teach(pattern: NightPattern, days: int = 20) -> None:
    """Sleep from 22:30 to 06:00 for a number of days."""
    moment = MIDNIGHT - timedelta(days=days)
    end = MIDNIGHT
    while moment < end:
        hour = moment.hour + moment.minute / 60
        pattern.update(moment, hour >= 22.5 or hour < 6.0)
        moment += timedelta(minutes=5)


def test_learned_night_applies_without_a_window() -> None:
    """After enough nights the learned window carries the setback."""
    pattern = NightPattern()
    _teach(pattern)
    assert pattern.ready

    params = SleepParams()
    assert SleepTracker().update(at(23.0), None, pattern, params).source is SleepSource.LEARNED
    assert not SleepTracker().update(at(12.0), None, pattern, params).sleeping


def test_learned_night_can_be_switched_off() -> None:
    """With the option off only sensor and window count."""
    pattern = NightPattern()
    _teach(pattern)
    params = SleepParams(use_learned=False)
    assert not SleepTracker().update(at(23.0), None, pattern, params).sleeping


def test_state_survives_a_restart() -> None:
    """The confirmed sensor state is persisted."""
    tracker = SleepTracker()
    _run(tracker, at(23.0), sensor=True, minutes=30)
    restored = SleepTracker()
    restored.restore(tracker.to_dict())
    assert restored.sensor_sleeping is True
    assert restored.since == tracker.since


@pytest.mark.parametrize(
    ("value", "minutes"),
    [("23:00", 1380), ("06:30:00", 390), ("", None), (None, None), ("25:00", None), ("abc", None)],
)
def test_parse_time_of_day(value: str | None, minutes: int | None) -> None:
    """Times come from the options as strings."""
    assert parse_time_of_day(value) == minutes


# -- effect on the room setpoint -------------------------------------------


def ctx(**kwargs):  # type: ignore[no-untyped-def]
    values = {
        "now": T0,
        "mode": OperatingMode.AUTO,
        "vacation_active": False,
        "present": True,
        "schedule_on": True,
        "next_schedule_on": None,
        "window_open": False,
        "room_temperature": 20.0,
        "heat_rate": None,
        "dead_time": None,
    }
    values.update(kwargs)
    return SetpointContext(**values)


def test_sleeping_rooms_fall_back_to_eco() -> None:
    """The night beats the schedule and the usage detection."""
    runtime = RoomRuntime(comfort=21.0, eco=18.0)
    params = SetpointParams()

    awake = compute_setpoint("bad", runtime, ctx(activity=True), params)
    assert awake.source is SetpointSource.USAGE_ACTIVE

    asleep = compute_setpoint("bad", runtime, ctx(activity=True, sleeping=True), params)
    assert asleep.source is SetpointSource.SLEEP
    assert asleep.target == 18.0


@pytest.mark.parametrize(
    ("kwargs", "source"),
    [
        ({"window_open": True}, SetpointSource.WINDOW),
        ({"mode": OperatingMode.COMFORT}, SetpointSource.COMFORT),
        ({"vacation_active": True}, SetpointSource.VACATION),
    ],
)
def test_stronger_reasons_win_over_the_night(kwargs: dict, source: SetpointSource) -> None:
    """Window, comfort mode and vacation stay in charge."""
    runtime = RoomRuntime(comfort=21.0, eco=18.0)
    result = compute_setpoint("bad", runtime, ctx(sleeping=True, **kwargs), SetpointParams())
    assert result.source is source


def test_boost_wins_over_the_night() -> None:
    """A boost during the night heats the room."""
    runtime = RoomRuntime(comfort=21.0, eco=18.0)
    runtime.boost_until = T0 + timedelta(minutes=10)
    result = compute_setpoint("bad", runtime, ctx(sleeping=True), SetpointParams())
    assert result.source is SetpointSource.BOOST
