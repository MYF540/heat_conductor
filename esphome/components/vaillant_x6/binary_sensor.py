"""On/off states read from the Vaillant X6 interface."""

import esphome.codegen as cg
from esphome.components import binary_sensor
import esphome.config_validation as cv
from esphome.const import (
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_HEAT,
    DEVICE_CLASS_RUNNING,
    ENTITY_CATEGORY_DIAGNOSTIC,
)

from . import CONF_VAILLANT_X6_ID, VaillantX6

CONF_CONNECTED = "connected"

STATES = {
    "burner": (0x0D, DEVICE_CLASS_HEAT),  # Brenner an
    "pump": (0x44, DEVICE_CLASS_RUNNING),  # Pumpe an
    "winter_mode": (0x08, None),  # Winterbetrieb (Heizung freigegeben)
}

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VAILLANT_X6_ID): cv.use_id(VaillantX6),
        **{
            cv.Optional(key): (
                binary_sensor.binary_sensor_schema(device_class=device_class)
                if device_class
                else binary_sensor.binary_sensor_schema()
            )
            for key, (_, device_class) in STATES.items()
        },
        cv.Optional(CONF_CONNECTED): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_CONNECTIVITY,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VAILLANT_X6_ID])
    for key, (address, _) in STATES.items():
        if key in config:
            sens = await binary_sensor.new_binary_sensor(config[key])
            cg.add(hub.add_binary_sensor(address, sens))
    if CONF_CONNECTED in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_CONNECTED])
        cg.add(hub.set_connected_sensor(sens))
