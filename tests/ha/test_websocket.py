"""WebSocket API of the panel."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from .conftest import set_inputs


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _call(client: Any, message: dict[str, Any]) -> dict[str, Any]:
    await client.send_json_auto_id(message)
    return await client.receive_json()


async def test_state_params_and_learning(
    hass: HomeAssistant, entry: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    await _setup(hass, entry)
    client = await hass_ws_client(hass)

    state = await _call(client, {"type": "heat_conductor/state"})
    assert state["success"]
    result = state["result"]
    assert result["loaded"]
    assert result["decision"]["reason"] == "deficit_start"
    assert {room["name"] for room in result["rooms"]} == {"Bad", "Schlafzimmer"}
    assert "total_demand" in result["history_entities"]

    params = await _call(client, {"type": "heat_conductor/params"})
    assert params["success"]
    keys = {p["key"] for p in params["result"]["params"]}
    assert {"min_run", "calorific_value", "default_comfort", "optimum_start"} <= keys
    assert params["result"]["can_edit"]

    learning = await _call(client, {"type": "heat_conductor/learning"})
    assert learning["success"]
    assert learning["result"]["rooms"][0]["name"] == "Bad"
    advice = learning["result"]["curve_advice"]
    assert advice["ready"] is False
    assert advice["target_valve"] == 0.85
    assert advice["curve_setting"] is None


async def test_admin_can_set_and_reset_params(
    hass: HomeAssistant, entry: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    await _setup(hass, entry)
    client = await hass_ws_client(hass)

    invalid = await _call(client, {"type": "heat_conductor/params/set", "values": {"min_run": 999}})
    assert not invalid["success"]

    ok = await _call(client, {"type": "heat_conductor/params/set", "values": {"min_run": 30}})
    assert ok["success"]
    await hass.async_block_till_done()
    assert entry.options["min_run"] == 30.0

    log = await _call(client, {"type": "heat_conductor/changelog"})
    assert log["result"]["entries"][0]["key"] == "min_run"

    reset = await _call(client, {"type": "heat_conductor/params/reset", "keys": ["min_run"]})
    assert reset["success"]
    await hass.async_block_till_done()
    assert entry.options["min_run"] == 20


async def test_non_admin_cannot_change(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_user: MockUser,
    hass_read_only_access_token: str,
) -> None:
    await _setup(hass, entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)

    state = await _call(client, {"type": "heat_conductor/state"})
    assert state["success"]
    params = await _call(client, {"type": "heat_conductor/params"})
    assert not params["result"]["can_edit"]

    denied = await _call(client, {"type": "heat_conductor/params/set", "values": {"min_run": 30}})
    assert not denied["success"]
    assert denied["error"]["code"] == "unauthorized"
    denied = await _call(client, {"type": "heat_conductor/learning/reset"})
    assert not denied["success"]
