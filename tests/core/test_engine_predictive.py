"""Predictive presence: the learned pattern predicts, actual presence confirms."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from custom_components.heat_conductor.core.engine import (
    EngineSnapshot,
    HeatingEngine,
    RoomControlInput,
)
from custom_components.heat_conductor.core.models import ControlParams, OperatingMode
from custom_components.heat_conductor.core.presence import MIN_DAYS, SAMPLE_INTERVAL
from custom_components.heat_conductor.core.setpoint import SetpointSource, TrvInput
from custom_components.heat_conductor.core.sleep import SleepParams

from .helpers import T0, fresh, room

MIDNIGHT = T0.replace(hour=0, minute=0, second=0, microsecond=0)
AWAY_FROM, AWAY_UNTIL = 8, 17  # nobody home between 08:00 and 17:00


def snapshot(
    now: datetime,
    *,
    present: bool | None,
    predictive: bool = True,
    schedule_on: bool | None = None,
) -> EngineSnapshot:
    return EngineSnapshot(
        now=now,
        rooms=(
            room(
                "Bad",
                room_temperature=fresh(19.0, now),
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
        learned_schedule_enabled=predictive,
        present=present,
        room_controls=(
            RoomControlInput(
                room_id="bad",
                schedule_on=schedule_on,
                trvs=(TrvInput("climate.bad", True, 20.0, 19.0, "heat"),),
            ),
        ),
    )


def trained(**kwargs) -> HeatingEngine:  # type: ignore[no-untyped-def]
    """Two weeks at home except between 08:00 and 17:00."""
    engine = HeatingEngine(ControlParams(), **kwargs)
    moment = MIDNIGHT - timedelta(days=MIN_DAYS + 1)
    while moment < MIDNIGHT:
        engine.learner.presence.update(moment, not AWAY_FROM <= moment.hour < AWAY_UNTIL)
        moment += SAMPLE_INTERVAL
    return engine


def at(hour: float) -> datetime:
    return MIDNIGHT + timedelta(hours=hour)


@pytest.mark.parametrize(
    ("hour", "present", "source", "occupancy"),
    [
        (12.0, True, SetpointSource.PRESENT, "present"),  # came home early
        (12.0, False, SetpointSource.ABSENT, "away"),  # nobody expected
        (16.25, False, SetpointSource.ARRIVAL_EXPECTED, "expected"),  # preheat for 17:00
        (17.5, False, SetpointSource.ARRIVAL_EXPECTED, "expected"),  # waiting for the arrival
        (17.9, False, SetpointSource.ABSENT, "away"),  # nobody came: back to standby
    ],
)
def test_prediction_and_confirmation(
    hour: float, present: bool, source: SetpointSource, occupancy: str
) -> None:
    """Preheat before the expected arrival, heat on arrival, stand by if nobody comes."""
    engine = trained()
    result = engine.evaluate(snapshot(at(hour), present=present))
    assert result.setpoint("bad").source is source
    assert result.occupancy == occupancy


def test_next_arrival_is_reported() -> None:
    """The panel shows when somebody is expected next."""
    result = trained().evaluate(snapshot(at(12.0), present=False))
    assert result.next_arrival == at(AWAY_UNTIL)


def test_learned_heat_up_rate_sets_the_preheat_lead() -> None:
    """A slow room starts earlier than the default preheat time."""
    engine = trained()
    learner = engine.learner.room("bad")
    for _ in range(5):
        learner.heat_rate["all"].add(0.5, at(0))  # K/h
    engine.runtime("bad").comfort = 21.0
    # 2 K missing at 0.5 K/h -> about 5 h with the safety margin, capped at 3 h.
    early = engine.evaluate(snapshot(at(14.5), present=False))
    assert early.setpoint("bad").source is SetpointSource.ARRIVAL_EXPECTED


def test_switched_off_keeps_the_simple_rules() -> None:
    """Without predictive presence: somebody home means comfort, nobody means eco."""
    engine = trained()
    assert (
        engine.evaluate(snapshot(at(16.25), present=False, predictive=False)).setpoint("bad").source
        is SetpointSource.ABSENT
    )
    assert (
        engine.evaluate(snapshot(at(12.0), present=True, predictive=False)).setpoint("bad").source
        is SetpointSource.NO_SCHEDULE
    )


def test_own_schedule_helper_wins() -> None:
    """A configured schedule helper stays a fixed rule for its room."""
    result = trained().evaluate(snapshot(at(12.0), present=True, schedule_on=False))
    assert result.setpoint("bad").source is SetpointSource.SCHEDULE_ECO


def test_without_enough_data_presence_alone_decides() -> None:
    """Before the pattern is learned there is no prediction."""
    engine = HeatingEngine(ControlParams())
    assert (
        engine.evaluate(snapshot(at(16.25), present=False)).setpoint("bad").source
        is SetpointSource.ABSENT
    )
    assert (
        engine.evaluate(snapshot(at(12.0), present=True)).setpoint("bad").source
        is SetpointSource.PRESENT
    )


def test_warm_up_before_the_night_ends() -> None:
    """The end of the night window is known, so rooms are warm when people get up."""
    engine = trained(sleep_params=SleepParams(window_start=23 * 60, window_end=6 * 60 + 30))
    night = engine.evaluate(snapshot(at(3.0), present=True))
    assert night.setpoint("bad").source is SetpointSource.SLEEP
    morning = engine.evaluate(snapshot(at(5.75), present=True))
    assert morning.setpoint("bad").source is SetpointSource.WAKE_PREHEAT
    assert morning.sleep.sleeping  # still night for learning and the entity
    later = engine.evaluate(replace(snapshot(at(7.0), present=True)))
    assert later.setpoint("bad").source is SetpointSource.PRESENT
