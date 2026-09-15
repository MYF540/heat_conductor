"""Vaillant X6 diagnostic interface (read-only) for ESPHome."""

import esphome.codegen as cg
from esphome.components import uart
import esphome.config_validation as cv
from esphome.const import CONF_ID

CODEOWNERS = ["@MYF540"]
DEPENDENCIES = ["uart"]
AUTO_LOAD = ["sensor", "binary_sensor"]

CONF_VAILLANT_X6_ID = "vaillant_x6_id"
CONF_RESPONSE_TIMEOUT = "response_timeout"
CONF_REQUEST_GAP = "request_gap"
CONF_REQUEST_BYTE = "request_byte"

vaillant_x6_ns = cg.esphome_ns.namespace("vaillant_x6")
VaillantX6 = vaillant_x6_ns.class_("VaillantX6", cg.PollingComponent, uart.UARTDevice)
ValueType = vaillant_x6_ns.enum("ValueType", is_class=True)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(VaillantX6),
            cv.Optional(
                CONF_RESPONSE_TIMEOUT, default="500ms"
            ): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_REQUEST_GAP, default="100ms"): cv.positive_time_period_milliseconds,
            # 6th request byte: 0x05 for older boilers, 0x00 for newer ones; auto tries both.
            cv.Optional(CONF_REQUEST_BYTE, default="auto"): cv.Any(
                cv.one_of("auto", lower=True), cv.hex_uint8_t
            ),
        }
    )
    .extend(cv.polling_component_schema("15s"))
    .extend(uart.UART_DEVICE_SCHEMA)
)

FINAL_VALIDATE_SCHEMA = uart.final_validate_device_schema(
    "vaillant_x6", require_tx=True, require_rx=True, data_bits=8, parity="NONE", stop_bits=1
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    cg.add(var.set_response_timeout(config[CONF_RESPONSE_TIMEOUT]))
    cg.add(var.set_request_gap(config[CONF_REQUEST_GAP]))
    if config[CONF_REQUEST_BYTE] == "auto":
        cg.add(var.set_request_byte(0x05, True))
    else:
        cg.add(var.set_request_byte(config[CONF_REQUEST_BYTE], False))
