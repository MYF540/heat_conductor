"""Usage based heating: a room is only heated to comfort while it is in use."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.heat_conductor.core.models import OperatingMode
from custom_components.heat_conductor.core.setpoint import (
    RoomRuntime,
    SetpointContext,
    SetpointParams,
    SetpointSource,
    compute_setpoint,
)

from .helpers import T0

PARAMS = SetpointParams()


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


def runtime() -> RoomRuntime:
    return RoomRuntime(comfort=20.0, eco=18.0)


@pytest.mark.parametrize(
    ("activity", "schedule_on", "target", "source"),
    [
        (True, True, 20.0, SetpointSource.USAGE_ACTIVE),
        (False, True, 18.0, SetpointSource.USAGE_IDLE),
        (True, False, 20.0, SetpointSource.USAGE_ACTIVE),
        (False, False, 18.0, SetpointSource.SCHEDULE_ECO),
        (None, True, 20.0, SetpointSource.SCHEDULE_COMFORT),
    ],
)
def test_usage_decides_between_comfort_and_eco(
    activity: bool | None, schedule_on: bool, target: float, source: SetpointSource
) -> None:
    """Active rooms get comfort, unused rooms get eco."""
    result = compute_setpoint(
        "bad", runtime(), ctx(activity=activity, schedule_on=schedule_on), PARAMS
    )
    assert result.target == target
    assert result.source is source
    assert result.room_active is activity


def test_usage_does_not_override_setback_when_switched_off() -> None:
    """With usage_in_eco off a used room still follows the schedule."""
    params = SetpointParams(usage_in_eco=False)
    result = compute_setpoint("bad", runtime(), ctx(activity=True, schedule_on=False), params)
    assert result.target == 18.0
    assert result.source is SetpointSource.SCHEDULE_ECO


def test_room_stays_in_use_during_the_hold_time() -> None:
    """After the last activity the room stays warm for the hold time."""
    rt = runtime()
    compute_setpoint("bad", rt, ctx(activity=True), PARAMS)

    inside = compute_setpoint(
        "bad", rt, ctx(now=T0 + timedelta(minutes=29), activity=False), PARAMS
    )
    assert inside.source is SetpointSource.USAGE_ACTIVE

    after = compute_setpoint("bad", rt, ctx(now=T0 + timedelta(minutes=31), activity=False), PARAMS)
    assert after.source is SetpointSource.USAGE_IDLE
    assert after.target == 18.0


def test_detection_can_be_disabled_per_room() -> None:
    """A room with detection off ignores its activity sensors."""
    rt = runtime()
    rt.usage_enabled = False
    result = compute_setpoint("bad", rt, ctx(activity=False), PARAMS)
    assert result.source is SetpointSource.SCHEDULE_COMFORT
    assert result.target == 20.0
    assert result.room_active is None


@pytest.mark.parametrize(
    ("kwargs", "source"),
    [
        ({"window_open": True}, SetpointSource.WINDOW),
        ({"mode": OperatingMode.OFF}, SetpointSource.MODE_OFF),
        ({"vacation_active": True}, SetpointSource.VACATION),
        ({"present": False}, SetpointSource.ABSENT),
    ],
)
def test_usage_never_overrides_stronger_reasons(kwargs: dict, source: SetpointSource) -> None:
    """Window, off, vacation and absence stay in charge."""
    result = compute_setpoint("bad", runtime(), ctx(activity=True, **kwargs), PARAMS)
    assert result.source is source


def test_usage_state_survives_a_restart() -> None:
    """The last activity is persisted so the hold time is not restarted."""
    rt = runtime()
    compute_setpoint("bad", rt, ctx(activity=True), PARAMS)
    rt.usage_enabled = False

    restored = RoomRuntime.from_dict(rt.to_dict(), PARAMS)
    assert restored.last_active_at == T0
    assert restored.usage_enabled is False
