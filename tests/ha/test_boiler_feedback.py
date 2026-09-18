"""Feedback from the boiler electronics inside Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_BOILER_FLOW_TEMPERATURE,
    CONF_BOILER_WINTER_MODE,
    CONF_BURNER_LOCK,
    CONF_FLOW_TEMPERATURE,
    CONF_PUMP_SENSOR,
    CONF_RELAY_FEEDBACK,
    CONF_RETURN_TEMPERATURE,
    DOMAIN,
)

from .conftest import set_inputs

FEEDBACK = "binary_sensor.heizung_waermeanforderung_raumthermostat"
BURNER_LOCK = "sensor.heizung_brennersperrzeit"
WINTER = "binary_sensor.heizung_winterbetrieb"
PUMP = "binary_sensor.heizung_heizungspumpe"
PIPE_FLOW = "sensor.heizung_vorlauf"
PIPE_RETURN = "sensor.heizung_rucklauf"
BOILER_FLOW = "sensor.heizung_kessel_vorlauf_ist"


@pytest.fixture
def feedback_entry(entry: MockConfigEntry) -> MockConfigEntry:
    """The standard entry with all boiler feedback entities configured."""
    options: dict[str, Any] = {
        **entry.options,
        CONF_RELAY_FEEDBACK: FEEDBACK,
        CONF_BURNER_LOCK: BURNER_LOCK,
        CONF_BOILER_WINTER_MODE: WINTER,
        CONF_PUMP_SENSOR: PUMP,
        CONF_FLOW_TEMPERATURE: PIPE_FLOW,
        CONF_RETURN_TEMPERATURE: PIPE_RETURN,
        CONF_BOILER_FLOW_TEMPERATURE: BOILER_FLOW,
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


def _set_feedback(
    hass: HomeAssistant, *, feedback: str = "off", lock: str = "0", winter: str = "on"
) -> None:
    hass.states.async_set(FEEDBACK, feedback)
    hass.states.async_set(BURNER_LOCK, lock, {"unit_of_measurement": "min"})
    hass.states.async_set(WINTER, winter)
    hass.states.async_set(PUMP, "on")
    celsius = {"unit_of_measurement": "°C", "device_class": "temperature"}
    hass.states.async_set(PIPE_FLOW, "52.0", celsius)
    hass.states.async_set(PIPE_RETURN, "41.0", celsius)
    hass.states.async_set(BOILER_FLOW, "55.0", celsius)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _advance(hass: HomeAssistant, entry: MockConfigEntry, freezer, minutes: float) -> None:  # type: ignore[no-untyped-def]
    freezer.tick(timedelta(minutes=minutes))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_relay_feedback_mismatch_raises_a_repair_issue(
    hass: HomeAssistant, feedback_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """The boiler reports demand although the relay is off."""
    set_inputs(hass, boiler="off")
    _set_feedback(hass, feedback="on")
    await _setup(hass, feedback_entry)

    problem = _entity_id(hass, "binary_sensor", f"{feedback_entry.entry_id}_problem")
    await _advance(hass, feedback_entry, freezer, 3)
    state = hass.states.get(problem)
    assert state.state == "on"
    assert state.attributes["relay_feedback_mismatch"] is True

    await _advance(hass, feedback_entry, freezer, 6)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "relay_feedback_mismatch") is not None

    hass.states.async_set(FEEDBACK, "off")
    await _advance(hass, feedback_entry, freezer, 1)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "relay_feedback_mismatch") is None


async def test_summer_mode_conflict_while_heat_is_needed(
    hass: HomeAssistant, feedback_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """A cold room and a boiler in summer mode are reported."""
    set_inputs(hass, target=21.0, current=19.0, valve=100)
    _set_feedback(hass, winter="off")
    await _setup(hass, feedback_entry)

    await _advance(hass, feedback_entry, freezer, 3)
    assert feedback_entry.runtime_data.data.decision.request_heat
    problem = _entity_id(hass, "binary_sensor", f"{feedback_entry.entry_id}_problem")
    assert hass.states.get(problem).attributes["boiler_summer_mode"] is True

    await _advance(hass, feedback_entry, freezer, 6)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "boiler_summer_mode") is not None


async def test_heat_request_shows_the_boiler_feedback(
    hass: HomeAssistant, feedback_entry: MockConfigEntry
) -> None:
    """Burner lock and demand feedback appear as attributes."""
    set_inputs(hass)
    _set_feedback(hass, feedback="off", lock="7")
    await _setup(hass, feedback_entry)

    heat_request = _entity_id(hass, "binary_sensor", f"{feedback_entry.entry_id}_heat_request")
    attributes = hass.states.get(heat_request).attributes
    assert attributes["burner_lock_minutes"] == 7.0
    assert attributes["boiler_sees_demand"] is False


async def test_without_feedback_entities_nothing_changes(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The standard entry keeps its previous attributes."""
    set_inputs(hass)
    await _setup(hass, entry)

    heat_request = _entity_id(hass, "binary_sensor", f"{entry.entry_id}_heat_request")
    attributes = hass.states.get(heat_request).attributes
    assert "burner_lock_minutes" not in attributes
    assert "boiler_sees_demand" not in attributes


async def test_boiler_sensor_comparison(
    hass: HomeAssistant, feedback_entry: MockConfigEntry
) -> None:
    """Pipe flow is compared with the boiler sensor, the boiler spread uses the pipe return."""
    set_inputs(hass)
    _set_feedback(hass)
    await _setup(hass, feedback_entry)

    deviation = _entity_id(hass, "sensor", f"{feedback_entry.entry_id}_flow_deviation")
    state = hass.states.get(deviation)
    assert float(state.state) == -3.0
    assert state.attributes["boiler_flow_temperature"] == 55.0
    assert state.attributes["suspicious"] is False

    spread = _entity_id(hass, "sensor", f"{feedback_entry.entry_id}_boiler_spread")
    state = hass.states.get(spread)
    assert float(state.state) == 14.0
    assert state.attributes["return_source"] == "pipe"

    pipe_spread = _entity_id(hass, "sensor", f"{feedback_entry.entry_id}_temperature_spread")
    assert float(hass.states.get(pipe_spread).state) == 11.0
