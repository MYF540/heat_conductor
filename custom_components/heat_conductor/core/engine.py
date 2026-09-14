"""Orchestrates one evaluation.

setpoints -> room demand -> outdoor/forecast -> boiler -> energy -> learning -> thermostat writes
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from .boiler_fsm import BoilerController, BoilerDecision, BoilerInputs
from .demand import DemandSummary, RoomDemand, RoomInput, evaluate_room, summarize
from .energy import EnergyParams, EnergySnapshot, EnergyTracker
from .learning import Learner
from .models import ControlParams, OperatingMode, Reading, RoomKind, RoomStatus
from .outdoor import ExponentialSmoother, OutdoorResult, fuse_outdoor
from .setpoint import (
    RoomRuntime,
    RoomSetpoint,
    SetpointContext,
    SetpointParams,
    TrvCommand,
    TrvInput,
    TrvState,
    compute_setpoint,
    plan_trv,
)
from .stats import DailyRuntime, RuntimeSnapshot

SOLAR_ACTIVE_RATIO = 0.4
FORECAST_DROP = 3.0


@dataclass(frozen=True, slots=True)
class RoomControlInput:
    """Room control inputs of one regulated room."""

    room_id: str
    schedule_on: bool | None = None
    next_schedule_on: datetime | None = None
    trvs: tuple[TrvInput, ...] = ()
    compensation: bool = True
    solar_gain: bool = False


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    """All inputs of one evaluation, read from Home Assistant."""

    now: datetime
    rooms: tuple[RoomInput, ...]
    outdoor_sensors: tuple[Reading, ...]
    weather_temperature: Reading | None
    flow_temperature: Reading | None
    return_temperature: Reading | None
    gas_flow: Reading | None
    gas_meter: Reading | None
    burner_on: bool | None
    relay_on: bool | None
    mode: OperatingMode
    automation_enabled: bool
    actuator_active: bool
    room_control_enabled: bool = False
    vacation_active: bool = False
    present: bool | None = None
    room_controls: tuple[RoomControlInput, ...] = ()
    duty_cycle: Reading | None = None
    flow_setpoint: Reading | None = None
    solar_power: Reading | None = None
    forecast_6h: float | None = None
    forecast_12h: float | None = None


@dataclass(frozen=True, slots=True)
class EngineResult:
    """Outputs of one evaluation."""

    rooms: tuple[RoomDemand, ...]
    demand: DemandSummary
    outdoor: OutdoorResult
    outdoor_smoothed: float | None
    decision: BoilerDecision
    flow_temperature: float | None
    return_temperature: float | None
    spread: float | None
    burner_active: bool | None
    boiler_stats: RuntimeSnapshot
    burner_stats: RuntimeSnapshot | None
    energy: EnergySnapshot
    setpoints: tuple[RoomSetpoint, ...] = ()
    trv_commands: tuple[TrvCommand, ...] = ()
    room_control_active: bool = False
    duty_cycle_ok: bool = True
    solar_ratio: float | None = None
    forecast_6h: float | None = None
    forecast_12h: float | None = None
    manual_overrides: tuple[str, ...] = field(default=())

    def room(self, room_id: str) -> RoomDemand | None:
        """Return the evaluated room with the given id."""
        return next((r for r in self.rooms if r.room_id == room_id), None)

    def setpoint(self, room_id: str) -> RoomSetpoint | None:
        """Return the setpoint decision of a room."""
        return next((s for s in self.setpoints if s.room_id == room_id), None)


class HeatingEngine:
    """Stateful evaluation pipeline."""

    def __init__(
        self,
        params: ControlParams,
        energy_params: EnergyParams | None = None,
        setpoint_params: SetpointParams | None = None,
        solar_reference: float = 0.0,
    ) -> None:
        self.params = params
        self.setpoint_params = setpoint_params or SetpointParams()
        self.solar_reference = solar_reference
        self.boiler = BoilerController(params)
        self.outdoor_smoother = ExponentialSmoother(params.outdoor_smoothing)
        self.boiler_stats = DailyRuntime()
        self.burner_stats = DailyRuntime()
        self.energy = EnergyTracker(energy_params or EnergyParams())
        self.room_runtime: dict[str, RoomRuntime] = {}
        self.learner = Learner()

    # -- parameters and room settings --------------------------------------

    def update_params(
        self,
        params: ControlParams,
        energy_params: EnergyParams,
        setpoint_params: SetpointParams,
        solar_reference: float,
    ) -> None:
        """Apply changed parameters without losing state."""
        self.params = params
        self.boiler.params = params
        smoothed, at = self.outdoor_smoother.value, self.outdoor_smoother.updated_at
        self.outdoor_smoother = ExponentialSmoother(params.outdoor_smoothing)
        self.outdoor_smoother.value, self.outdoor_smoother.updated_at = smoothed, at
        self.energy.params = energy_params
        self.setpoint_params = setpoint_params
        self.solar_reference = solar_reference

    def runtime(self, room_id: str) -> RoomRuntime:
        """Settings and runtime state of a room (created with defaults)."""
        if room_id not in self.room_runtime:
            self.room_runtime[room_id] = RoomRuntime(
                comfort=self.setpoint_params.default_comfort,
                eco=self.setpoint_params.default_eco,
            )
        return self.room_runtime[room_id]

    def set_boost(
        self, room_id: str, now: datetime, duration: timedelta | None, temperature: float | None
    ) -> None:
        """Start a boost for a room."""
        runtime = self.runtime(room_id)
        runtime.boost_until = now + (duration or self.setpoint_params.boost_duration)
        runtime.boost_temp = temperature

    def set_override(
        self, room_id: str, now: datetime, temperature: float, duration: timedelta | None = None
    ) -> None:
        """Set a temporary manual target."""
        runtime = self.runtime(room_id)
        runtime.override_temp = temperature
        runtime.override_until = now + (duration or self.setpoint_params.override_duration)

    def clear_override(self, room_id: str) -> None:
        """End boost and manual override."""
        runtime = self.runtime(room_id)
        runtime.override_temp = None
        runtime.override_until = None
        runtime.boost_until = None
        runtime.boost_temp = None

    # -- evaluation ---------------------------------------------------------

    def evaluate(self, snap: EngineSnapshot) -> EngineResult:
        """Run one evaluation."""
        p = self.params
        sp = self.setpoint_params
        now = snap.now

        outdoor = fuse_outdoor(
            snap.outdoor_sensors, snap.weather_temperature, now, p.stale_after, p.outdoor_max_spread
        )
        smoothed = self.outdoor_smoother.update(outdoor.value, now)
        forecast_drop = (
            p.use_forecast
            and snap.forecast_6h is not None
            and outdoor.value is not None
            and snap.forecast_6h < outdoor.value - FORECAST_DROP
        )

        solar_value = snap.solar_power.valid_value(now, p.stale_after) if snap.solar_power else None
        solar_ratio = (
            max(solar_value, 0.0) / self.solar_reference
            if solar_value is not None and self.solar_reference > 0
            else None
        )

        controls = {c.room_id: c for c in snap.room_controls}
        room_control_active = snap.room_control_enabled and snap.automation_enabled
        setpoints: list[RoomSetpoint] = []
        room_inputs: list[RoomInput] = []
        for room in snap.rooms:
            control = controls.get(room.room_id)
            effective: float | None = None
            solar_active = False
            if room.kind is RoomKind.REGULATED and control is not None:
                runtime = self.runtime(room.room_id)
                learner = self.learner.room(room.room_id)
                setpoint = compute_setpoint(
                    room.room_id,
                    runtime,
                    SetpointContext(
                        now=now,
                        mode=snap.mode,
                        vacation_active=snap.vacation_active,
                        present=snap.present,
                        schedule_on=control.schedule_on,
                        next_schedule_on=control.next_schedule_on,
                        window_open=any(room.windows_open),
                        room_temperature=_room_temperature(room, now, p.stale_after),
                        heat_rate=learner.heat_rate_for(outdoor.value),
                        dead_time=learner.dead_time_value(),
                        forecast_drop=forecast_drop,
                    ),
                    sp,
                )
                setpoints.append(setpoint)
                if room_control_active:
                    effective = setpoint.target
                solar_active = (
                    control.solar_gain
                    and solar_ratio is not None
                    and solar_ratio >= SOLAR_ACTIVE_RATIO
                )
            room_inputs.append(replace(room, effective_target=effective, solar_active=solar_active))

        rooms = tuple(evaluate_room(room, now, p) for room in room_inputs)
        demand = summarize(rooms)

        flow = (
            snap.flow_temperature.valid_value(now, p.stale_after) if snap.flow_temperature else None
        )
        ret = (
            snap.return_temperature.valid_value(now, p.stale_after)
            if snap.return_temperature
            else None
        )

        decision = self.boiler.step(
            BoilerInputs(
                now=now,
                demand=demand,
                outdoor_smoothed=smoothed,
                flow_temperature=flow,
                mode=OperatingMode.VACATION if snap.vacation_active else snap.mode,
                automation_enabled=snap.automation_enabled,
                actuator_active=snap.actuator_active,
                relay_on=snap.relay_on,
                forecast_outdoor=snap.forecast_12h,
            )
        )

        energy = self.energy.update(
            now,
            meter=snap.gas_meter,
            flow=snap.gas_flow,
            burner_on=snap.burner_on,
            burner_flow_threshold=p.burner_flow_threshold,
            return_temperature=ret,
            outdoor=outdoor.value,
            max_age=p.stale_after,
        )
        burner = energy.burner_active
        has_burner_source = snap.burner_on is not None or energy.has_gas_source

        # Learning needs real heat: the burner, or the relay when HeatConductor controls it.
        heating = (
            burner
            if burner is not None
            else (decision.request_heat if snap.actuator_active else None)
        )
        for room in rooms:
            if room.kind is not RoomKind.REGULATED:
                continue
            self.learner.room(room.room_id).update(
                now,
                temperature=room.temperature,
                outdoor=outdoor.value,
                valve=room.valve,
                heating=heating,
                window_open=room.status is RoomStatus.WINDOW_OPEN,
            )
        self.learner.boiler.update(now, burner, outdoor.value)
        self.learner.curve.update(
            now,
            outdoor.value,
            snap.flow_setpoint.valid_value(now, p.stale_after) if snap.flow_setpoint else None,
        )

        duty = snap.duty_cycle.valid_value(now, p.stale_after) if snap.duty_cycle else None
        duty_cycle_ok = duty is None or duty <= sp.duty_cycle_limit
        commands: list[TrvCommand] = []
        manual: list[str] = []
        if room_control_active:
            by_id = {r.room_id: r for r in room_inputs}
            for setpoint in setpoints:
                control = controls[setpoint.room_id]
                runtime = self.runtime(setpoint.room_id)
                room_input = by_id[setpoint.room_id]
                external = (
                    room_input.room_temperature.valid_value(now, p.stale_after)
                    if room_input.room_temperature
                    else None
                )
                for trv in control.trvs:
                    state = runtime.trvs.setdefault(trv.entity_id, TrvState())
                    command, manual_temp = plan_trv(
                        state,
                        trv,
                        target=setpoint.target,
                        target_changed=setpoint.changed,
                        source=setpoint.source,
                        room_temperature=external,
                        compensation=control.compensation,
                        now=now,
                        params=sp,
                        duty_cycle_ok=duty_cycle_ok,
                    )
                    if manual_temp is not None:
                        self.set_override(setpoint.room_id, now, manual_temp)
                        manual.append(setpoint.room_id)
                    if command is not None:
                        commands.append(command)

        return EngineResult(
            rooms=rooms,
            demand=demand,
            outdoor=outdoor,
            outdoor_smoothed=smoothed,
            decision=decision,
            flow_temperature=flow,
            return_temperature=ret,
            spread=flow - ret if flow is not None and ret is not None else None,
            burner_active=burner,
            boiler_stats=self.boiler_stats.update(now, decision.request_heat),
            burner_stats=self.burner_stats.update(now, burner) if has_burner_source else None,
            energy=energy,
            setpoints=tuple(setpoints),
            trv_commands=tuple(commands),
            room_control_active=room_control_active,
            duty_cycle_ok=duty_cycle_ok,
            solar_ratio=solar_ratio,
            forecast_6h=snap.forecast_6h,
            forecast_12h=snap.forecast_12h,
            manual_overrides=tuple(manual),
        )

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize persistent state."""
        return {
            "boiler": self.boiler.to_dict(),
            "outdoor_smoothed": self.outdoor_smoother.value,
            "outdoor_smoothed_at": (
                self.outdoor_smoother.updated_at.isoformat()
                if self.outdoor_smoother.updated_at
                else None
            ),
            "boiler_stats": self.boiler_stats.to_dict(),
            "burner_stats": self.burner_stats.to_dict(),
            "energy": self.energy.to_dict(),
            "rooms": {room_id: runtime.to_dict() for room_id, runtime in self.room_runtime.items()},
            "learning": self.learner.to_dict(),
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore state saved by to_dict."""
        self.boiler.restore(data.get("boiler", {}))
        value = data.get("outdoor_smoothed")
        at = data.get("outdoor_smoothed_at")
        if isinstance(value, (int, float)) and isinstance(at, str):
            try:
                self.outdoor_smoother.updated_at = datetime.fromisoformat(at)
                self.outdoor_smoother.value = float(value)
            except ValueError:
                pass
        self.boiler_stats.restore(data.get("boiler_stats", {}))
        self.burner_stats.restore(data.get("burner_stats", {}))
        self.energy.restore(data.get("energy", {}))
        self.room_runtime = {
            room_id: RoomRuntime.from_dict(room, self.setpoint_params)
            for room_id, room in (data.get("rooms") or {}).items()
        }
        self.learner = Learner.from_dict(data.get("learning"))


def _room_temperature(room: RoomInput, now: datetime, max_age: timedelta) -> float | None:
    if room.room_temperature is not None:
        value = room.room_temperature.valid_value(now, max_age)
        if value is not None:
            return value
    values = [
        v for r in room.thermostat_temperatures if (v := r.valid_value(now, max_age)) is not None
    ]
    return sum(values) / len(values) if values else None
