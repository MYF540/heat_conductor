"""Rooms without their own schedule may follow the learned presence schedule."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.heat_conductor.core.engine import (
    EngineSnapshot,
    HeatingEngine,
    RoomControlInput,
)
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode
from custom_components.heat_conductor.core.presence import MIN_DAYS, SAMPLE_INTERVAL
from custom_components.heat_conductor.core.setpoint import SetpointSource, TrvInput

from .helpers import T0, fresh, room

MIDNIGHT = T0.replace(hour=0, minute=0, second=0, microsecond=0)
AWAY_FROM, AWAY_UNTIL = 8, 17


def snapshot(now: datetime, *, learned: bool, schedule_on: bool | None = None) -> EngineSnapshot:
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
        learned_schedule_enabled=learned,
        present=True,
        room_controls=(
            RoomControlInput(
                room_id="bad",
                schedule_on=schedule_on,
                trvs=(TrvInput("climate.bad", True, 20.0, 20.0, "heat"),),
            ),
        ),
    )


def _train(engine: HeatingEngine) -> None:
    """Two weeks of presence: at home except between 08:00 and 17:00."""
    moment = MIDNIGHT - timedelta(days=MIN_DAYS + 1)
    while moment < MIDNIGHT:
        engine.learner.presence.update(moment, not AWAY_FROM <= moment.hour < AWAY_UNTIL)
        moment += SAMPLE_INTERVAL


def test_learned_schedule_sets_comfort_and_eco() -> None:
    """A room without a schedule helper follows the learned windows."""
    engine = HeatingEngine(ControlParams())
    _train(engine)

    at_home = engine.evaluate(snapshot(MIDNIGHT + timedelta(hours=19), learned=True))
    assert at_home.setpoint("bad").source is SetpointSource.SCHEDULE_COMFORT
    assert at_home.learned_schedule_on is True

    away = engine.evaluate(snapshot(MIDNIGHT + timedelta(hours=12), learned=True))
    assert away.setpoint("bad").source is SetpointSource.SCHEDULE_ECO
    assert away.learned_schedule_on is False


def test_learned_schedule_is_only_used_when_enabled() -> None:
    """Switched off, a room without a schedule stays on comfort."""
    engine = HeatingEngine(ControlParams())
    _train(engine)
    result = engine.evaluate(snapshot(MIDNIGHT + timedelta(hours=12), learned=False))
    assert result.setpoint("bad").source is SetpointSource.NO_SCHEDULE
    assert result.learned_schedule_on is None


def test_own_schedule_wins_over_the_learned_one() -> None:
    """A configured schedule helper is never overruled."""
    engine = HeatingEngine(ControlParams())
    _train(engine)
    result = engine.evaluate(
        snapshot(MIDNIGHT + timedelta(hours=12), learned=True, schedule_on=True)
    )
    assert result.setpoint("bad").source is SetpointSource.SCHEDULE_COMFORT


def test_learning_needs_data_before_it_changes_anything() -> None:
    """Without enough observed days the rooms keep their previous behaviour."""
    engine = HeatingEngine(ControlParams())
    result = engine.evaluate(snapshot(MIDNIGHT + timedelta(hours=12), learned=True))
    assert result.setpoint("bad").source is SetpointSource.NO_SCHEDULE
    assert result.learned_schedule_on is None
