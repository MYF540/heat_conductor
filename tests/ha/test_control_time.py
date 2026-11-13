"""Tests for the time handed to the engine."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.heat_conductor.helpers import control_now


async def test_durations_are_right_across_the_autumn_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Berlin goes back from 03:00 CEST to 02:00 CET on 2026-10-25."""
    await hass.config.async_set_time_zone("Europe/Berlin")

    freezer.move_to("2026-10-25 00:50:00+00:00")  # 02:50 CEST
    before, plain_before = control_now(), dt_util.now()
    freezer.move_to("2026-10-25 01:10:00+00:00")  # 02:10 CET
    after, plain_after = control_now(), dt_util.now()

    assert before.hour == after.hour == 2
    assert after - before == timedelta(minutes=20)
    # The plain local time has the bug the helper avoids.
    assert plain_after - plain_before != timedelta(minutes=20)


async def test_durations_are_right_across_the_spring_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Berlin goes forward from 02:00 CET to 03:00 CEST on 2026-03-29."""
    await hass.config.async_set_time_zone("Europe/Berlin")

    freezer.move_to("2026-03-29 00:50:00+00:00")  # 01:50 CET
    before = control_now()
    freezer.move_to("2026-03-29 01:10:00+00:00")  # 03:10 CEST
    after = control_now()

    assert (before.hour, after.hour) == (1, 3)
    assert after - before == timedelta(minutes=20)
    assert before.date() == after.date()
