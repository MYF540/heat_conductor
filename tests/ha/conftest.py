"""Fixtures for Home Assistant integration tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heat_conductor.const import (
    CONF_BOILER_SWITCH,
    CONF_CLIMATES,
    CONF_OUTDOOR_SENSORS,
    CONF_ROOM_KIND,
    CONF_ROOM_TEMPERATURE,
    CONF_VALVES,
    CONF_WEIGHT,
    DOMAIN,
    PARAMETER_DEFAULTS,
    SUBENTRY_ROOM,
)

OUTDOOR = "sensor.aussen_temperatur"
CLIMATE_BAD = "climate.bad"
VALVE_BAD = "sensor.bad_heating"
BEDROOM_TEMP = "sensor.schlafzimmer_temperatur"
BOILER = "switch.kessel"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    """Allow loading custom_components in every test."""
    yield


def set_inputs(
    hass: HomeAssistant,
    *,
    valve: float | str = 100,
    target: float = 21.0,
    current: float = 19.3,
    outdoor: float = 3.0,
    boiler: str = "off",
) -> None:
    """Write input states."""
    hass.states.async_set(
        OUTDOOR,
        str(outdoor),
        {"unit_of_measurement": UnitOfTemperature.CELSIUS, "device_class": "temperature"},
    )
    hass.states.async_set(
        CLIMATE_BAD, "heat", {"temperature": target, "current_temperature": current}
    )
    hass.states.async_set(VALVE_BAD, str(valve), {"unit_of_measurement": PERCENTAGE})
    hass.states.async_set(
        BEDROOM_TEMP,
        "17.0",
        {"unit_of_measurement": UnitOfTemperature.CELSIUS, "device_class": "temperature"},
    )
    hass.states.async_set(BOILER, boiler)


@pytest.fixture
def entry() -> MockConfigEntry:
    """A config entry with one regulated and one monitored room."""
    options: dict[str, Any] = {
        **PARAMETER_DEFAULTS,
        CONF_OUTDOOR_SENSORS: [OUTDOOR],
        CONF_BOILER_SWITCH: BOILER,
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
            ConfigSubentryData(
                data={
                    CONF_ROOM_KIND: "monitor",
                    CONF_ROOM_TEMPERATURE: BEDROOM_TEMP,
                    CONF_WEIGHT: 1.0,
                },
                subentry_type=SUBENTRY_ROOM,
                title="Schlafzimmer",
                unique_id=None,
            ),
        ],
    )
