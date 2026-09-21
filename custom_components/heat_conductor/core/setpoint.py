"""Effective room setpoints and planning of thermostat writes (room control)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
import math
from typing import Any

from .models import OperatingMode

MIN_TEMPERATURE = 5.0
MAX_TEMPERATURE = 30.0
# A thermostat change counts as manual only if it happened well after our own write.
MANUAL_CHANGE_GRACE = timedelta(minutes=3)
OPTIMUM_START_SAFETY = 1.25
FORECAST_DROP_FACTOR = 1.2


class SetpointSource(StrEnum):
    """Why a room has its current target temperature."""

    WINDOW = "window"
    ROOM_OFF = "room_off"
    BOOST = "boost"
    OVERRIDE = "override"
    MODE_OFF = "mode_off"
    FROST_PROTECTION = "frost_protection"
    VACATION = "vacation"
    AWAY = "away"
    ECO = "eco"
    COMFORT = "comfort"
    ABSENT = "absent"
    NO_SCHEDULE = "no_schedule"
    SCHEDULE_COMFORT = "schedule_comfort"
    SCHEDULE_ECO = "schedule_eco"
    OPTIMUM_START = "optimum_start"
    USAGE_ACTIVE = "usage_active"
    USAGE_IDLE = "usage_idle"
    SLEEP = "sleep"


# Sources the usage detection may change: the automatic comfort and eco decisions.
AUTO_COMFORT_SOURCES = frozenset(
    {
        SetpointSource.COMFORT,
        SetpointSource.NO_SCHEDULE,
        SetpointSource.SCHEDULE_COMFORT,
        SetpointSource.OPTIMUM_START,
    }
)
AUTO_ECO_SOURCES = frozenset({SetpointSource.ECO, SetpointSource.SCHEDULE_ECO})


@dataclass(frozen=True, slots=True)
class SetpointParams:
    """Room control parameters."""

    default_comfort: float = 21.0
    default_eco: float = 18.0
    vacation_temp: float = 15.0
    frost_temp: float = 7.0
    window_temp: float = 12.0
    boost_temp: float = 24.0
    boost_duration: timedelta = timedelta(minutes=30)
    override_duration: timedelta = timedelta(hours=3)
    write_interval: timedelta = timedelta(minutes=15)
    compensation_max: float = 3.0
    compensation_smoothing: timedelta = timedelta(hours=1)
    duty_cycle_limit: float = 80.0
    force_manual_mode: bool = True
    adopt_trv_changes: bool = True
    optimum_start: bool = True
    optimum_start_max_lead: timedelta = timedelta(hours=3)
    usage_hold: timedelta = timedelta(minutes=30)
    usage_in_eco: bool = True


@dataclass(slots=True)
class TrvState:
    """What was last written to one thermostat."""

    last_written: float | None = None
    last_write_at: datetime | None = None
    offset: float | None = None
    offset_at: datetime | None = None


@dataclass(slots=True)
class RoomRuntime:
    """User settings and runtime state of one room (persisted)."""

    comfort: float
    eco: float
    enabled: bool = True
    usage_enabled: bool = True
    last_active_at: datetime | None = None
    override_temp: float | None = None
    override_until: datetime | None = None
    boost_until: datetime | None = None
    boost_temp: float | None = None
    last_schedule_on: bool | None = None
    last_target: float | None = None
    last_source: SetpointSource | None = None
    trvs: dict[str, TrvState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "comfort": self.comfort,
            "eco": self.eco,
            "enabled": self.enabled,
            "usage_enabled": self.usage_enabled,
            "last_active_at": _iso(self.last_active_at),
            "override_temp": self.override_temp,
            "override_until": _iso(self.override_until),
            "boost_until": _iso(self.boost_until),
            "boost_temp": self.boost_temp,
            "trvs": {
                entity_id: {
                    "last_written": s.last_written,
                    "last_write_at": _iso(s.last_write_at),
                    "offset": s.offset,
                    "offset_at": _iso(s.offset_at),
                }
                for entity_id, s in self.trvs.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], params: SetpointParams) -> RoomRuntime:
        """Restore, falling back to defaults."""
        runtime = cls(
            comfort=_float(data.get("comfort"), params.default_comfort),
            eco=_float(data.get("eco"), params.default_eco),
            enabled=bool(data.get("enabled", True)),
            usage_enabled=bool(data.get("usage_enabled", True)),
            last_active_at=_parse(data.get("last_active_at")),
            override_temp=_float(data.get("override_temp"), None),
            override_until=_parse(data.get("override_until")),
            boost_until=_parse(data.get("boost_until")),
            boost_temp=_float(data.get("boost_temp"), None),
        )
        for entity_id, trv in (data.get("trvs") or {}).items():
            runtime.trvs[entity_id] = TrvState(
                last_written=_float(trv.get("last_written"), None),
                last_write_at=_parse(trv.get("last_write_at")),
                offset=_float(trv.get("offset"), None),
                offset_at=_parse(trv.get("offset_at")),
            )
        return runtime


@dataclass(frozen=True, slots=True)
class SetpointContext:
    """Inputs for the setpoint decision of one room."""

    now: datetime
    mode: OperatingMode
    vacation_active: bool
    present: bool | None
    schedule_on: bool | None
    next_schedule_on: datetime | None
    window_open: bool
    room_temperature: float | None
    heat_rate: float | None  # learned K/h
    dead_time: timedelta | None
    forecast_drop: bool = False
    activity: bool | None = None  # None: the room has no activity sensors
    sleeping: bool = False  # night setback for the whole home


@dataclass(frozen=True, slots=True)
class RoomSetpoint:
    """Result of the setpoint decision."""

    room_id: str
    target: float
    source: SetpointSource
    changed: bool
    override_until: datetime | None
    boost_until: datetime | None
    optimum_start_lead: timedelta | None
    room_active: bool | None = None


@dataclass(frozen=True, slots=True)
class TrvInput:
    """Current state of one thermostat."""

    entity_id: str
    available: bool
    current_target: float | None
    current_temperature: float | None
    hvac_mode: str | None


@dataclass(frozen=True, slots=True)
class TrvCommand:
    """A write to a thermostat."""

    entity_id: str
    temperature: float
    set_heat_mode: bool


def clamp_temperature(value: float) -> float:
    """Limit to the thermostat range."""
    return min(max(value, MIN_TEMPERATURE), MAX_TEMPERATURE)


def round_half(value: float) -> float:
    """Round to the 0.5 K steps of typical thermostats."""
    return math.floor(value * 2 + 0.5) / 2


def optimum_start_lead(
    runtime: RoomRuntime, ctx: SetpointContext, params: SetpointParams
) -> timedelta | None:
    """How long before the next comfort period heating has to start."""
    if not params.optimum_start or ctx.heat_rate is None or ctx.heat_rate <= 0.05:
        return None
    if ctx.room_temperature is None:
        return None
    missing = runtime.comfort - ctx.room_temperature
    if missing <= 0:
        return timedelta(0)
    hours = missing / ctx.heat_rate * OPTIMUM_START_SAFETY
    if ctx.forecast_drop:
        hours *= FORECAST_DROP_FACTOR
    lead = timedelta(hours=hours) + (ctx.dead_time or timedelta(0))
    return min(lead, params.optimum_start_max_lead)


def room_active(runtime: RoomRuntime, ctx: SetpointContext, params: SetpointParams) -> bool | None:
    """Whether the room is in use. None without activity sensors or detection off."""
    if ctx.activity is None or not runtime.usage_enabled:
        return None
    if ctx.activity:
        runtime.last_active_at = ctx.now
        return True
    if runtime.last_active_at is None:
        return False
    return ctx.now - runtime.last_active_at <= params.usage_hold


def compute_setpoint(
    room_id: str, runtime: RoomRuntime, ctx: SetpointContext, params: SetpointParams
) -> RoomSetpoint:
    """Decide the target temperature of a room (highest priority first)."""
    now = ctx.now
    if runtime.boost_until is not None and now >= runtime.boost_until:
        runtime.boost_until = None
        runtime.boost_temp = None
    if runtime.override_until is not None and now >= runtime.override_until:
        runtime.override_until = None
        runtime.override_temp = None
    if (
        ctx.schedule_on is not None
        and runtime.last_schedule_on is not None
        and ctx.schedule_on != runtime.last_schedule_on
    ):
        # A schedule change ends a manual override.
        runtime.override_until = None
        runtime.override_temp = None
    if ctx.schedule_on is not None:
        runtime.last_schedule_on = ctx.schedule_on

    lead: timedelta | None = None
    mode = OperatingMode.VACATION if ctx.vacation_active else ctx.mode

    if ctx.window_open:
        target, source = params.window_temp, SetpointSource.WINDOW
    elif not runtime.enabled:
        target, source = params.frost_temp, SetpointSource.ROOM_OFF
    elif runtime.boost_until is not None:
        target, source = runtime.boost_temp or params.boost_temp, SetpointSource.BOOST
    elif runtime.override_until is not None and runtime.override_temp is not None:
        target, source = runtime.override_temp, SetpointSource.OVERRIDE
    elif mode is OperatingMode.OFF:
        target, source = params.frost_temp, SetpointSource.MODE_OFF
    elif mode is OperatingMode.FROST_PROTECTION:
        target, source = params.frost_temp, SetpointSource.FROST_PROTECTION
    elif mode is OperatingMode.VACATION:
        target, source = params.vacation_temp, SetpointSource.VACATION
    elif mode is OperatingMode.AWAY:
        target, source = runtime.eco, SetpointSource.AWAY
    elif mode is OperatingMode.ECO:
        target, source = runtime.eco, SetpointSource.ECO
    elif mode is OperatingMode.COMFORT:
        target, source = runtime.comfort, SetpointSource.COMFORT
    elif ctx.sleeping:
        # The night beats schedule and usage, but not the modes above.
        target, source = runtime.eco, SetpointSource.SLEEP
    elif ctx.present is False:
        target, source = runtime.eco, SetpointSource.ABSENT
    elif ctx.schedule_on is None:
        target, source = runtime.comfort, SetpointSource.NO_SCHEDULE
    elif ctx.schedule_on:
        target, source = runtime.comfort, SetpointSource.SCHEDULE_COMFORT
    else:
        lead = optimum_start_lead(runtime, ctx, params)
        if (
            lead is not None
            and ctx.next_schedule_on is not None
            and ctx.next_schedule_on > now
            and now >= ctx.next_schedule_on - lead
        ):
            target, source = runtime.comfort, SetpointSource.OPTIMUM_START
        else:
            target, source = runtime.eco, SetpointSource.SCHEDULE_ECO

    active = room_active(runtime, ctx, params)
    if active:
        if source in AUTO_ECO_SOURCES and params.usage_in_eco:
            target, source = runtime.comfort, SetpointSource.USAGE_ACTIVE
        elif source in AUTO_COMFORT_SOURCES:
            source = SetpointSource.USAGE_ACTIVE
    elif active is False and source in AUTO_COMFORT_SOURCES:
        target, source = runtime.eco, SetpointSource.USAGE_IDLE

    target = clamp_temperature(target)
    changed = (
        runtime.last_target is None
        or abs(target - runtime.last_target) >= 0.25
        or source != runtime.last_source
    )
    runtime.last_target = target
    runtime.last_source = source
    return RoomSetpoint(
        room_id=room_id,
        target=target,
        source=source,
        changed=changed,
        override_until=runtime.override_until,
        boost_until=runtime.boost_until,
        optimum_start_lead=lead,
        room_active=active,
    )


def plan_trv(
    state: TrvState,
    trv: TrvInput,
    *,
    target: float,
    target_changed: bool,
    source: SetpointSource,
    room_temperature: float | None,
    compensation: bool,
    now: datetime,
    params: SetpointParams,
    duty_cycle_ok: bool,
) -> tuple[TrvCommand | None, float | None]:
    """Decide whether to write a thermostat.

    Returns (command, manual_temperature). manual_temperature is set when the
    thermostat was changed by hand and should become a room override.
    """
    if not trv.available or trv.current_target is None:
        return None, None

    if compensation and room_temperature is not None and trv.current_temperature is not None:
        raw = trv.current_temperature - room_temperature
        if state.offset is None or state.offset_at is None:
            state.offset = raw
        else:
            dt = (now - state.offset_at).total_seconds()
            tau = params.compensation_smoothing.total_seconds()
            if dt > 0 and tau > 0:
                alpha = 1.0 - math.exp(-dt / tau)
                state.offset += alpha * (raw - state.offset)
        state.offset = min(max(state.offset, -params.compensation_max), params.compensation_max)
        state.offset_at = now
    offset = state.offset if compensation and state.offset is not None else 0.0

    if (
        params.adopt_trv_changes
        and not target_changed
        and source is not SetpointSource.WINDOW
        and state.last_written is not None
        and state.last_write_at is not None
        and now - state.last_write_at > MANUAL_CHANGE_GRACE
        and abs(trv.current_target - state.last_written) >= 0.5
        and trv.current_target > params.window_temp + 0.25
    ):
        state.last_written = trv.current_target
        state.last_write_at = now
        return None, clamp_temperature(round_half(trv.current_target - offset))

    desired = clamp_temperature(round_half(target + offset))
    needs_heat_mode = params.force_manual_mode and trv.hvac_mode == "auto"

    if abs(desired - trv.current_target) < 0.25 and not needs_heat_mode:
        if state.last_written is None:
            state.last_written = trv.current_target
            state.last_write_at = now
        return None, None
    if not duty_cycle_ok:
        return None, None
    due = (
        target_changed
        or needs_heat_mode
        or state.last_write_at is None
        or now - state.last_write_at >= params.write_interval
    )
    if not due:
        return None, None
    state.last_written = desired
    state.last_write_at = now
    return TrvCommand(trv.entity_id, desired, needs_heat_mode), None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _float(value: Any, default: float | None) -> Any:
    return float(value) if isinstance(value, (int, float)) else default
