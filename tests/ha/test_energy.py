"""Phase 2: energy entities inside Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_BURNER_MAX_POWER,
    CONF_CALORIFIC_VALUE,
    CONF_GAS_FLOW,
    CONF_GAS_METER,
    CONF_RETURN_TEMPERATURE,
    CONF_Z_FACTOR,
    DOMAIN,
    ENERGY_DEFAULTS,
)

from .conftest import set_inputs

GAS_METER = "sensor.gaszaehler"
GAS_FLOW = "sensor.gasdurchfluss"
RETURN = "sensor.ruecklauf"


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


def _set_gas(hass: HomeAssistant, meter: float, flow: float, ret: float = 45.0) -> None:
    hass.states.async_set(
        GAS_METER, str(meter), {"unit_of_measurement": "m³", "device_class": "gas"}
    )
    hass.states.async_set(GAS_FLOW, str(flow), {"unit_of_measurement": "m³/h"})
    hass.states.async_set(RETURN, str(ret), {"unit_of_measurement": "°C"})


@pytest.fixture
def energy_entry(entry: MockConfigEntry) -> MockConfigEntry:
    """The standard entry extended with gas meter, flow and return temperature."""
    options = {
        **entry.options,
        CONF_GAS_METER: GAS_METER,
        CONF_GAS_FLOW: GAS_FLOW,
        CONF_RETURN_TEMPERATURE: RETURN,
        CONF_CALORIFIC_VALUE: 11.5,
        CONF_Z_FACTOR: 0.96,
        CONF_BURNER_MAX_POWER: 21.0,
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
                "unique_id": None,
            }
            for s in entry.subentries.values()
        ],
    )


async def test_energy_entities(
    hass: HomeAssistant, energy_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    set_inputs(hass)
    _set_gas(hass, meter=1000.0, flow=1.0)
    energy_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(energy_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = energy_entry.runtime_data
    entry_id = energy_entry.entry_id

    freezer.tick(timedelta(minutes=1))
    _set_gas(hass, meter=1000.5, flow=1.0)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    kwh_per_m3 = 11.5 * 0.96
    energy = hass.states.get(_entity_id(hass, "sensor", f"{entry_id}_gas_energy"))
    assert float(energy.state) == pytest.approx(0.5 * kwh_per_m3, abs=0.001)
    assert energy.attributes["device_class"] == "energy"
    assert energy.attributes["state_class"] == "total_increasing"

    power = hass.states.get(_entity_id(hass, "sensor", f"{entry_id}_burner_power"))
    assert float(power.state) == pytest.approx(kwh_per_m3, abs=0.01)

    modulation = hass.states.get(_entity_id(hass, "sensor", f"{entry_id}_burner_modulation"))
    assert float(modulation.state) == pytest.approx(kwh_per_m3 / 1.11 / 21 * 100, abs=0.1)

    condensing = hass.states.get(_entity_id(hass, "binary_sensor", f"{entry_id}_condensing"))
    assert condensing.state == "on"

    volume = hass.states.get(_entity_id(hass, "sensor", f"{entry_id}_gas_volume"))
    assert float(volume.state) == pytest.approx(0.5)


async def test_energy_entities_absent_without_gas_source(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_gas_energy") is None
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_outdoor_mean_today")
        is not None
    )


async def test_options_energy_step(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    set_inputs(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "energy"}
    )
    assert result["type"] is FlowResultType.FORM
    values = {**ENERGY_DEFAULTS, CONF_CALORIFIC_VALUE: 11.4, CONF_Z_FACTOR: 0.955}
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.energy_params.kwh_per_m3 == pytest.approx(11.4 * 0.955)
