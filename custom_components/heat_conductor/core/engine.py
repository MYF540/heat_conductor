"""Orchestrates one evaluation.

setpoints -> room demand -> outdoor/forecast -> boiler -> energy -> learning -> thermostat writes
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from typing import Any

from .boiler_fsm import BoilerController, BoilerDecision, BoilerInputs
from .curve_advice import CurveRoomSample
from .demand import DemandSummary, RoomDemand, RoomInput, evaluate_room, summarize
from .diagnosis import BoilerDiagnosis, DiagnosisTracker
from .energy import EnergyParams, EnergySnapshot, EnergyTracker
from .learning import Learner
from .models import ControlParams, OperatingMode, Reading, Reason, RoomKind, RoomStatus
from .network import (
    CoHeatEnd,
    HeatNetwork,
    NetworkInputs,
    NetworkParams,
    NetworkRoom,
    NetworkState,
    bundle_room,
    forecast_room,
)
from .outdoor import ExponentialSmoother, OutdoorResult, fuse_outdoor
from .setpoint import (
    COMFORT_PERIOD_SOURCES,
    RoomRuntime,
    RoomSetpoint,
    SetpointContext,
    SetpointParams,
    SetpointSource,
    TrvCommand,
    TrvInput,
    TrvState,
    compute_setpoint,
    plan_trv,
    preheat_lead,
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
    schedule_ends: datetime | None = None  # end of the running comfort period
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
    network_enabled: bool = False
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
    occupancy: str | None = None  # present, expected, away (predictive presence)
    next_arrival: datetime | None = None
    vacation_active: bool = False
    auto_vacation_active: bool = False
    sleep: SleepState = field(default_factory=SleepState)
    duty_cycle_ok: bool = True
    solar_ratio: float | None = None
    forecast_6h: float | None = None
    forecast_12h: float | None = None
    manual_overrides: tuple[str, ...] = field(default=())
    diagnosis: BoilerDiagnosis = field(default_factory=BoilerDiagnosis)
    network: NetworkState = field(default_factory=NetworkState)

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
        network_params: NetworkParams | None = None,
    ) -> None:
        self.params = params
        self.network_params = network_params or NetworkParams()
        self.network = HeatNetwork()
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
        network_params: NetworkParams | None = None,
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
        if network_params is not None:
            self.network_params = network_params

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
        # Predictive presence: the learned pattern predicts, actual presence confirms.
        predictive = snap.learned_schedule_enabled and snap.present is not None
        arrival_now, arrival_next = (
            self.learner.presence.window_starts(now) if predictive else (None, None)
        )
        occupancy = None
        if predictive:
            sp_ = self.setpoint_params
            if snap.present:
                occupancy = "present"
            elif (arrival_now is not None and now < arrival_now + sp_.arrival_grace) or (
                arrival_next is not None and arrival_next - sp_.default_preheat <= now
            ):
                occupancy = "expected"
            else:
                occupancy = "away"

        controls = {c.room_id: c for c in snap.room_controls}
        room_control_active = snap.room_control_enabled and snap.automation_enabled
        night_next = self._next_night(now) if not sleep.sleeping else None
        masked = self.network.masked_rooms(now)
        setpoints: list[RoomSetpoint] = []
        periods: dict[str, tuple[datetime | None, datetime | None, timedelta]] = {}
        room_inputs: list[RoomInput] = []
        for room in snap.rooms:
            control = controls.get(room.room_id)
            effective: float | None = None
            solar_active = False
            if room.kind is RoomKind.REGULATED and control is not None:
                runtime = self.runtime(room.room_id)
                learner = self.learner.room(room.room_id)
                schedule_on, next_schedule_on = control.schedule_on, control.next_schedule_on
                ctx = SetpointContext(
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
                    wake_at=sleep.ends_at,
                    predictive=predictive,
                    arrival_now=arrival_now,
                    arrival_next=arrival_next,
                )
                setpoint = compute_setpoint(room.room_id, runtime, ctx, sp)
                setpoints.append(setpoint)
                periods[room.room_id] = (
                    *_comfort_period(
                        setpoint, control, now, predictive, arrival_next, sleep.ends_at, night_next
                    ),
                    preheat_lead(runtime, ctx, sp),
                )
                if room_control_active:
                    effective = setpoint.target
                solar_active = (
                    control.solar_gain
                    and solar_ratio is not None
                    and solar_ratio >= SOLAR_ACTIVE_RATIO
                )
            room_inputs.append(
                replace(
                    room,
                    effective_target=effective,
                    solar_active=solar_active,
                    ignore_valve=room.room_id in masked,
                )
            )

        rooms = tuple(evaluate_room(room, now, p) for room in room_inputs)
        demand = summarize(rooms)
        by_id = {r.room_id: r for r in room_inputs}

        # Heat network: forecast every room, then decide whether a start should wait.
        np_ = self.network_params
        network_rooms = self._network_rooms(setpoints, rooms, by_id, controls, periods)
        forecasts = {r.room_id: forecast_room(r, now, outdoor.value, np_) for r in network_rooms}
        sink = _open_heating_surface(rooms, by_id)
        sink_needed, sink_learned = self.learner.sink.needed(np_.target_run, np_.default_sink)
        if not snap.network_enabled:
            blocked: str | None = "switch_off"
        elif not room_control_active:
            blocked = "room_control_off"
        elif not snap.actuator_active:
            blocked = "observation_mode"
        else:
            blocked = None
        waiting_for = (
            bundle_room(
                forecasts,
                sink=sink,
                sink_needed=sink_needed,
                co_heating=blocked is None,
                params=np_,
            )
            if snap.network_enabled
            else None
        )

        flow = (
            snap.flow_temperature.valid_value(now, p.stale_after) if snap.flow_temperature else None
        )
        ret = (
            snap.return_temperature.valid_value(now, p.stale_after)
            if snap.return_temperature
            else None
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
                burner_on=burner,
                bundle_wait=np_.bundle_wait if waiting_for is not None else None,
            )
        )
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
            flow_setpoint=snap.flow_setpoint.valid_value(now, p.stale_after)
            if snap.flow_setpoint
            else None,
        )

        network = self.network.step(
            NetworkInputs(
                now=now,
                rooms=network_rooms,
                forecasts=forecasts,
                release=decision.request_heat,
                enabled=snap.network_enabled,
                blocked=blocked,
                duty_cycle=snap.duty_cycle.valid_value(now, p.stale_after)
                if snap.duty_cycle
                else None,
                duty_cycle_limit=sp.duty_cycle_limit,
                pump_on=snap.pump_on,
                flow=boiler_flow if boiler_flow is not None else flow,
                boiler_not_heating=diagnosis.not_heating,
                sink=sink,
                sink_needed=sink_needed,
                sink_learned=sink_learned,
                bundle_room=waiting_for if decision.reason is Reason.BUNDLING else None,
            ),
            np_,
        )
        # The relay as it really is: only a real release teaches the heat sink.
        real_release = (
            snap.relay_on
            if snap.relay_on is not None
            else (decision.request_heat if snap.actuator_active else None)
        )
        self.learner.sink.update(now, burner=burner, release=real_release, sink=sink)
        self.network.kpi.update(
            now,
            burner=burner,
            release=real_release,
            co_heats=network.started if network.executing else 0,
            enabled=snap.network_enabled,
            energy=energy,
        )
        room_temps = {r.room_id: r.temperature for r in rooms}
        for room_id, end in network.ended:
            if end is CoHeatEnd.REACHED and network.executing:
                self.learner.room(room_id).start_overshoot(now, room_temps.get(room_id))

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
                and room.room_id not in masked
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
        co_heated = network.active_rooms() if network.executing else frozenset()
        settling = self.network.masked_rooms(now)
        if room_control_active:
            for setpoint in setpoints:
                control = controls[setpoint.room_id]
                runtime = self.runtime(setpoint.room_id)
                room_input = by_id[setpoint.room_id]
                external = (
                    room_input.room_temperature.valid_value(now, p.stale_after)
                    if room_input.room_temperature
                    else None
                )
                co_heat = setpoint.room_id in co_heated
                toggled = co_heat != runtime.co_heat_written
                for trv in control.trvs:
                    state = runtime.trvs.setdefault(trv.entity_id, TrvState())
                    if toggled:
                        state.restore_target = trv.current_target if co_heat else None
                    command, manual_temp = plan_trv(
                        state,
                        trv,
                        target=np_.opening_temperature if co_heat else setpoint.target,
                        target_changed=setpoint.changed or toggled,
                        source=setpoint.source,
                        room_temperature=external,
                        compensation=control.compensation,
                        now=now,
                        params=sp,
                        duty_cycle_ok=duty_cycle_ok,
                        learn_offset=setpoint.room_id not in settling,
                    )
                    if manual_temp is not None:
                        self.set_override(setpoint.room_id, now, manual_temp)
                        manual.append(setpoint.room_id)
                    if command is not None:
                        commands.append(command)
                if duty_cycle_ok:
                    runtime.co_heat_written = co_heat
        elif duty_cycle_ok:
            # Without room control the thermostats get back what they had before.
            for setpoint in setpoints:
                runtime = self.runtime(setpoint.room_id)
                if not runtime.co_heat_written:
                    continue
                for trv in controls[setpoint.room_id].trvs:
                    state = runtime.trvs.setdefault(trv.entity_id, TrvState())
                    restore = (
                        state.restore_target
                        if state.restore_target is not None
                        else setpoint.target
                    )
                    if trv.available:
                        commands.append(TrvCommand(trv.entity_id, restore, False))
                    state.restore_target = None
                    state.last_written = restore
                    state.last_write_at = now
                runtime.co_heat_written = False

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
            occupancy=occupancy,
            next_arrival=arrival_next,
            vacation_active=vacation,
            auto_vacation_active=auto_vacation,
            sleep=sleep,
            duty_cycle_ok=duty_cycle_ok,
            solar_ratio=solar_ratio,
            forecast_6h=snap.forecast_6h,
            forecast_12h=snap.forecast_12h,
            manual_overrides=tuple(manual),
            diagnosis=diagnosis,
            network=network,
        )

    # -- heat network ---------------------------------------------------------

    def _next_night(self, now: datetime) -> datetime | None:
        """Start of the next night, from the manual window or the learned night."""
        params = self.sleep_params
        if params.window_start is not None and params.window_end is not None:
            start = datetime.combine(now.date(), time(), tzinfo=now.tzinfo) + timedelta(
                minutes=params.window_start
            )
            return start if start > now else start + timedelta(days=1)
        if params.use_learned:
            return self.learner.night.window_starts(now)[1]
        return None

    def _network_rooms(
        self,
        setpoints: list[RoomSetpoint],
        rooms: tuple[RoomDemand, ...],
        inputs: dict[str, RoomInput],
        controls: dict[str, RoomControlInput],
        periods: dict[str, tuple[datetime | None, datetime | None, timedelta]],
    ) -> tuple[NetworkRoom, ...]:
        """What the heat network needs to know about every regulated room."""
        demands = {r.room_id: r for r in rooms}
        result: list[NetworkRoom] = []
        for setpoint in setpoints:
            room_id = setpoint.room_id
            demand, room_input, control = demands[room_id], inputs[room_id], controls[room_id]
            runtime = self.runtime(room_id)
            learner = self.learner.room(room_id)
            comfort_starts, comfort_ends, lead = periods[room_id]
            comfort_like = setpoint.source in COMFORT_PERIOD_SOURCES
            eligible = (
                runtime.enabled
                and runtime.co_heat_enabled
                and bool(control.trvs)
                and demand.temperature is not None
                and demand.status in (RoomStatus.OK, RoomStatus.DEGRADED)
                and not room_input.solar_active
                and (comfort_like or comfort_starts is not None)
            )
            result.append(
                NetworkRoom(
                    room_id=room_id,
                    temperature=demand.temperature,
                    target=setpoint.target,
                    comfort=runtime.comfort,
                    eligible=eligible,
                    comfort_like=comfort_like,
                    comfort_starts=comfort_starts,
                    comfort_ends=comfort_ends,
                    preheat_lead=lead,
                    radiators=max(len(room_input.valves), len(control.trvs), 1),
                    valve=demand.valve,
                    demanding=demand.deficit is not None and demand.deficit > 0,
                    tau=learner.cooling_tau_value(),
                    overshoot=learner.overshoot_value(),
                )
            )
        return tuple(result)

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
            "network": self.network.to_dict(),
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
        self.network.restore(data.get("network"))


def _comfort_period(
    setpoint: RoomSetpoint,
    control: RoomControlInput,
    now: datetime,
    predictive: bool,
    arrival_next: datetime | None,
    wake_at: datetime | None,
    night_next: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """(when comfort begins for an eco room, when it ends for a comfort room)."""
    source = setpoint.source
    if source in COMFORT_PERIOD_SOURCES:
        ends = [
            t
            for t in (control.schedule_ends if control.schedule_on else None, night_next)
            if t is not None and t > now
        ]
        return None, min(ends) if ends else None
    if setpoint.room_active is False:
        return None, None  # an unused room would stay in eco anyway
    if source is SetpointSource.SCHEDULE_ECO:
        starts = control.next_schedule_on
    elif source is SetpointSource.ABSENT and predictive:
        starts = arrival_next
    elif source is SetpointSource.SLEEP:
        starts = wake_at
    else:
        starts = None
    return (starts if starts is not None and starts > now else None), None


def _open_heating_surface(
    rooms: tuple[RoomDemand, ...], inputs: dict[str, RoomInput]
) -> float | None:
    """Open valves in fully open radiators (a room's mean times its valve count)."""
    values = [
        room.valve * max(len(inputs[room.room_id].valves), 1)
        for room in rooms
        if room.valve is not None
    ]
    return sum(values) if values else None


def _room_temperature(room: RoomInput, now: datetime, max_age: timedelta) -> float | None:
    if room.room_temperature is not None:
        value = room.room_temperature.valid_value(now, max_age)
        if value is not None:
            return value
    values = [
        v for r in room.thermostat_temperatures if (v := r.valid_value(now, max_age)) is not None
    ]
    return sum(values) / len(values) if values else None
