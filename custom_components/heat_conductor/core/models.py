"""Shared data types of the control logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class RoomKind(StrEnum):
    """How a room participates in the control."""

    REGULATED = "regulated"
    MONITOR = "monitor"


class OperatingMode(StrEnum):
    """Global operating mode selected by the user."""

    AUTO = "auto"
    COMFORT = "comfort"
    ECO = "eco"
    AWAY = "away"
    VACATION = "vacation"
    FROST_PROTECTION = "frost_protection"
    OFF = "off"


class BoilerState(StrEnum):
    """State of the boiler controller."""

    STARTING = "starting"
    OFF = "off"
    HEATING = "heating"
    FROST_PROTECTION = "frost_protection"
    SUMMER = "summer"
    MANUAL = "manual"
    DISABLED = "disabled"
    FAILSAFE = "failsafe"


class Reason(StrEnum):
    """Why the boiler controller decided the way it did."""

    STARTUP = "startup"
    AUTOMATION_DISABLED = "automation_disabled"
    MANUAL_OVERRIDE = "manual_override"
    RELAY_UNAVAILABLE = "relay_unavailable"
    NO_DATA = "no_data"
    OVERTEMPERATURE = "overtemperature"
    FROST_PROTECTION = "frost_protection"
    MODE_OFF = "mode_off"
    FROST_ONLY = "frost_only"
    SUMMER_MODE = "summer_mode"
    NO_DEMAND = "no_demand"
    WAITING_CONFIRMATION = "waiting_confirmation"
    WAITING_MIN_PAUSE = "waiting_min_pause"
    WAITING_MAX_STARTS = "waiting_max_starts"
    DEMAND_START = "demand_start"
    DEFICIT_START = "deficit_start"
    DEMAND_CONTINUES = "demand_continues"
    MIN_RUNTIME = "min_runtime"
    DEMAND_SATISFIED = "demand_satisfied"
    RESIDUAL_HEAT = "residual_heat"


class RoomStatus(StrEnum):
    """Data quality / participation status of a room."""

    OK = "ok"
    DEGRADED = "degraded"
    STALE = "stale"
    WINDOW_OPEN = "window_open"
    MONITOR_ONLY = "monitor_only"


@dataclass(frozen=True, slots=True)
class Reading:
    """A numeric input value with the time it was last reported."""

    value: float | None
    last_reported: datetime | None

    def valid_value(self, now: datetime, max_age: timedelta) -> float | None:
        """Return the value if present and not older than max_age."""
        if self.value is None or self.last_reported is None:
            return None
        if now - self.last_reported > max_age:
            return None
        return self.value


MISSING = Reading(None, None)


@dataclass(frozen=True, slots=True)
class ControlParams:
    """Tunable parameters. Defaults are starting values to be calibrated."""

    start_threshold: float = 0.25
    start_confirm: timedelta = timedelta(minutes=5)
    stop_threshold: float = 0.10
    immediate_start_deficit: float = 1.0
    deficit_full_scale: float = 1.0
    valve_noise: float = 0.05
    min_run: timedelta = timedelta(minutes=20)
    min_pause: timedelta = timedelta(minutes=15)
    max_starts_per_hour: int = 3
    heating_limit: float = 16.0
    frost_limit: float = 6.0
    frost_release_hysteresis: float = 1.0
    max_flow_temperature: float = 80.0
    stale_after: timedelta = timedelta(hours=4)
    outdoor_smoothing: timedelta = timedelta(hours=24)
    outdoor_max_spread: float = 2.0
    manual_override: timedelta = timedelta(minutes=60)
    startup_grace: timedelta = timedelta(minutes=2)
    burner_flow_threshold: float = 0.2
    residual_heat_stop: bool = True
    residual_heat_margin: float = 0.2
    use_forecast: bool = True
