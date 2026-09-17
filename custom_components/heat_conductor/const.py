"""Constants for HeatConductor."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "heat_conductor"

UPDATE_INTERVAL: Final = timedelta(seconds=30)
COMMAND_RETRY_INTERVAL: Final = timedelta(seconds=60)
WATCHDOG_INTERVAL: Final = timedelta(seconds=60)
FORECAST_INTERVAL: Final = timedelta(minutes=30)
ISSUE_DELAY: Final = timedelta(minutes=5)
STORAGE_VERSION: Final = 1
STORAGE_SAVE_DELAY: Final = 30
CHANGELOG_MAX_ENTRIES: Final = 500

SUBENTRY_ROOM: Final = "room"

PANEL_URL: Final = "heat-conductor"
PANEL_STATIC_URL: Final = "/heat_conductor_static"
PANEL_ELEMENT: Final = "heat-conductor-panel"

# Entities of the main entry (stored in options)
CONF_BOILER_SWITCH: Final = "boiler_switch"
CONF_FLOW_TEMPERATURE: Final = "flow_temperature"
CONF_RETURN_TEMPERATURE: Final = "return_temperature"
CONF_GAS_FLOW: Final = "gas_flow"
CONF_GAS_METER: Final = "gas_meter"
CONF_BURNER_SENSOR: Final = "burner_sensor"
CONF_OUTDOOR_SENSORS: Final = "outdoor_sensors"
CONF_WEATHER: Final = "weather"
CONF_WATCHDOG_URL: Final = "watchdog_url"
CONF_PRESENCE: Final = "presence_entities"
CONF_DUTY_CYCLE: Final = "duty_cycle_sensor"
CONF_FLOW_SETPOINT: Final = "flow_setpoint_sensor"
CONF_SOLAR_POWER: Final = "solar_power_sensor"

# Room subentry
CONF_ROOM_KIND: Final = "kind"
CONF_CLIMATES: Final = "climates"
CONF_VALVES: Final = "valves"
CONF_ROOM_TEMPERATURE: Final = "room_temperature"
CONF_WINDOWS: Final = "windows"
CONF_WEIGHT: Final = "weight"
CONF_SCHEDULE: Final = "schedule"
CONF_COMPENSATION: Final = "compensation"
CONF_SOLAR_GAIN: Final = "solar_gain"
CONF_USAGE_ENTITIES: Final = "usage_entities"

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

# Room control (stored in options)
CONF_DEFAULT_COMFORT: Final = "default_comfort"
CONF_DEFAULT_ECO: Final = "default_eco"
CONF_VACATION_TEMP: Final = "vacation_temperature"
CONF_FROST_TEMP: Final = "frost_temperature"
CONF_WINDOW_TEMP: Final = "window_temperature"
CONF_BOOST_TEMP: Final = "boost_temperature"
CONF_BOOST_DURATION: Final = "boost_duration"
CONF_OVERRIDE_DURATION: Final = "override_duration"
CONF_WRITE_INTERVAL: Final = "write_interval"
CONF_COMPENSATION_MAX: Final = "compensation_max"
CONF_DUTY_CYCLE_LIMIT: Final = "duty_cycle_limit"
CONF_FORCE_MANUAL_MODE: Final = "force_manual_mode"
CONF_ADOPT_TRV_CHANGES: Final = "adopt_trv_changes"

ROOM_CONTROL_DEFAULTS: Final[dict[str, float | bool]] = {
    CONF_DEFAULT_COMFORT: 21.0,  # °C
    CONF_DEFAULT_ECO: 18.0,  # °C
    CONF_VACATION_TEMP: 15.0,  # °C
    CONF_FROST_TEMP: 7.0,  # °C
    CONF_WINDOW_TEMP: 12.0,  # °C
    CONF_BOOST_TEMP: 24.0,  # °C
    CONF_BOOST_DURATION: 30,  # min
    CONF_OVERRIDE_DURATION: 180,  # min
    CONF_WRITE_INTERVAL: 15,  # min
    CONF_COMPENSATION_MAX: 3.0,  # K
    CONF_DUTY_CYCLE_LIMIT: 80,  # %
    CONF_FORCE_MANUAL_MODE: True,
    CONF_ADOPT_TRV_CHANGES: True,
}

# Usage based heating (stored in options)
CONF_USAGE_HOLD: Final = "usage_hold"
CONF_USAGE_IN_ECO: Final = "usage_in_eco"

USAGE_DEFAULTS: Final[dict[str, float | bool]] = {
    CONF_USAGE_HOLD: 30,  # min a room stays "in use" after the last activity
    CONF_USAGE_IN_ECO: True,  # a used room is heated during setback periods too
}

# Learning and anticipation (stored in options)
CONF_OPTIMUM_START: Final = "optimum_start"
CONF_OPTIMUM_START_MAX_LEAD: Final = "optimum_start_max_lead"
CONF_RESIDUAL_HEAT: Final = "residual_heat"
CONF_USE_FORECAST: Final = "use_forecast"
CONF_SOLAR_REFERENCE: Final = "solar_reference"

LEARNING_DEFAULTS: Final[dict[str, float | bool]] = {
    CONF_OPTIMUM_START: True,
    CONF_OPTIMUM_START_MAX_LEAD: 180,  # min
    CONF_RESIDUAL_HEAT: True,
    CONF_USE_FORECAST: True,
    CONF_SOLAR_REFERENCE: 0.0,  # kW peak, 0 = no solar proxy
}

ALL_DEFAULTS: Final[dict[str, float | bool]] = {
    **PARAMETER_DEFAULTS,
    **ENERGY_DEFAULTS,
    **ROOM_CONTROL_DEFAULTS,
    **USAGE_DEFAULTS,
    **LEARNING_DEFAULTS,
}
