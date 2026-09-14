"""Numeric values read from the Vaillant X6 interface."""

import esphome.codegen as cg
from esphome.components import sensor
import esphome.config_validation as cv
from esphome.const import (
    DEVICE_CLASS_DURATION,
    DEVICE_CLASS_TEMPERATURE,
    ENTITY_CATEGORY_DIAGNOSTIC,
    ICON_COUNTER,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    UNIT_CELSIUS,
    UNIT_MINUTE,
)

from . import CONF_VAILLANT_X6_ID, ValueType, VaillantX6

CONF_ERRORS = "errors"

# key: (X6 address, value type)
TEMPERATURES = {
    "flow_temperature": 0x18,  # Vorlauf ist
    "flow_temperature_target": 0x39,  # Vorlauf soll (Kessel)
    "flow_temperature_controller": 0x25,  # Vorlauf soll vom Regler (7-8-9)
    "return_temperature": 0x98,  # Rücklauf ist
}
MINUTES = {
    "remaining_burner_lock": 0x38,  # verbleibende Brennsperrzeit
}

_temperature_schema = sensor.sensor_schema(
    unit_of_measurement=UNIT_CELSIUS,
    accuracy_decimals=1,
    device_class=DEVICE_CLASS_TEMPERATURE,
    state_class=STATE_CLASS_MEASUREMENT,
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VAILLANT_X6_ID): cv.use_id(VaillantX6),
        **{cv.Optional(key): _temperature_schema for key in TEMPERATURES},
        cv.Optional("remaining_burner_lock"): sensor.sensor_schema(
            unit_of_measurement=UNIT_MINUTE,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_DURATION,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        cv.Optional(CONF_ERRORS): sensor.sensor_schema(
            accuracy_decimals=0,
            icon=ICON_COUNTER,
            state_class=STATE_CLASS_TOTAL_INCREASING,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VAILLANT_X6_ID])
    for key, address in TEMPERATURES.items():
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(hub.add_sensor(address, ValueType.TEMPERATURE, sens))
    for key, address in MINUTES.items():
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(hub.add_sensor(address, ValueType.MINUTES, sens))
    if CONF_ERRORS in config:
        sens = await sensor.new_sensor(config[CONF_ERRORS])
        cg.add(hub.set_error_sensor(sens))
