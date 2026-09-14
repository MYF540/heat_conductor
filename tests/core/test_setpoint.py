"""Tests for effective setpoints and thermostat write planning."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.heat_conductor.core.models import OperatingMode
from custom_components.heat_conductor.core.setpoint import (
    RoomRuntime,
    SetpointContext,
    SetpointParams,
    SetpointSource,
    TrvInput,
    TrvState,
    compute_setpoint,
    plan_trv,
    round_half,
)

from .helpers import T0

PARAMS = SetpointParams()


def ctx(**kwargs) -> SetpointContext:  # type: ignore[no-untyped-def]
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
    return RoomRuntime(comfort=21.0, eco=17.0)


@pytest.mark.parametrize(
    ("kwargs", "target", "source"),
    [
        ({}, 21.0, SetpointSource.SCHEDULE_COMFORT),
        ({"schedule_on": False}, 17.0, SetpointSource.SCHEDULE_ECO),
        ({"schedule_on": None}, 21.0, SetpointSource.NO_SCHEDULE),
        ({"present": False}, 17.0, SetpointSource.ABSENT),
        ({"window_open": True}, 12.0, SetpointSource.WINDOW),
        ({"mode": OperatingMode.OFF}, 7.0, SetpointSource.MODE_OFF),
        ({"mode": OperatingMode.ECO}, 17.0, SetpointSource.ECO),
        ({"mode": OperatingMode.COMFORT, "schedule_on": False}, 21.0, SetpointSource.COMFORT),
        ({"vacation_active": True}, 15.0, SetpointSource.VACATION),
    ],
)
def test_priorities(kwargs: dict, target: float, source: SetpointSource) -> None:
    result = compute_setpoint("r", runtime(), ctx(**kwargs), PARAMS)
    assert result.target == target
    assert result.source is source


def test_boost_and_override_expire() -> None:
    rt = runtime()
    rt.boost_until = T0 + timedelta(minutes=30)
    assert compute_setpoint("r", rt, ctx(), PARAMS).source is SetpointSource.BOOST
    rt.override_temp, rt.override_until = 19.5, T0 + timedelta(hours=3)
    later = compute_setpoint("r", rt, ctx(now=T0 + timedelta(minutes=31)), PARAMS)
    assert later.source is SetpointSource.OVERRIDE
    assert later.target == 19.5
    expired = compute_setpoint("r", rt, ctx(now=T0 + timedelta(hours=4)), PARAMS)
    assert expired.source is SetpointSource.SCHEDULE_COMFORT


def test_schedule_change_ends_override() -> None:
    rt = runtime()
    compute_setpoint("r", rt, ctx(schedule_on=True), PARAMS)
    rt.override_temp, rt.override_until = 23.0, T0 + timedelta(hours=3)
    result = compute_setpoint("r", rt, ctx(schedule_on=False), PARAMS)
    assert result.source is SetpointSource.SCHEDULE_ECO


def test_room_off_wins_over_boost() -> None:
    rt = runtime()
    rt.enabled = False
    rt.boost_until = T0 + timedelta(minutes=30)
    assert compute_setpoint("r", rt, ctx(), PARAMS).source is SetpointSource.ROOM_OFF


def test_optimum_start_begins_early() -> None:
    rt = runtime()
    context = ctx(
        schedule_on=False,
        next_schedule_on=T0 + timedelta(minutes=90),
        room_temperature=19.0,
        heat_rate=1.0,  # 2 K missing -> 2 h * 1.25 = 2.5 h lead
    )
    result = compute_setpoint("r", rt, context, PARAMS)
    assert result.source is SetpointSource.OPTIMUM_START
    assert result.optimum_start_lead == timedelta(hours=2.5)

    far = ctx(
        schedule_on=False,
        next_schedule_on=T0 + timedelta(hours=5),
        room_temperature=19.0,
        heat_rate=1.0,
    )
    assert compute_setpoint("r", runtime(), far, PARAMS).source is SetpointSource.SCHEDULE_ECO


def test_changed_flag() -> None:
    rt = runtime()
    assert compute_setpoint("r", rt, ctx(), PARAMS).changed
    assert not compute_setpoint("r", rt, ctx(), PARAMS).changed
    assert compute_setpoint("r", rt, ctx(schedule_on=False), PARAMS).changed


def trv(
    target: float | None = 18.0, temperature: float | None = 20.0, mode: str = "heat"
) -> TrvInput:
    return TrvInput("climate.bad", True, target, temperature, mode)


def test_write_on_target_change_with_compensation() -> None:
    state = TrvState()
    command, manual = plan_trv(
        state,
        trv(target=18.0, temperature=22.0),
        target=21.0,
        target_changed=True,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=20.0,
        compensation=True,
        now=T0,
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert manual is None
    assert command is not None
    assert command.temperature == 23.0  # 21 + offset 2
    assert state.last_written == 23.0


def test_no_write_when_already_set_and_throttled_drift() -> None:
    state = TrvState(last_written=21.0, last_write_at=T0)
    command, _ = plan_trv(
        state,
        trv(target=21.0),
        target=21.0,
        target_changed=False,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0 + timedelta(minutes=1),
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert command is None
    state2 = TrvState(last_written=21.0, last_write_at=T0)
    command2, _ = plan_trv(
        state2,
        trv(target=21.0, temperature=21.0),
        target=22.0,
        target_changed=False,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0 + timedelta(minutes=1),
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert command2 is None  # not changed and within write interval
    command3, _ = plan_trv(
        state2,
        trv(target=21.0, temperature=21.0),
        target=22.0,
        target_changed=False,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0 + timedelta(minutes=16),
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert command3 is not None


def test_duty_cycle_blocks_writes() -> None:
    command, _ = plan_trv(
        TrvState(),
        trv(target=18.0),
        target=21.0,
        target_changed=True,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0,
        params=PARAMS,
        duty_cycle_ok=False,
    )
    assert command is None


def test_manual_change_at_thermostat_becomes_override() -> None:
    state = TrvState(last_written=21.0, last_write_at=T0)
    command, manual = plan_trv(
        state,
        trv(target=23.0),
        target=21.0,
        target_changed=False,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0 + timedelta(minutes=10),
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert command is None
    assert manual == 23.0


def test_window_function_of_thermostat_is_not_manual() -> None:
    state = TrvState(last_written=21.0, last_write_at=T0)
    _, manual = plan_trv(
        state,
        trv(target=12.0),
        target=21.0,
        target_changed=False,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0 + timedelta(minutes=10),
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert manual is None


def test_auto_mode_is_switched_to_heat() -> None:
    command, _ = plan_trv(
        TrvState(),
        trv(target=21.0, mode="auto"),
        target=21.0,
        target_changed=False,
        source=SetpointSource.SCHEDULE_COMFORT,
        room_temperature=None,
        compensation=False,
        now=T0,
        params=PARAMS,
        duty_cycle_ok=True,
    )
    assert command is not None
    assert command.set_heat_mode


def test_round_half() -> None:
    assert round_half(21.24) == 21.0
    assert round_half(21.25) == 21.5
    assert round_half(20.74) == 20.5


def test_runtime_roundtrip() -> None:
    rt = runtime()
    rt.override_temp, rt.override_until = 22.0, T0
    rt.trvs["climate.x"] = TrvState(21.5, T0, 1.0, T0)
    restored = RoomRuntime.from_dict(rt.to_dict(), PARAMS)
    assert restored.override_temp == 22.0
    assert restored.override_until == T0
    assert restored.trvs["climate.x"].offset == 1.0
