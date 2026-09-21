"""Orchestrates one evaluation.

setpoints -> room demand -> outdoor/forecast -> boiler -> energy -> learning -> thermostat writes
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from .boiler_fsm import BoilerController, BoilerDecision, BoilerInputs
from .curve_advice import CurveRoomSample
from .demand import DemandSummary, RoomDemand, RoomInput, evaluate_room, summarize
from .diagnosis import BoilerDiagnosis, DiagnosisTracker
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
from .sleep import SleepParams, SleepState, SleepTracker
from .stats import DailyRuntime, RuntimeSnapshot
from .vacation import AutoVacation, VacationParams

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
    activity: bool | None = None  # None: the room has no activity sensors
    curve_reference: bool = True  # counts for the heating curve suggestion


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
    learned_schedule_enabled: bool = False
    vacation_active: bool = False
    present: bool | None = None
    room_controls: tuple[RoomControlInput, ...] = ()
    duty_cycle: Reading | None = None
    flow_setpoint: Reading | None = None
    solar_power: Reading | None = None
    forecast_6h: float | None = None
    forecast_12h: float | None = None
    relay_feedback: bool | None = None
    burner_lock: Reading | None = None
    boiler_winter_mode: bool | None = None
    pump_on: bool | None = None
    boiler_flow_temperature: Reading | None = None
    boiler_return_temperature: Reading | None = None
    sleep_sensor: bool | None = None


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
    learned_schedule_on: bool | None = None
    vacation_active: bool = False
    auto_vacation_active: bool = False
    sleep: SleepState = field(default_factory=SleepState)
    duty_cycle_ok: bool = True
    solar_ratio: float | None = None
    forecast_6h: float | None = None
    forecast_12h: float | None = None
    manual_overrides: tuple[str, ...] = field(default=())
    diagnosis: BoilerDiagnosis = field(default_factory=BoilerDiagnosis)

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
        vacation_params: VacationParams | None = None,
        sleep_params: SleepParams | None = None,
    ) -> None:
        self.params = params
        self.setpoint_params = setpoint_params or SetpointParams()
        self.solar_reference = solar_reference
        self.vacation_params = vacation_params or VacationParams()
        self.auto_vacation = AutoVacation()
        self.diagnosis = DiagnosisTracker()
        self.sleep_params = sleep_params or SleepParams()
        self.sleep = SleepTracker()
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
        vacation_params: VacationParams | None = None,
        sleep_params: SleepParams | None = None,
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
        if vacation_params is not None:
            self.vacation_params = vacation_params
        if sleep_params is not None:
            self.sleep_params = sleep_params

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

        auto_vacation = self.auto_vacation.update(now, snap.present, self.vacation_params)
        vacation = snap.vacation_active or auto_vacation
        sleep = self.sleep.update(now, snap.sleep_sensor, self.learner.night, self.sleep_params)
        # A vacation says nothing about everyday habits, so it is not learned.
        if not vacation and snap.mode is not OperatingMode.VACATION:
            self.learner.presence.update(now, snap.present)
            # Only the sensor teaches the night pattern; windows must not reinforce themselves.
            self.learner.night.update(now, self.sleep.sensor_sleeping)
        learned_on, learned_next = (
            self.learner.presence.schedule_state(now)
            if snap.learned_schedule_enabled
            else (None, None)
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
                # Without its own schedule helper a room may follow the learned one.
                schedule_on, next_schedule_on = (
                    (control.schedule_on, control.next_schedule_on)
                    if control.schedule_on is not None
                    else (learned_on, learned_next)
                )
                setpoint = compute_setpoint(
                    room.room_id,
                    runtime,
                    SetpointContext(
                        now=now,
                        mode=snap.mode,
                        vacation_active=vacation,
                        present=snap.present,
                        schedule_on=schedule_on,
                        next_schedule_on=next_schedule_on,
                        window_open=any(room.windows_open),
                        room_temperature=_room_temperature(room, now, p.stale_after),
                        heat_rate=learner.heat_rate_for(outdoor.value),
                        dead_time=learner.dead_time_value(),
                        forecast_drop=forecast_drop,
                        activity=control.activity,
                        sleeping=sleep.sleeping,
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
                mode=OperatingMode.VACATION if vacation else snap.mode,
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
        boiler_flow = (
            snap.boiler_flow_temperature.valid_value(now, p.stale_after)
            if snap.boiler_flow_temperature
            else None
        )
        boiler_return = (
            snap.boiler_return_temperature.valid_value(now, p.stale_after)
            if snap.boiler_return_temperature
            else None
        )
        diagnosis = self.diagnosis.update(
            now,
            relay_on=snap.relay_on,
            relay_feedback=snap.relay_feedback,
            request_heat=decision.request_heat,
            burner_on=burner,
            burner_lock=snap.burner_lock.valid_value(now, p.stale_after)
            if snap.burner_lock
            else None,
            winter_mode=snap.boiler_winter_mode,
            pump_on=snap.pump_on,
            pipe_flow=flow,
            pipe_return=ret,
            boiler_flow=boiler_flow,
            boiler_return=boiler_return,
        )

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
        curve_rooms = {c.room_id for c in snap.room_controls if c.curve_reference}
        self.learner.curve_advice.update(
            now,
            heating=heating,
            outdoor=outdoor.value,
            flow_setpoint=snap.flow_setpoint.valid_value(now, p.stale_after)
            if snap.flow_setpoint
            else None,
            flow=flow,
            return_temperature=ret,
            pump_on=snap.pump_on,
            rooms=[
                CurveRoomSample(room.room_id, room.temperature, room.target, room.valve)
                for room in rooms
                if room.kind is RoomKind.REGULATED
                and room.status is RoomStatus.OK
                and room.temperature is not None
                and room.target is not None
                and room.valve is not None
                and room.room_id in curve_rooms
            ],
        )
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
            # Without circulation the spread only shows how pipes cool down.
            spread=flow - ret
            if flow is not None and ret is not None and snap.pump_on is not False
            else None,
            burner_active=burner,
            boiler_stats=self.boiler_stats.update(now, decision.request_heat),
            burner_stats=self.burner_stats.update(now, burner) if has_burner_source else None,
            energy=energy,
            setpoints=tuple(setpoints),
            trv_commands=tuple(commands),
            room_control_active=room_control_active,
            learned_schedule_on=learned_on,
            vacation_active=vacation,
            auto_vacation_active=auto_vacation,
            sleep=sleep,
            duty_cycle_ok=duty_cycle_ok,
            solar_ratio=solar_ratio,
            forecast_6h=snap.forecast_6h,
            forecast_12h=snap.forecast_12h,
            manual_overrides=tuple(manual),
            diagnosis=diagnosis,
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
            "auto_vacation": self.auto_vacation.to_dict(),
            "diagnosis": self.diagnosis.to_dict(),
            "sleep": self.sleep.to_dict(),
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
        self.auto_vacation = AutoVacation.from_dict(data.get("auto_vacation"))
        self.diagnosis.restore(data.get("diagnosis"))
        self.sleep.restore(data.get("sleep"))


def _room_temperature(room: RoomInput, now: datetime, max_age: timedelta) -> float | None:
    if room.room_temperature is not None:
        value = room.room_temperature.valid_value(now, max_age)
        if value is not None:
            return value
    values = [
        v for r in room.thermostat_temperatures if (v := r.valid_value(now, max_age)) is not None
    ]
    return sum(values) / len(values) if values else None
