"""Heat network inside Home Assistant: switches, sensors, options and panel data."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.heat_conductor.const import (
    CONF_CO_HEAT_RESERVE,
    DOMAIN,
    NETWORK_DEFAULTS,
)

from .conftest import set_inputs


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return next(s.subentry_id for s in entry.subentries.values() if s.title == "Bad")


async def test_switches_and_room_sensor(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """The heat network starts switched off; rooms with thermostats get their own switch."""
    room_id = await _setup(hass, entry)

    network = _entity_id(hass, "switch", f"{entry.entry_id}_heat_network")
    co_heating = _entity_id(hass, "switch", f"{room_id}_co_heating")
    active = _entity_id(hass, "binary_sensor", f"{room_id}_co_heating_active")
    assert hass.states.get(network).state == "off"
    assert hass.states.get(co_heating).state == "on"
    assert hass.states.get(active).state == "off"

    await hass.services.async_call("switch", "turn_on", {"entity_id": network}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(network).state == "on"
    assert entry.runtime_data.settings.network_enabled

    await hass.services.async_call("switch", "turn_off", {"entity_id": co_heating}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(co_heating).state == "off"
    assert not entry.runtime_data.engine.runtime(room_id).co_heat_enabled
    assert hass.states.get(active).attributes["allowed"] is False


async def test_monitored_rooms_get_no_network_entities(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    bedroom = next(s.subentry_id for s in entry.subentries.values() if s.title == "Schlafzimmer")
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("switch", DOMAIN, f"{bedroom}_co_heating") is None


async def test_options_step(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """The heat network has its own options step and applies without reload."""
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "network" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "network"}
    )
    assert result["type"] is FlowResultType.FORM
    values: dict[str, Any] = {**NETWORK_DEFAULTS, CONF_CO_HEAT_RESERVE: 0.5}
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    params = entry.runtime_data.engine.network_params
    assert params.reserve == 0.5
    assert params.horizon == timedelta(minutes=180)


async def test_panel_data(
    hass: HomeAssistant, entry: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    """State and learning carry the network plan, the heating surface and daily figures."""
    await _setup(hass, entry)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "heat_conductor/state"})
    state = (await client.receive_json())["result"]
    network = state["network"]
    assert network["enabled"] is False
    assert network["blocked"] == "switch_off"
    assert network["sink_needed"] == NETWORK_DEFAULTS["default_sink"]
    assert [r["room_id"] for r in network["rooms"]] == [
        r["room_id"] for r in state["rooms"] if r["kind"] == "regulated"
    ]
    assert any(r["co_heat_enabled"] for r in state["rooms"])

    await client.send_json_auto_id({"type": "heat_conductor/learning"})
    learning = (await client.receive_json())["result"]
    assert learning["network"]["sink"]["learned"] is False
    assert learning["network"]["kpi"]["today"] is not None
    assert "overshoot" in learning["rooms"][0]
