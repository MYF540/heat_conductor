"""Config flow, options flow and room subentry flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_CLIMATES,
    CONF_MIN_RUN,
    CONF_OUTDOOR_SENSORS,
    CONF_ROOM_KIND,
    CONF_VALVES,
    CONF_WEIGHT,
    DOMAIN,
    PARAMETER_DEFAULTS,
    SUBENTRY_ROOM,
)

from .conftest import CLIMATE_BAD, OUTDOOR, VALVE_BAD, set_inputs


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Heizung", CONF_OUTDOOR_SENSORS: []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "outdoor_required"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Heizung", CONF_OUTDOOR_SENSORS: [OUTDOOR]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Heizung"
    options = result["result"].options
    assert options[CONF_OUTDOOR_SENSORS] == [OUTDOOR]
    assert options[CONF_MIN_RUN] == PARAMETER_DEFAULTS[CONF_MIN_RUN]


async def test_single_instance(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_room_subentry_flow(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_ROOM), context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Küche", CONF_ROOM_KIND: "regulated", CONF_WEIGHT: 1.0}
    )
    assert result["errors"] == {"base": "regulated_needs_inputs"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Küche",
            CONF_ROOM_KIND: "regulated",
            CONF_CLIMATES: [CLIMATE_BAD],
            CONF_VALVES: [VALVE_BAD],
            CONF_WEIGHT: 1.5,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    kitchen = next(s for s in entry.subentries.values() if s.title == "Küche")
    assert kitchen.data[CONF_WEIGHT] == 1.5
    assert any(r.name == "Küche" for r in entry.runtime_data.rooms)


async def test_options_parameters(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "parameters"}
    )
    assert result["type"] is FlowResultType.FORM

    params = {**PARAMETER_DEFAULTS, CONF_MIN_RUN: 30}
    result = await hass.config_entries.options.async_configure(result["flow_id"], params)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_MIN_RUN] == 30
    assert entry.options[CONF_OUTDOOR_SENSORS] == [OUTDOOR]
    assert entry.runtime_data.params.min_run.total_seconds() == 30 * 60
