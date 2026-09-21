"""Parameter metadata and conversion of options into control parameters.

PARAMS is the single source for ranges, units and grouping. It is used by the
options flow, the panel and the server-side validation of panel changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .const import (
    ALL_DEFAULTS,
    CONF_ADOPT_TRV_CHANGES,
    CONF_AUTO_VACATION,
    CONF_AUTO_VACATION_AFTER,
    CONF_AUTO_VACATION_RETURN,
    CONF_BOOST_DURATION,
    CONF_BOOST_TEMP,
    CONF_BURNER_FLOW_THRESHOLD,
    CONF_BURNER_MAX_POWER,
    CONF_CALORIFIC_VALUE,
    CONF_COMPENSATION_MAX,
    CONF_CONDENSING_RETURN_LIMIT,
    CONF_CURVE_SETTING,
    CONF_CURVE_TARGET_VALVE,
    CONF_DEFAULT_COMFORT,
    CONF_DEFAULT_ECO,
    CONF_DEFICIT_FULL_SCALE,
    CONF_DUTY_CYCLE_LIMIT,
    CONF_FORCE_MANUAL_MODE,
    CONF_FROST_LIMIT,
    CONF_FROST_TEMP,
    CONF_HEATING_LIMIT,
    CONF_IMMEDIATE_DEFICIT,
    CONF_LEARNED_NIGHT,
    CONF_MANUAL_OVERRIDE,
    CONF_MAX_FLOW_TEMPERATURE,
    CONF_MAX_STARTS,
    CONF_MIN_PAUSE,
    CONF_MIN_RUN,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_OPTIMUM_START,
    CONF_OPTIMUM_START_MAX_LEAD,
    CONF_OUTDOOR_SMOOTHING,
    CONF_OVERRIDE_DURATION,
    CONF_RESIDUAL_HEAT,
    CONF_SLEEP_CONFIRM,
    CONF_SOLAR_REFERENCE,
    CONF_STALE_AFTER,
    CONF_START_CONFIRM,
    CONF_START_THRESHOLD,
    CONF_STOP_THRESHOLD,
    CONF_USAGE_HOLD,
    CONF_USAGE_IN_ECO,
    CONF_USE_FORECAST,
    CONF_VACATION_TEMP,
    CONF_WAKE_CONFIRM,
    CONF_WINDOW_TEMP,
    CONF_WRITE_INTERVAL,
    CONF_Z_FACTOR,
)
from .core.energy import EnergyParams
from .core.models import ControlParams
from .core.setpoint import SetpointParams
from .core.sleep import SleepParams, parse_time_of_day
from .core.vacation import VacationParams


@dataclass(frozen=True, slots=True)
class ParamMeta:
    """Description of one user parameter."""

    key: str
    group: str
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | str | None = None
    boolean: bool = False

    @property
    def default(self) -> float | bool:
        """Default value."""
        return ALL_DEFAULTS[self.key]

    def as_dict(self) -> dict[str, Any]:
        """For the panel."""
        return {
            "key": self.key,
            "group": self.group,
            "unit": self.unit,
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "boolean": self.boolean,
            "default": self.default,
        }


def _n(
    key: str, group: str, unit: str | None, minimum: float, maximum: float, step: float | str
) -> ParamMeta:
    return ParamMeta(key, group, unit, minimum, maximum, step)


def _b(key: str, group: str) -> ParamMeta:
    return ParamMeta(key, group, boolean=True)


PARAMS: tuple[ParamMeta, ...] = (
    _n(CONF_START_THRESHOLD, "start_stop", "%", 1, 100, 1),
    _n(CONF_START_CONFIRM, "start_stop", "min", 0, 60, 1),
    _n(CONF_STOP_THRESHOLD, "start_stop", "%", 0, 100, 1),
    _n(CONF_IMMEDIATE_DEFICIT, "start_stop", "K", 0.2, 5, 0.1),
    _n(CONF_DEFICIT_FULL_SCALE, "start_stop", "K", 0.2, 5, 0.1),
    _n(CONF_MIN_RUN, "cycle_protection", "min", 0, 120, 1),
    _n(CONF_MIN_PAUSE, "cycle_protection", "min", 0, 120, 1),
    _n(CONF_MAX_STARTS, "cycle_protection", "1/h", 1, 20, 1),
    _n(CONF_HEATING_LIMIT, "heating_limit", "°C", 5, 30, 0.5),
    _n(CONF_OUTDOOR_SMOOTHING, "heating_limit", "h", 1, 72, 1),
    _n(CONF_FROST_LIMIT, "heating_limit", "°C", 2, 12, 0.5),
    _n(CONF_MAX_FLOW_TEMPERATURE, "safety", "°C", 40, 90, 1),
    _n(CONF_STALE_AFTER, "safety", "min", 15, 1440, 5),
    _n(CONF_MANUAL_OVERRIDE, "safety", "min", 5, 1440, 5),
    _n(CONF_BURNER_FLOW_THRESHOLD, "sensors", "m³/h", 0, 5, 0.05),
    _n(CONF_CALORIFIC_VALUE, "energy", "kWh/m³", 8, 13, 0.001),
    _n(CONF_Z_FACTOR, "energy", None, 0.8, 1.1, "any"),
    _n(CONF_BURNER_MAX_POWER, "energy", "kW", 0, 200, 0.1),
    _n(CONF_CONDENSING_RETURN_LIMIT, "energy", "°C", 30, 70, 1),
    _n(CONF_DEFAULT_COMFORT, "room_control", "°C", 12, 28, 0.5),
    _n(CONF_DEFAULT_ECO, "room_control", "°C", 10, 24, 0.5),
    _n(CONF_VACATION_TEMP, "room_control", "°C", 5, 22, 0.5),
    _n(CONF_FROST_TEMP, "room_control", "°C", 5, 12, 0.5),
    _n(CONF_WINDOW_TEMP, "room_control", "°C", 5, 16, 0.5),
    _n(CONF_BOOST_TEMP, "room_control", "°C", 16, 30, 0.5),
    _n(CONF_BOOST_DURATION, "room_control", "min", 5, 240, 5),
    _n(CONF_OVERRIDE_DURATION, "room_control", "min", 15, 1440, 15),
    _n(CONF_WRITE_INTERVAL, "room_control", "min", 1, 120, 1),
    _n(CONF_COMPENSATION_MAX, "room_control", "K", 0, 6, 0.5),
    _n(CONF_DUTY_CYCLE_LIMIT, "room_control", "%", 10, 100, 1),
    _b(CONF_FORCE_MANUAL_MODE, "room_control"),
    _b(CONF_ADOPT_TRV_CHANGES, "room_control"),
    _n(CONF_USAGE_HOLD, "usage", "min", 0, 240, 5),
    _b(CONF_USAGE_IN_ECO, "usage"),
    _n(CONF_SLEEP_CONFIRM, "sleep", "min", 0, 120, 5),
    _n(CONF_WAKE_CONFIRM, "sleep", "min", 0, 120, 5),
    _b(CONF_LEARNED_NIGHT, "sleep"),
    _b(CONF_AUTO_VACATION, "vacation"),
    _n(CONF_AUTO_VACATION_AFTER, "vacation", "h", 6, 336, 1),
    _n(CONF_AUTO_VACATION_RETURN, "vacation", "min", 15, 1440, 15),
    _b(CONF_OPTIMUM_START, "learning"),
    _n(CONF_OPTIMUM_START_MAX_LEAD, "learning", "min", 15, 480, 15),
    _b(CONF_RESIDUAL_HEAT, "learning"),
    _b(CONF_USE_FORECAST, "learning"),
    _n(CONF_SOLAR_REFERENCE, "learning", "kW", 0, 100, 0.1),
    _n(CONF_CURVE_SETTING, "learning", None, 0, 4, 0.05),
    _n(CONF_CURVE_TARGET_VALVE, "learning", "%", 50, 100, 5),
)
PARAMS_BY_KEY: dict[str, ParamMeta] = {meta.key: meta for meta in PARAMS}
GROUPS: tuple[str, ...] = tuple(dict.fromkeys(meta.group for meta in PARAMS))


def validate(values: dict[str, Any]) -> dict[str, float | bool]:
    """Check panel input against the metadata. Raises ValueError."""
    result: dict[str, float | bool] = {}
    for key, value in values.items():
        meta = PARAMS_BY_KEY.get(key)
        if meta is None:
            raise ValueError(f"Unknown parameter: {key}")
        if meta.boolean:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            result[key] = value
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        if meta.minimum is not None and value < meta.minimum:
            raise ValueError(f"{key} must be at least {meta.minimum}")
        if meta.maximum is not None and value > meta.maximum:
            raise ValueError(f"{key} must be at most {meta.maximum}")
        result[key] = float(value)
    return result


def _value(options: dict[str, Any], key: str) -> Any:
    return options.get(key, ALL_DEFAULTS[key])


def control_params(options: dict[str, Any]) -> ControlParams:
    """Boiler control parameters."""

    def f(key: str) -> float:
        return float(_value(options, key))

    return ControlParams(
        start_threshold=f(CONF_START_THRESHOLD) / 100,
        start_confirm=timedelta(minutes=f(CONF_START_CONFIRM)),
        stop_threshold=f(CONF_STOP_THRESHOLD) / 100,
        immediate_start_deficit=f(CONF_IMMEDIATE_DEFICIT),
        deficit_full_scale=f(CONF_DEFICIT_FULL_SCALE),
        min_run=timedelta(minutes=f(CONF_MIN_RUN)),
        min_pause=timedelta(minutes=f(CONF_MIN_PAUSE)),
        max_starts_per_hour=int(f(CONF_MAX_STARTS)),
        heating_limit=f(CONF_HEATING_LIMIT),
        frost_limit=f(CONF_FROST_LIMIT),
        max_flow_temperature=f(CONF_MAX_FLOW_TEMPERATURE),
        stale_after=timedelta(minutes=f(CONF_STALE_AFTER)),
        manual_override=timedelta(minutes=f(CONF_MANUAL_OVERRIDE)),
        outdoor_smoothing=timedelta(hours=f(CONF_OUTDOOR_SMOOTHING)),
        burner_flow_threshold=f(CONF_BURNER_FLOW_THRESHOLD),
        residual_heat_stop=bool(_value(options, CONF_RESIDUAL_HEAT)),
        use_forecast=bool(_value(options, CONF_USE_FORECAST)),
    )


def energy_params(options: dict[str, Any]) -> EnergyParams:
    """Gas and boiler constants."""
    return EnergyParams(
        calorific_value=float(_value(options, CONF_CALORIFIC_VALUE)),
        z_factor=float(_value(options, CONF_Z_FACTOR)),
        burner_max_power=float(_value(options, CONF_BURNER_MAX_POWER)),
        condensing_return_limit=float(_value(options, CONF_CONDENSING_RETURN_LIMIT)),
    )


def setpoint_params(options: dict[str, Any]) -> SetpointParams:
    """Room control parameters."""

    def f(key: str) -> float:
        return float(_value(options, key))

    return SetpointParams(
        default_comfort=f(CONF_DEFAULT_COMFORT),
        default_eco=f(CONF_DEFAULT_ECO),
        vacation_temp=f(CONF_VACATION_TEMP),
        frost_temp=f(CONF_FROST_TEMP),
        window_temp=f(CONF_WINDOW_TEMP),
        boost_temp=f(CONF_BOOST_TEMP),
        boost_duration=timedelta(minutes=f(CONF_BOOST_DURATION)),
        override_duration=timedelta(minutes=f(CONF_OVERRIDE_DURATION)),
        write_interval=timedelta(minutes=f(CONF_WRITE_INTERVAL)),
        compensation_max=f(CONF_COMPENSATION_MAX),
        duty_cycle_limit=f(CONF_DUTY_CYCLE_LIMIT),
        force_manual_mode=bool(_value(options, CONF_FORCE_MANUAL_MODE)),
        adopt_trv_changes=bool(_value(options, CONF_ADOPT_TRV_CHANGES)),
        optimum_start=bool(_value(options, CONF_OPTIMUM_START)),
        optimum_start_max_lead=timedelta(minutes=f(CONF_OPTIMUM_START_MAX_LEAD)),
        usage_hold=timedelta(minutes=f(CONF_USAGE_HOLD)),
        usage_in_eco=bool(_value(options, CONF_USAGE_IN_ECO)),
    )


def sleep_params(options: dict[str, Any]) -> SleepParams:
    """Night window, confirmation times and whether the learned night counts."""
    return SleepParams(
        window_start=parse_time_of_day(options.get(CONF_NIGHT_START)),
        window_end=parse_time_of_day(options.get(CONF_NIGHT_END)),
        confirm=timedelta(minutes=float(_value(options, CONF_SLEEP_CONFIRM))),
        wake_confirm=timedelta(minutes=float(_value(options, CONF_WAKE_CONFIRM))),
        use_learned=bool(_value(options, CONF_LEARNED_NIGHT)),
    )


def vacation_params(options: dict[str, Any]) -> VacationParams:
    """When automatic vacation starts and ends."""
    return VacationParams(
        enabled=bool(_value(options, CONF_AUTO_VACATION)),
        absence=timedelta(hours=float(_value(options, CONF_AUTO_VACATION_AFTER))),
        presence=timedelta(minutes=float(_value(options, CONF_AUTO_VACATION_RETURN))),
    )


def curve_advice_params(options: dict[str, Any]) -> tuple[float, float]:
    """(target valve opening as a fraction, heating curve set at the controller)."""
    return (
        float(_value(options, CONF_CURVE_TARGET_VALVE)) / 100,
        float(_value(options, CONF_CURVE_SETTING)),
    )


def solar_reference(options: dict[str, Any]) -> float:
    """Peak PV power used as reference for the sun proxy."""
    return float(_value(options, CONF_SOLAR_REFERENCE))
