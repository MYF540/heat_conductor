"""Automatic vacation inside Home Assistant: sensor, attributes and manual end."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_BOILER_SWITCH,
    CONF_CLIMATES,
    CONF_OUTDOOR_SENSORS,
    CONF_PRESENCE,
    CONF_ROOM_KIND,
    CONF_VALVES,
    CONF_WEIGHT,
    DOMAIN,
    PARAMETER_DEFAULTS,
    SUBENTRY_ROOM,
)

from .conftest import CLIMATE_BAD, VALVE_BAD, set_inputs

PERSON = "person.bewohner"


@pytest.fixture
def presence_entry() -> MockConfigEntry:
    """A config entry with a presence entity."""
    options: dict[str, Any] = {
        **PARAMETER_DEFAULTS,
        CONF_OUTDOOR_SENSORS: ["sensor.aussen_temperatur"],
        CONF_BOILER_SWITCH: "switch.kessel",
        CONF_PRESENCE: [PERSON],
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
                    CONF_WEIGHT: 1.0,
                },
                subentry_type=SUBENTRY_ROOM,
                title="Bad",
                unique_id=None,
            ),
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


async def test_vacation_sensor_reports_an_automatic_vacation(
    hass: HomeAssistant, presence_entry: MockConfigEntry
) -> None:
    """The sensor shows where the vacation comes from and can be ended by service."""
    set_inputs(hass)
    hass.states.async_set(PERSON, "not_home")
    await _setup(hass, presence_entry)

    sensor = _entity_id(hass, "binary_sensor", f"{presence_entry.entry_id}_vacation")
    state = hass.states.get(sensor)
    assert state.state == "off"
    assert state.attributes["source"] == "off"
    assert state.attributes["automatic_enabled"] is True

    # The absence timer itself is covered by the core tests.
    coordinator = presence_entry.runtime_data
    coordinator.engine.auto_vacation.active = True
    coordinator.engine.auto_vacation.since = dt_util.now()
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(sensor)
    assert state.state == "on"
    assert state.attributes["source"] == "automatic"
    assert state.attributes["since"] is not None

    await hass.services.async_call(DOMAIN, "clear_vacation", {}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(sensor).state == "off"
    assert coordinator.engine.auto_vacation.active is False


async def test_no_vacation_sensor_without_presence_entities(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Without presence entities the automatic vacation cannot work."""
    set_inputs(hass)
    await _setup(hass, entry)

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_vacation") is None
    )
