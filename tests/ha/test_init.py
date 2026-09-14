"""Setup, entities and control behaviour inside Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.heat_conductor.const import DOMAIN

from .conftest import BOILER, set_inputs


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_entities_and_observes(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    set_inputs(hass)
    turn_on = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    heat_request = _entity_id(hass, "binary_sensor", f"{entry.entry_id}_heat_request")
    reason = _entity_id(hass, "sensor", f"{entry.entry_id}_decision_reason")
    demand = _entity_id(hass, "sensor", f"{entry.entry_id}_total_demand")
    observation = _entity_id(hass, "switch", f"{entry.entry_id}_observation_mode")

    assert hass.states.get(heat_request).state == "on"
    assert hass.states.get(reason).state == "deficit_start"
    assert float(hass.states.get(demand).state) == 100.0
    assert hass.states.get(observation).state == "on"
    # Observation mode never touches the relay.
    assert turn_on == []

    rooms = {s.title: s.subentry_id for s in entry.subentries.values()}
    bedroom_temp = _entity_id(hass, "sensor", f"{rooms['Schlafzimmer']}_room_temperature")
    assert float(hass.states.get(bedroom_temp).state) == 17.0
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{rooms['Schlafzimmer']}_room_demand")
        is None
    )


async def test_relay_is_switched_when_observation_is_off(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    set_inputs(hass)
    turn_on = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)

    observation = _entity_id(hass, "switch", f"{entry.entry_id}_observation_mode")
    await hass.services.async_call("switch", "turn_off", {"entity_id": observation}, blocking=True)
    await hass.async_block_till_done()

    assert len(turn_on) == 1
    assert turn_on[0].data["entity_id"] == BOILER


async def test_missing_data_leads_to_failsafe(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    coordinator = entry.runtime_data

    hass.states.async_set("climate.bad", "unavailable")
    hass.states.async_set("sensor.bad_heating", "unavailable")
    freezer.tick(timedelta(minutes=3))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = _entity_id(hass, "sensor", f"{entry.entry_id}_boiler_state")
    problem = _entity_id(hass, "binary_sensor", f"{entry.entry_id}_problem")
    assert hass.states.get(state).state == "failsafe"
    assert hass.states.get(problem).state == "on"


async def test_mode_is_persisted_across_reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    mode = _entity_id(hass, "select", f"{entry.entry_id}_operating_mode")

    await hass.services.async_call(
        "select", "select_option", {"entity_id": mode, "option": "off"}, blocking=True
    )
    assert hass.states.get(mode).state == "off"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(mode).state == "off"


async def test_unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
