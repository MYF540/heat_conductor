"""Constants for HeatConductor."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "heat_conductor"

UPDATE_INTERVAL: Final = timedelta(seconds=30)
COMMAND_RETRY_INTERVAL: Final = timedelta(seconds=60)
STORAGE_VERSION: Final = 1
STORAGE_SAVE_DELAY: Final = 30

SUBENTRY_ROOM: Final = "room"

# Entities of the main entry (stored in options)
CONF_BOILER_SWITCH: Final = "boiler_switch"
CONF_FLOW_TEMPERATURE: Final = "flow_temperature"
CONF_RETURN_TEMPERATURE: Final = "return_temperature"
CONF_GAS_FLOW: Final = "gas_flow"
CONF_GAS_METER: Final = "gas_meter"
CONF_BURNER_SENSOR: Final = "burner_sensor"
CONF_OUTDOOR_SENSORS: Final = "outdoor_sensors"
CONF_WEATHER: Final = "weather"

# Room subentry
CONF_ROOM_KIND: Final = "kind"
CONF_CLIMATES: Final = "climates"
CONF_VALVES: Final = "valves"
CONF_ROOM_TEMPERATURE: Final = "room_temperature"
CONF_WINDOWS: Final = "windows"
CONF_WEIGHT: Final = "weight"

# Control parameters (stored in options, in user-facing units)
CONF_START_THRESHOLD: Final = "start_threshold"
CONF_START_CONFIRM: Final = "start_confirm"
CONF_STOP_THRESHOLD: Final = "stop_threshold"
CONF_IMMEDIATE_DEFICIT: Final = "immediate_start_deficit"
CONF_DEFICIT_FULL_SCALE: Final = "deficit_full_scale"
CONF_MIN_RUN: Final = "min_run"
CONF_MIN_PAUSE: Final = "min_pause"
CONF_MAX_STARTS: Final = "max_starts_per_hour"
CONF_HEATING_LIMIT: Final = "heating_limit"
CONF_FROST_LIMIT: Final = "frost_limit"
CONF_MAX_FLOW_TEMPERATURE: Final = "max_flow_temperature"
CONF_STALE_AFTER: Final = "stale_after"
CONF_MANUAL_OVERRIDE: Final = "manual_override"
CONF_OUTDOOR_SMOOTHING: Final = "outdoor_smoothing"
CONF_BURNER_FLOW_THRESHOLD: Final = "burner_flow_threshold"

PARAMETER_DEFAULTS: Final[dict[str, float]] = {
    CONF_START_THRESHOLD: 25,  # %
    CONF_START_CONFIRM: 5,  # min
    CONF_STOP_THRESHOLD: 10,  # %
    CONF_IMMEDIATE_DEFICIT: 1.0,  # K
    CONF_DEFICIT_FULL_SCALE: 1.0,  # K
    CONF_MIN_RUN: 20,  # min
    CONF_MIN_PAUSE: 15,  # min
    CONF_MAX_STARTS: 3,
    CONF_HEATING_LIMIT: 16.0,  # °C
    CONF_FROST_LIMIT: 6.0,  # °C
    CONF_MAX_FLOW_TEMPERATURE: 80.0,  # °C
    CONF_STALE_AFTER: 240,  # min
    CONF_MANUAL_OVERRIDE: 60,  # min
    CONF_OUTDOOR_SMOOTHING: 24,  # h
    CONF_BURNER_FLOW_THRESHOLD: 0.2,  # m³/h
}

# Energy constants (stored in options)
CONF_CALORIFIC_VALUE: Final = "calorific_value"
CONF_Z_FACTOR: Final = "z_factor"
CONF_BURNER_MAX_POWER: Final = "burner_max_power"
CONF_CONDENSING_RETURN_LIMIT: Final = "condensing_return_limit"

ENERGY_DEFAULTS: Final[dict[str, float]] = {
    CONF_CALORIFIC_VALUE: 11.2,  # kWh/m³ (Brennwert Hs, see gas bill)
    CONF_Z_FACTOR: 0.95,  # Zustandszahl, see gas bill
    CONF_BURNER_MAX_POWER: 0.0,  # kW (Hi) from the type plate, 0 = unknown
    CONF_CONDENSING_RETURN_LIMIT: 55.0,  # °C
}
