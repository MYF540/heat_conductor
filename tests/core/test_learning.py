"""Tests for the online learners."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.heat_conductor.core.learning import (
    BoilerCycleLearner,
    HeatingCurveLearner,
    Learner,
    RoomLearner,
    Stat,
    outdoor_bin,
)

from .helpers import T0


def test_stat_mean_and_usable() -> None:
    stat = Stat()
    for value in (1.0, 2.0, 3.0):
        stat.add(value, T0)
    assert stat.mean == pytest.approx(2.0)
    assert stat.usable()


def test_outdoor_bins() -> None:
    assert outdoor_bin(-3) == "below_0"
    assert outdoor_bin(4.9) == "0_5"
    assert outdoor_bin(12) == "above_10"
    assert outdoor_bin(None) is None


def feed_heating(
    learner: RoomLearner, rate_k_per_h: float, hours: float, outdoor: float = 3.0
) -> None:
    steps = int(hours * 12)
    for i in range(steps + 1):
        learner.update(
            T0 + timedelta(minutes=5 * i),
            temperature=18.0 + rate_k_per_h * (5 * i) / 60,
            outdoor=outdoor,
            valve=0.8,
            heating=True,
            window_open=False,
        )


def test_heat_rate_is_learned_per_band() -> None:
    learner = RoomLearner()
    feed_heating(learner, 1.2, hours=2.5)
    assert learner.heat_rate["all"].count >= 3
    assert learner.heat_rate_for(3.0) == pytest.approx(1.2, rel=0.01)
    assert learner.heat_points


def test_heating_with_open_window_is_ignored() -> None:
    learner = RoomLearner()
    for i in range(40):
        learner.update(
            T0 + timedelta(minutes=5 * i),
            temperature=18.0 + 0.1 * i,
            outdoor=3.0,
            valve=0.8,
            heating=True,
            window_open=True,
        )
    assert learner.heat_rate["all"].count == 0


def test_cooling_time_constant() -> None:
    learner = RoomLearner()
    # delta 16 K, slope -0.4 K/h -> tau 40 h
    for i in range(3 * 12 + 1):
        minutes = 5 * i
        learner.update(
            T0 + timedelta(minutes=minutes),
            temperature=20.0 - 0.4 * minutes / 60,
            outdoor=4.0,
            valve=0.0,
            heating=False,
            window_open=False,
        )
    assert learner.cooling_tau.count >= 2
    assert learner.cooling_tau.mean == pytest.approx(40, rel=0.1)


def test_dead_time() -> None:
    learner = RoomLearner()
    learner.update(T0, temperature=18.0, outdoor=3.0, valve=0.0, heating=True, window_open=False)
    learner.update(
        T0 + timedelta(minutes=5),
        temperature=18.0,
        outdoor=3.0,
        valve=0.9,
        heating=True,
        window_open=False,
    )
    learner.update(
        T0 + timedelta(minutes=10),
        temperature=18.1,
        outdoor=3.0,
        valve=0.9,
        heating=True,
        window_open=False,
    )
    learner.update(
        T0 + timedelta(minutes=25),
        temperature=18.3,
        outdoor=3.0,
        valve=0.9,
        heating=True,
        window_open=False,
    )
    assert learner.dead_time.count == 1
    assert learner.dead_time.mean == pytest.approx(20.0)


def test_boiler_cycles() -> None:
    learner = BoilerCycleLearner()
    learner.update(T0, False, 3.0)
    learner.update(T0 + timedelta(minutes=10), True, 3.0)  # first phase length unknown
    learner.update(T0 + timedelta(minutes=35), False, 3.0)  # 25 min run
    learner.update(T0 + timedelta(minutes=50), True, 3.0)  # 15 min pause
    assert learner.runs["all"].mean == pytest.approx(25)
    assert learner.pauses["all"].mean == pytest.approx(15)
    assert learner.run_histogram[3] == 1  # 20-40 min
    assert learner.pause_histogram[2] == 1  # 10-20 min


def test_heating_curve_fit() -> None:
    learner = HeatingCurveLearner()
    for i in range(30):
        outdoor = -10 + i
        learner.update(T0 + timedelta(minutes=10 * i), outdoor, 50.0 - 1.2 * outdoor)
    slope, intercept = learner.fit()
    assert slope == pytest.approx(-1.2, rel=0.01)
    assert intercept == pytest.approx(50.0, rel=0.01)


def test_learner_roundtrip_and_reset() -> None:
    learner = Learner()
    feed_heating(learner.room("bad"), 1.0, hours=2.5)
    restored = Learner.from_dict(learner.to_dict())
    assert restored.room("bad").heat_rate["all"].count == learner.room("bad").heat_rate["all"].count
    summary = restored.summary({"bad": "Bad"})
    assert summary["rooms"][0]["name"] == "Bad"
    restored.reset("bad")
    assert "bad" not in restored.rooms
