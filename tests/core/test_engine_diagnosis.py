"""Boiler feedback inside the engine pipeline."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from custom_components.heat_conductor.core.diagnosis import RELAY_FEEDBACK_DELAY
from custom_components.heat_conductor.core.engine import HeatingEngine
from custom_components.heat_conductor.core.models import ControlParams

from .helpers import T0, fresh
from .test_engine_vacation import snapshot


def test_spread_needs_a_running_pump() -> None:
    """Without circulation flow minus return is no spread."""
    engine = HeatingEngine(ControlParams())
    base = replace(
        snapshot(T0, present=True),
        flow_temperature=fresh(50.0, T0),
        return_temperature=fresh(40.0, T0),
    )
    assert engine.evaluate(replace(base, pump_on=True)).spread == 10.0
    assert engine.evaluate(replace(base, pump_on=False)).spread is None
    assert engine.evaluate(base).spread == 10.0  # no pump entity: shown as before


def test_relay_feedback_mismatch_is_reported() -> None:
    """Relay on, but the boiler does not see the demand."""
    engine = HeatingEngine(ControlParams())
    first = replace(snapshot(T0, present=True), relay_on=True, relay_feedback=False)
    assert not engine.evaluate(first).diagnosis.relay_mismatch

    later = T0 + RELAY_FEEDBACK_DELAY
    result = engine.evaluate(
        replace(snapshot(later, present=True), relay_on=True, relay_feedback=False)
    )
    assert result.diagnosis.relay_mismatch
    assert result.diagnosis.relay_feedback is False


def test_burner_lock_is_passed_through() -> None:
    """The remaining lock time reaches the result."""
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(
        replace(snapshot(T0, present=True), burner_lock=fresh(6.0, T0), burner_on=False)
    )
    assert result.diagnosis.burner_lock_minutes == 6.0
    assert result.diagnosis.burner_locked


def test_rooms_can_be_left_out_of_the_curve_suggestion() -> None:
    """A room marked as not relevant never becomes the bottleneck."""
    engine = HeatingEngine(ControlParams())
    base = snapshot(T0, present=True)
    control = replace(base.room_controls[0], curve_reference=False)
    moment = T0
    for _ in range(60):
        engine.evaluate(
            replace(
                snapshot(moment, present=True),
                room_controls=(control,),
                burner_on=True,
                flow_setpoint=fresh(45.0, moment),
            )
        )
        moment += timedelta(minutes=1)
    assert engine.learner.curve_advice.bands == {}

    moment = T0
    for _ in range(60):
        engine.evaluate(
            replace(
                snapshot(moment, present=True),
                burner_on=True,
                flow_setpoint=fresh(45.0, moment),
            )
        )
        moment += timedelta(minutes=1)
    assert engine.learner.curve_advice.bands
