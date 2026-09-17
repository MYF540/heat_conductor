"""Usage based heating inside Home Assistant: activity entities, switch and sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_BOILER_SWITCH,
    CONF_CLIMATES,
    CONF_OUTDOOR_SENSORS,
    CONF_ROOM_KIND,
    CONF_USAGE_ENTITIES,
    CONF_USAGE_HOLD,
    CONF_VALVES,
    CONF_WEIGHT,
    DOMAIN,
    PARAMETER_DEFAULTS,
    SUBENTRY_ROOM,
)

from .conftest import CLIMATE_BAD, VALVE_BAD, set_inputs

TV = "media_player.wohnzimmer_tv"


@pytest.fixture
def usage_entry() -> MockConfigEntry:
    """A config entry with one room whose usage is detected by a media player."""
    options: dict[str, Any] = {
        **PARAMETER_DEFAULTS,
        CONF_OUTDOOR_SENSORS: ["sensor.aussen_temperatur"],
        CONF_BOILER_SWITCH: "switch.kessel",
        CONF_USAGE_HOLD: 0,  # no hold time, so the tests see changes immediately
    }
    return MockConfigEntry(
        domain=DOMAIN,
        title="HeatConductor",
        data={},
        options=options,
        unique_id=DOMAIN,
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_ROOM_KIND: "regulated",
                    CONF_CLIMATES: [CLIMATE_BAD],
                    CONF_VALVES: [VALVE_BAD],
                    CONF_USAGE_ENTITIES: [TV],
                    CONF_WEIGHT: 1.0,
                },
                subentry_type=SUBENTRY_ROOM,
                title="Wohnzimmer",
                unique_id=None,
            ),
        ],
    )


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return next(iter(entry.subentries))


async def test_room_follows_its_activity_entities(
    hass: HomeAssistant, usage_entry: MockConfigEntry
) -> None:
    """The room is heated to comfort while the TV runs and to eco afterwards."""
    set_inputs(hass)
    hass.states.async_set(TV, "playing")
    room_id = await _setup(hass, usage_entry)

    climate = _entity_id(hass, "climate", f"{room_id}_room_climate")
    in_use = _entity_id(hass, "binary_sensor", f"{room_id}_room_in_use")

    assert hass.states.get(in_use).state == "on"
    state = hass.states.get(climate)
    assert state.attributes["source"] == "usage_active"
    assert state.attributes["temperature"] == 21.0

    hass.states.async_set(TV, "off")
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(in_use).state == "off"
    state = hass.states.get(climate)
    assert state.attributes["source"] == "usage_idle"
    assert state.attributes["temperature"] == 18.0


async def test_standby_does_not_count_as_usage(
    hass: HomeAssistant, usage_entry: MockConfigEntry
) -> None:
    """An idle media player leaves the room unused."""
    set_inputs(hass)
    hass.states.async_set(TV, "idle")
    room_id = await _setup(hass, usage_entry)

    assert (
        hass.states.get(_entity_id(hass, "binary_sensor", f"{room_id}_room_in_use")).state == "off"
    )


async def test_detection_can_be_switched_off_per_room(
    hass: HomeAssistant, usage_entry: MockConfigEntry
) -> None:
    """With the switch off the room ignores the TV again."""
    set_inputs(hass)
    hass.states.async_set(TV, "off")
    room_id = await _setup(hass, usage_entry)

    switch = _entity_id(hass, "switch", f"{room_id}_usage_detection")
    assert hass.states.get(switch).state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)

    climate = _entity_id(hass, "climate", f"{room_id}_room_climate")
    assert hass.states.get(climate).attributes["source"] == "no_schedule"
    assert hass.states.get(climate).attributes["temperature"] == 21.0
    in_use = _entity_id(hass, "binary_sensor", f"{room_id}_room_in_use")
    assert hass.states.get(in_use).state == "unknown"


async def test_rooms_without_activity_entities_have_no_usage_entities(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Rooms that do not configure activity entities stay as they were."""
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    room_id = next(s.subentry_id for s in entry.subentries.values() if s.title == "Bad")
    assert registry.async_get_entity_id("switch", DOMAIN, f"{room_id}_usage_detection") is None
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, f"{room_id}_room_in_use") is None


async def test_learned_schedule_switch_is_off_by_default(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The learned schedule only applies after the user switches it on."""
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    switch = _entity_id(hass, "switch", f"{entry.entry_id}_learned_schedule")
    assert hass.states.get(switch).state == "off"

    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(switch).state == "on"
    assert entry.runtime_data.settings.learned_schedule_enabled is True
