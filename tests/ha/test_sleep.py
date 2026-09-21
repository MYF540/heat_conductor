"""Night setback inside Home Assistant: options, sensor and setpoints."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_SLEEP_CONFIRM,
    CONF_SLEEP_SENSOR,
    DOMAIN,
)

from .conftest import set_inputs

BED = "binary_sensor.bett_belegt"


@pytest.fixture
def night_entry(entry: MockConfigEntry) -> MockConfigEntry:
    """The standard entry with a night window and a sleep sensor."""
    options: dict[str, Any] = {
        **entry.options,
        CONF_SLEEP_SENSOR: BED,
        CONF_NIGHT_START: "23:00",
        CONF_NIGHT_END: "06:30",
        CONF_SLEEP_CONFIRM: 0,  # no confirmation time, so the tests see it immediately
    }
    return MockConfigEntry(
        domain=DOMAIN,
        title=entry.title,
        data={},
        options=options,
        unique_id=DOMAIN,
        subentries_data=[
            {
                "data": dict(s.data),
                "subentry_type": s.subentry_type,
                "title": s.title,
                "unique_id": s.unique_id,
            }
            for s in entry.subentries.values()
        ],
    )


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sleep_sensor_sets_the_rooms_back(
    hass: HomeAssistant, night_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """The bed sensor switches the night setback on and off."""
    # The night window is read in local time, so pin both.
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-01-15 12:00:00+00:00")  # midday, outside the night window
    set_inputs(hass)
    hass.states.async_set(BED, "off")
    await _setup(hass, night_entry)

    sleeping = _entity_id(hass, "binary_sensor", f"{night_entry.entry_id}_sleep")
    room_id = next(s.subentry_id for s in night_entry.subentries.values() if s.title == "Bad")
    climate = _entity_id(hass, "climate", f"{room_id}_room_climate")
    assert hass.states.get(sleeping).state == "off"

    hass.states.async_set(BED, "on")
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(sleeping)
    assert state.state == "on"
    assert state.attributes["source"] == "sensor"
    assert hass.states.get(climate).attributes["source"] == "sleep"
    assert hass.states.get(climate).attributes["temperature"] == 18.0  # default eco

    hass.states.async_set(BED, "off")
    await night_entry.runtime_data.async_refresh()  # starts the wake-up timer
    assert hass.states.get(sleeping).state == "on"  # still within the wake-up time

    freezer.tick(timedelta(minutes=20))
    await night_entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(sleeping).state == "off"
    assert hass.states.get(climate).attributes["source"] != "sleep"


async def test_night_window_without_a_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """A night window alone is enough and creates the entity."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-01-15 23:30:00+00:00")
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_NIGHT_START: "23:00", CONF_NIGHT_END: "06:30"}
    )
    set_inputs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sleeping = _entity_id(hass, "binary_sensor", f"{entry.entry_id}_sleep")
    state = hass.states.get(sleeping)
    assert state.state == "on"
    assert state.attributes["source"] == "window"


async def test_no_sleep_entity_without_window_and_sensor(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Without a night window and without a sensor nothing changes."""
    set_inputs(hass)
    await _setup(hass, entry)

    registry = er.async_get(hass)
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_sleep") is None
