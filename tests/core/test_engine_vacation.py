"""Automatic vacation inside the engine pipeline."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.heat_conductor.core.engine import (
    EngineSnapshot,
    HeatingEngine,
    RoomControlInput,
)
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode
from custom_components.heat_conductor.core.setpoint import SetpointSource, TrvInput
from custom_components.heat_conductor.core.vacation import VacationParams

from .helpers import T0, fresh, room

STEP = timedelta(minutes=10)


def snapshot(now: datetime, *, present: bool | None) -> EngineSnapshot:
    return EngineSnapshot(
        now=now,
        rooms=(
            room(
                "Bad",
                room_temperature=fresh(20.0, now),
                targets=(fresh(20.0, now),),
                valves=(fresh(0.0, now),),
            ),
        ),
        outdoor_sensors=(fresh(3.0, now),),
        weather_temperature=None,
        flow_temperature=None,
        return_temperature=None,
        gas_flow=None,
        gas_meter=None,
        burner_on=None,
        relay_on=None,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=False,
        room_control_enabled=False,
        present=present,
        room_controls=(
            RoomControlInput(
                room_id="bad", trvs=(TrvInput("climate.bad", True, 20.0, 20.0, "heat"),)
            ),
        ),
    )


def _evaluate(engine: HeatingEngine, start: datetime, *, present: bool | None, hours: float):
    """Run evaluations for a while and return the last result."""
    moment, end, result = start, start + timedelta(hours=hours), None
    while moment <= end:
        result = engine.evaluate(snapshot(moment, present=present))
        moment += STEP
    return result


def test_absence_switches_the_installation_to_vacation() -> None:
    """After two days without anybody home the rooms follow the vacation setpoint."""
    engine = HeatingEngine(ControlParams())
    result = _evaluate(engine, T0, present=False, hours=49)

    assert result.auto_vacation_active is True
    assert result.vacation_active is True
    assert result.setpoint("bad").source is SetpointSource.VACATION
    assert result.setpoint("bad").target == 15.0


def test_return_ends_the_vacation() -> None:
    """Three hours at home switch back to normal operation."""
    engine = HeatingEngine(ControlParams())
    _evaluate(engine, T0, present=False, hours=49)
    result = _evaluate(engine, T0 + timedelta(hours=49), present=True, hours=4)

    assert result.auto_vacation_active is False
    assert result.setpoint("bad").source is not SetpointSource.VACATION


def test_nothing_is_learned_during_a_vacation() -> None:
    """A vacation says nothing about everyday habits."""
    engine = HeatingEngine(ControlParams())
    _evaluate(engine, T0, present=False, hours=49)
    learned_days = engine.learner.presence.days_observed

    _evaluate(engine, T0 + timedelta(hours=49), present=False, hours=48)
    assert engine.learner.presence.days_observed == learned_days


def test_scheduled_vacation_also_pauses_learning() -> None:
    """A vacation set by the user counts the same."""
    engine = HeatingEngine(ControlParams(), vacation_params=VacationParams(enabled=False))
    moment = T0
    for _ in range(60):
        engine.evaluate(replace(snapshot(moment, present=True), vacation_active=True))
        moment += STEP
    assert engine.learner.presence.days_observed == 0


def test_automatic_vacation_can_be_switched_off() -> None:
    """With detection disabled a long absence changes nothing."""
    engine = HeatingEngine(ControlParams(), vacation_params=VacationParams(enabled=False))
    result = _evaluate(engine, T0, present=False, hours=72)

    assert result.auto_vacation_active is False
    assert result.setpoint("bad").source is SetpointSource.ABSENT
