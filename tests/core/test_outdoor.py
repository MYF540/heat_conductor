"""Tests for outdoor temperature fusion."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.heat_conductor.core.outdoor import ExponentialSmoother, fuse_outdoor

from .helpers import T0, fresh, old

AGE = timedelta(hours=4)


def test_two_close_sensors_are_averaged() -> None:
    result = fuse_outdoor((fresh(4.0), fresh(5.0)), None, T0, AGE, 2.0)
    assert result.value == pytest.approx(4.5)
    assert result.sensors_used == 2


def test_sun_exposed_sensor_is_ignored() -> None:
    result = fuse_outdoor((fresh(4.0), fresh(12.0)), None, T0, AGE, 2.0)
    assert result.value == 4.0


def test_median_of_three() -> None:
    result = fuse_outdoor((fresh(3.0), fresh(4.0), fresh(30.0)), None, T0, AGE, 2.0)
    assert result.value == 4.0


def test_weather_fallback_and_implausible_values() -> None:
    result = fuse_outdoor((old(3.0), fresh(-80.0)), fresh(7.0), T0, AGE, 2.0)
    assert result.value == 7.0
    assert result.source == "weather"


def test_nothing_available() -> None:
    result = fuse_outdoor((), None, T0, AGE, 2.0)
    assert result.value is None


def test_smoother_moves_towards_new_value() -> None:
    smoother = ExponentialSmoother(timedelta(hours=24))
    assert smoother.update(10.0, T0) == 10.0
    after_day = smoother.update(0.0, T0 + timedelta(hours=24))
    assert after_day == pytest.approx(10.0 * 0.3679, abs=0.01)
    assert smoother.update(None, T0 + timedelta(hours=25)) == after_day
