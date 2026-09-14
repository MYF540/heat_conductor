"""Room control, virtual thermostats, numbers and services inside Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.heat_conductor.const import CONF_WATCHDOG_URL, DOMAIN

from .conftest import CLIMATE_BAD, set_inputs


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _room_id(entry: MockConfigEntry, title: str = "Bad") -> str:
    return next(s.subentry_id for s in entry.subentries.values() if s.title == title)


async def test_room_control_is_off_by_default_and_writes_when_enabled(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    set_inputs(hass, target=18.0)
    await _setup(hass, entry)
    # Registered after setup: loading the climate platform replaces earlier mocks.
    set_temperature = async_mock_service(hass, "climate", "set_temperature")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert set_temperature == []

    switch = _entity_id(hass, "switch", f"{entry.entry_id}_room_control")
    assert hass.states.get(switch).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(set_temperature) == 1
    assert set_temperature[0].data["entity_id"] == CLIMATE_BAD
    assert set_temperature[0].data["temperature"] == 21.0  # default comfort, no room sensor


async def test_virtual_thermostat_override_and_numbers(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    room_id = _room_id(entry)
    climate = _entity_id(hass, "climate", f"{room_id}_room_climate")
    comfort = _entity_id(hass, "number", f"{room_id}_comfort_temperature")

    state = hass.states.get(climate)
    assert state.state == "heat"
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["source"] == "no_schedule"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": comfort, "value": 22.5}, blocking=True
    )
    assert hass.states.get(climate).attributes["temperature"] == 22.5

    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": climate, "temperature": 19.0}, blocking=True
    )
    state = hass.states.get(climate)
    assert state.attributes["temperature"] == 19.0
    assert state.attributes["source"] == "override"

    await hass.services.async_call(DOMAIN, "clear_override", {"entity_id": climate}, blocking=True)
    assert hass.states.get(climate).attributes["source"] == "no_schedule"

    await hass.services.async_call(
        DOMAIN, "boost", {"entity_id": climate, "duration": {"minutes": 10}}, blocking=True
    )
    assert hass.states.get(climate).attributes["preset_mode"] == "boost"

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"}, blocking=True
    )
    state = hass.states.get(climate)
    assert state.state == "off"
    assert state.attributes["temperature"] == 7.0


async def test_vacation_service(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    climate = _entity_id(hass, "climate", f"{_room_id(entry)}_room_climate")
    end = dt_util.now() + timedelta(days=3)

    await hass.services.async_call(
        DOMAIN, "set_vacation", {"end": end.isoformat(), "temperature": 14.0}, blocking=True
    )
    state = hass.states.get(climate)
    assert state.attributes["source"] == "vacation"
    assert state.attributes["temperature"] == 14.0

    await hass.services.async_call(DOMAIN, "clear_vacation", {}, blocking=True)
    assert hass.states.get(climate).attributes["source"] == "no_schedule"


async def test_reset_learning_unknown_room(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "reset_learning", {}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "reset_learning", {"room": "Nirgendwo"}, blocking=True
        )


async def test_parameter_change_applies_without_reload(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    await coordinator.async_set_params({"min_run": 35.0}, "tester")
    await hass.async_block_till_done()
    assert entry.runtime_data is coordinator  # no reload
    assert coordinator.params.min_run == timedelta(minutes=35)
    assert coordinator.engine.boiler.params.min_run == timedelta(minutes=35)
    assert coordinator.changelog[-1]["key"] == "min_run"


async def test_watchdog_heartbeat(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    url = "http://shelly.local/script/1/heartbeat"
    aioclient_mock.get(url, text="ok")
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_WATCHDOG_URL: url})
    set_inputs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][1].query["armed"] == "0"  # observation mode
    watchdog = _entity_id(hass, "binary_sensor", f"{entry.entry_id}_watchdog")
    await entry.runtime_data.async_refresh()
    assert hass.states.get(watchdog).state == "on"


async def test_repair_issue_after_lasting_failsafe(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    set_inputs(hass)
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    hass.states.async_set("climate.bad", "unavailable")
    hass.states.async_set("sensor.bad_heating", "unavailable")

    freezer.tick(timedelta(minutes=3))
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_data") is None

    freezer.tick(timedelta(minutes=6))
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_data") is not None

    set_inputs(hass)
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_data") is None
