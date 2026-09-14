"""What-if simulation over recorded history."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from tests.ha.conftest import set_inputs


async def test_simulation_with_recorder(
    hass: HomeAssistant, entry: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "heat_conductor/simulate", "values": {"min_run": 40}, "hours": 1}
    )
    response: dict[str, Any] = await client.receive_json()
    assert response["success"], response
    result = response["result"]
    assert result["hours"] == 1
    assert "starts" in result["current"]
    assert result["draft"]["series"]
