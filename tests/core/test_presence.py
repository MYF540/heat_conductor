"""Tests for the learned presence schedule."""

from __future__ import annotations

from datetime import timedelta

from custom_components.heat_conductor.core.presence import (
    MIN_DAYS,
    SAMPLE_INTERVAL,
    PresenceLearner,
)

from .helpers import T0

# A working week: at home before 08:00 and from 17:00, away in between.
AWAY_FROM = 8
AWAY_UNTIL = 17


def _at_home(moment) -> bool:  # type: ignore[no-untyped-def]
    return not (AWAY_FROM <= moment.hour < AWAY_UNTIL)


def _feed(learner: PresenceLearner, days: int, start=T0) -> None:  # type: ignore[no-untyped-def]
    moment = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = moment + timedelta(days=days)
    while moment < end:
        learner.update(moment, _at_home(moment))
        moment += SAMPLE_INTERVAL


def test_not_ready_before_enough_days() -> None:
    """Without two weeks of data there is no suggestion."""
    learner = PresenceLearner()
    _feed(learner, days=3)
    assert not learner.ready
    assert learner.schedule_state(T0) == (None, None)


def test_learns_daily_pattern() -> None:
    """The suggested windows follow the observed presence."""
    learner = PresenceLearner()
    _feed(learner, days=MIN_DAYS + 1)
    assert learner.ready

    for day in learner.windows():
        assert day == [(0, AWAY_FROM * 60), (AWAY_UNTIL * 60, 24 * 60)]


def test_schedule_state_follows_the_windows() -> None:
    """Comfort while at home, otherwise the next start is reported."""
    learner = PresenceLearner()
    _feed(learner, days=MIN_DAYS + 1)
    start = T0.replace(hour=0, minute=0, second=0, microsecond=0)

    morning = start + timedelta(days=MIN_DAYS, hours=7)
    assert learner.schedule_state(morning) == (True, None)

    midday = start + timedelta(days=MIN_DAYS, hours=12)
    on, next_on = learner.schedule_state(midday)
    assert on is False
    assert next_on == midday.replace(hour=AWAY_UNTIL, minute=0)


def test_ignores_missing_presence_information() -> None:
    """Without presence entities nothing is learned."""
    learner = PresenceLearner()
    moment = T0
    for _ in range(100):
        learner.update(moment, None)
        moment += SAMPLE_INTERVAL
    assert learner.days_observed == 0
    assert not learner.ready


def test_decimates_to_the_sample_interval() -> None:
    """Observations closer than the sample interval are skipped."""
    learner = PresenceLearner()
    learner.update(T0, True)
    learner.update(T0 + timedelta(seconds=30), False)
    day, slot = T0.weekday(), (T0.hour * 60 + T0.minute) // 30
    assert learner.counts[day][slot] == 1
    assert learner.grid[day][slot] == 1.0


def test_survives_a_restart() -> None:
    """Grid, counts and observed days are persisted."""
    learner = PresenceLearner()
    _feed(learner, days=MIN_DAYS + 1)
    restored = PresenceLearner.from_dict(learner.to_dict())

    assert restored.days_observed == learner.days_observed
    assert restored.ready
    assert restored.windows() == learner.windows()


def test_restores_nothing_from_broken_data() -> None:
    """A damaged store falls back to an empty learner."""
    restored = PresenceLearner.from_dict({"grid": "nonsense", "counts": None})
    assert not restored.ready
    assert restored.days_observed == 0
