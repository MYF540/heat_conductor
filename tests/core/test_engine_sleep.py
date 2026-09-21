"""Night setback inside the engine pipeline."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from custom_components.heat_conductor.core.engine import HeatingEngine
from custom_components.heat_conductor.core.models import ControlParams
from custom_components.heat_conductor.core.setpoint import SetpointSource
from custom_components.heat_conductor.core.sleep import SleepParams, SleepSource

from .helpers import T0
from .test_engine_vacation import snapshot

MIDNIGHT = T0.replace(hour=0, minute=0, second=0, microsecond=0)

NIGHT = SleepParams(window_start=23 * 60, window_end=6 * 60 + 30)


def test_night_window_sets_the_rooms_back() -> None:
    """Inside the night window every room follows its eco temperature."""
    engine = HeatingEngine(ControlParams(), sleep_params=NIGHT)
    engine.runtime("bad").comfort, engine.runtime("bad").eco = 21.0, 18.0

    evening = engine.evaluate(snapshot(MIDNIGHT + timedelta(hours=22), present=True))
    assert evening.setpoint("bad").source is not SetpointSource.SLEEP
    assert not evening.sleep.sleeping

    night = engine.evaluate(snapshot(MIDNIGHT + timedelta(hours=23, minutes=30), present=True))
    assert night.sleep.sleeping
    assert night.sleep.source is SleepSource.WINDOW
    assert night.setpoint("bad").source is SetpointSource.SLEEP
    assert night.setpoint("bad").target == 18.0


def test_sleep_sensor_teaches_the_night_pattern() -> None:
    """Only the sensor trains the learned night window."""
    engine = HeatingEngine(ControlParams(), sleep_params=NIGHT)
    moment = MIDNIGHT + timedelta(hours=23)
    for _ in range(40):  # a bit over three hours
        engine.evaluate(replace(snapshot(moment, present=True), sleep_sensor=True))
        moment += timedelta(minutes=5)

    pattern = engine.learner.night
    assert pattern.days_observed >= 1
    day, _slot = MIDNIGHT.weekday(), 0
    assert max(pattern.grid[day]) > 0.5


def test_windows_alone_teach_nothing() -> None:
    """Without a sensor the night pattern stays empty."""
    engine = HeatingEngine(ControlParams(), sleep_params=NIGHT)
    moment = MIDNIGHT + timedelta(hours=23)
    for _ in range(40):
        engine.evaluate(snapshot(moment, present=True))
        moment += timedelta(minutes=5)

    assert engine.learner.night.days_observed == 0
    assert max(max(day) for day in engine.learner.night.grid) == 0.0


def test_no_night_learning_during_a_vacation() -> None:
    """A vacation says nothing about everyday nights."""
    engine = HeatingEngine(ControlParams(), sleep_params=NIGHT)
    moment = T0
    for _ in range(40):
        engine.evaluate(
            replace(snapshot(moment, present=True), sleep_sensor=True, vacation_active=True)
        )
        moment += timedelta(minutes=5)
    assert engine.learner.night.days_observed == 0
