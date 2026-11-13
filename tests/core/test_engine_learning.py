"""The room learners follow delivered heat, not the burner's anti-cycling pauses."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.heat_conductor.core.engine import EngineSnapshot, HeatingEngine
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode

from .helpers import T0, fresh, room


def _snapshot(
    now: datetime, *, rise: float, burner: bool, actuator: bool, relay: bool | None
) -> EngineSnapshot:
    return EngineSnapshot(
        now=now,
        rooms=(
            room(
                "Bad",
                room_temperature=fresh(17.0 + rise, now),
                targets=(fresh(22.0, now),),
                valves=(fresh(0.9, now),),
            ),
        ),
        outdoor_sensors=(fresh(3.0, now),),
        weather_temperature=None,
        flow_temperature=None,
        return_temperature=None,
        gas_flow=None,
        gas_meter=None,
        burner_on=burner,
        relay_on=relay,
        mode=OperatingMode.AUTO,
        automation_enabled=True,
        actuator_active=actuator,
    )


def _run(*, actuator: bool, relay: bool | None, cycle: int | None) -> HeatingEngine:
    """Three hours at +1 K/h; the burner runs `cycle` minutes on and off (None: always on)."""
    engine = HeatingEngine(ControlParams())
    for minute in range(181):
        burner = True if cycle is None else (minute // cycle) % 2 == 0
        engine.evaluate(
            _snapshot(
                T0 + timedelta(minutes=minute),
                rise=minute / 60,
                burner=burner,
                actuator=actuator,
                relay=relay,
            )
        )
    return engine


def test_heat_rate_is_learned_while_the_burner_cycles_in_a_release() -> None:
    engine = _run(actuator=True, relay=True, cycle=10)
    assert engine.learner.room("bad").heat_rate["all"].count > 0


def test_pump_marks_heat_delivery_without_a_relay() -> None:
    engine = HeatingEngine(ControlParams())
    for minute in range(181):
        snap = _snapshot(
            T0 + timedelta(minutes=minute),
            rise=minute / 60,
            burner=(minute // 10) % 2 == 0,
            actuator=False,
            relay=None,
        )
        engine.evaluate(replace(snap, pump_on=True))
    assert engine.learner.room("bad").heat_rate["all"].count > 0


def test_observation_mode_still_uses_the_burner() -> None:
    cycling = _run(actuator=False, relay=None, cycle=10)
    assert cycling.learner.room("bad").heat_rate["all"].count == 0
    steady = _run(actuator=False, relay=None, cycle=None)
    assert steady.learner.room("bad").heat_rate["all"].count > 0
