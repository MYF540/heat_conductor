"""Heat network: use every release for as many rooms as makes sense.

The relay only releases heat, and the boiler cannot go below its minimum output.
With few open radiators the water overheats within minutes and the burner stops
again. The network planner therefore looks at all rooms together:

- rooms that would soon need heat themselves are heated along ("co-heating"),
- more rooms are opened while the open heating surface is smaller than what the
  boiler needs for a sensible burner run (learned from the burner runs),
- rooms whose comfort period begins soon are preheated in the same release,
- after a release the heat stored in boiler and pipes goes into open rooms,
- a start waits a while when another room will need heat soon.

Co-heating opens the thermostats of a room with a high target (the opening
temperature) and writes the normal target back once the room reached its goal
minus the learned after-heating of its radiators. Co-heated rooms never count as
demand, so an open valve cannot keep a release alive.

Rooms cool down towards the outdoor temperature with the learned time constant
tau: T(t) = T_out + (T - T_out) * exp(-t / tau).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
import math
from typing import Any

from .energy import EnergySnapshot

# A co-heat must add at least this much to be worth two radio commands.
MIN_GAIN = 0.3
DEFAULT_TAU = 40.0  # h, a well insulated room, used until tau is learned
DEFAULT_OVERSHOOT = 0.3  # K after-heating of the radiators until learned
MAX_DURATION = timedelta(hours=2)
RESTART_GAP = timedelta(minutes=15)
# Valves close slowly and report late: keep ignoring them after a co-heat.
VALVE_SETTLE = timedelta(minutes=15)
# Starting a co-heat needs this much reserve below the duty cycle limit.
DUTY_RESERVE = 20.0
# The flow must be this much warmer than the rooms for residual heat to be worth it.
RESIDUAL_MARGIN = 5.0
# A room whose comfort ends sooner is not heated beyond its need.
SINK_MIN_COMFORT_LEFT = timedelta(minutes=60)
SHORT_RUN = timedelta(minutes=3)
KPI_DAYS = 120


class CoHeatReason(StrEnum):
    """Why a room is heated along."""

    SOON = "soon"  # would need heat within the horizon
    PREHEAT = "preheat"  # its comfort period begins soon
    SINK = "sink"  # the boiler needs a larger heat sink


class CoHeatEnd(StrEnum):
    """Why co-heating of a room ended."""

    REACHED = "reached"
    RELEASE_ENDED = "release_ended"
    INELIGIBLE = "ineligible"
    MAX_DURATION = "max_duration"
    STOPPED = "stopped"  # switch, room control, observation mode or restart


class NetworkPhase(StrEnum):
    """What the network is doing right now."""

    IDLE = "idle"
    RELEASE = "release"
    RESIDUAL = "residual"


_PRIORITY = {CoHeatReason.SOON: 0, CoHeatReason.PREHEAT: 0, CoHeatReason.SINK: 1}


@dataclass(frozen=True, slots=True)
class NetworkParams:
    """Settings of the heat network."""

    opening_temperature: float = 25.0
    reserve: float = 1.0
    horizon: timedelta = timedelta(hours=3)
    preheat_pull: timedelta = timedelta(minutes=60)
    residual_use: bool = True
    residual_max: timedelta = timedelta(minutes=15)
    target_run: timedelta = timedelta(minutes=10)
    default_sink: float = 4.0
    bundle_wait: timedelta = timedelta(minutes=30)
    max_per_day: int = 6


@dataclass(frozen=True, slots=True)
class NetworkRoom:
    """What the planner needs to know about one regulated room."""

    room_id: str
    temperature: float | None
    target: float
    comfort: float
    eligible: bool  # may be co-heated at all (switch, window, sun, target source)
    comfort_like: bool  # the room is in a comfort period
    comfort_starts: datetime | None = None  # eco room: when comfort begins
    comfort_ends: datetime | None = None  # comfort room: when it ends, if known
    preheat_lead: timedelta = timedelta(0)
    radiators: int = 1
    valve: float | None = None
    demanding: bool = False  # below its target: its own thermostat is heating
    tau: float | None = None  # learned cooling constant in hours
    overshoot: float | None = None  # learned after-heating in K


@dataclass(frozen=True, slots=True)
class RoomForecast:
    """Prediction and possible co-heat goals of one room."""

    room_id: str
    temperature: float | None
    need_in: timedelta | None  # until the room needs heat (0 = now)
    soon_goal: float | None
    preheat_goal: float | None
    sink_goal: float | None
    min_gain: float
    overshoot: float
    radiators: int
    valve: float | None
    demanding: bool
    eligible: bool

    def goal(self, reason: CoHeatReason) -> float | None:
        """Goal temperature for a co-heat of the given kind."""
        if reason is CoHeatReason.SOON:
            return self.soon_goal
        if reason is CoHeatReason.PREHEAT:
            return self.preheat_goal
        return self.sink_goal

    def candidate(self) -> CoHeatReason | None:
        """Kind of co-heat worth starting now, if any."""
        if not self.eligible or self.demanding or self.temperature is None:
            return None
        for reason in (CoHeatReason.SOON, CoHeatReason.PREHEAT, CoHeatReason.SINK):
            goal = self.goal(reason)
            if goal is not None and goal - self.temperature >= self.min_gain:
                return reason
        return None


@dataclass(frozen=True, slots=True)
class NetworkInputs:
    """Everything the network needs for one step."""

    now: datetime
    rooms: tuple[NetworkRoom, ...]
    forecasts: dict[str, RoomForecast]
    release: bool  # heat is released (virtually in observation mode)
    enabled: bool  # switch "heat network"
    blocked: str | None  # why co-heating is only previewed, None = it is executed
    duty_cycle: float | None = None
    duty_cycle_limit: float = 80.0
    pump_on: bool | None = None
    flow: float | None = None  # boiler flow if known, else pipe flow
    boiler_not_heating: bool = False
    sink: float | None = None  # open heating surface in fully open radiators
    sink_needed: float = 4.0
    sink_learned: bool = False
    bundle_room: str | None = None


@dataclass(frozen=True, slots=True)
class RoomPlan:
    """Network state of one room for display."""

    room_id: str
    need_in: timedelta | None
    candidate: CoHeatReason | None
    active: bool
    reason: CoHeatReason | None
    goal: float | None
    since: datetime | None
    last_end: CoHeatEnd | None
    today: int


@dataclass(frozen=True, slots=True)
class NetworkState:
    """Result of one step."""

    enabled: bool = False
    executing: bool = False
    blocked: str | None = None
    phase: NetworkPhase = NetworkPhase.IDLE
    sink: float | None = None
    sink_needed: float = 4.0
    sink_learned: bool = False
    rooms: tuple[RoomPlan, ...] = ()
    next_need_room: str | None = None
    next_need_at: datetime | None = None
    bundle_room: str | None = None
    started: int = 0
    ended: tuple[tuple[str, CoHeatEnd], ...] = ()

    def active_rooms(self) -> frozenset[str]:
        """Rooms that are (or would be) co-heated right now."""
        return frozenset(r.room_id for r in self.rooms if r.active)

    def room(self, room_id: str) -> RoomPlan | None:
        """Plan of one room."""
        return next((r for r in self.rooms if r.room_id == room_id), None)

    def as_dict(self) -> dict[str, Any]:
        """For the panel."""
        return {
            "enabled": self.enabled,
            "executing": self.executing,
            "blocked": self.blocked,
            "phase": self.phase.value,
            "sink": round(self.sink, 2) if self.sink is not None else None,
            "sink_needed": round(self.sink_needed, 2),
            "sink_learned": self.sink_learned,
            "next_need_room": self.next_need_room,
            "next_need_at": self.next_need_at.isoformat() if self.next_need_at else None,
            "bundle_room": self.bundle_room,
            "rooms": [
                {
                    "room_id": r.room_id,
                    "need_in": _minutes(r.need_in),
                    "candidate": r.candidate.value if r.candidate else None,
                    "active": r.active,
                    "reason": r.reason.value if r.reason else None,
                    "goal": round(r.goal, 1) if r.goal is not None else None,
                    "since": r.since.isoformat() if r.since else None,
                    "last_end": r.last_end.value if r.last_end else None,
                    "today": r.today,
                }
                for r in self.rooms
            ],
        }


def _minutes(value: timedelta | None) -> int | None:
    return round(value.total_seconds() / 60) if value is not None else None


# -- room model ----------------------------------------------------------------


def need_in(
    temperature: float | None, trigger: float, outdoor: float | None, tau: float
) -> timedelta | None:
    """Time until the room cools down to `trigger` (None: not within reach)."""
    if temperature is None or outdoor is None:
        return None
    if temperature <= trigger:
        return timedelta(0)
    if trigger <= outdoor:
        return None
    return timedelta(hours=tau * math.log((temperature - outdoor) / (trigger - outdoor)))


def hold_temperature(trigger: float, outdoor: float, tau: float, duration: timedelta) -> float:
    """Temperature that lasts `duration` before the room cools down to `trigger`."""
    hours = duration.total_seconds() / 3600.0
    return outdoor + (trigger - outdoor) * math.exp(hours / tau)


def forecast_room(
    room: NetworkRoom, now: datetime, outdoor: float | None, params: NetworkParams
) -> RoomForecast:
    """When a room needs heat and how far co-heating could take it."""
    tau = room.tau if room.tau is not None and room.tau > 0 else DEFAULT_TAU
    overshoot = room.overshoot if room.overshoot is not None else DEFAULT_OVERSHOOT
    temperature = room.temperature

    need = need_in(temperature, room.target, outdoor, tau)
    if room.comfort_like:
        if need is not None and room.comfort_ends is not None and now + need >= room.comfort_ends:
            need = None  # stays warm enough until its comfort period ends
    elif room.comfort_starts is not None:
        heat_from = max(room.comfort_starts - room.preheat_lead - now, timedelta(0))
        need = heat_from if need is None else min(need, heat_from)

    soon_goal = preheat_goal = sink_goal = None
    if room.eligible and temperature is not None:
        if room.comfort_like:
            cap = room.target + params.reserve
            left = params.horizon
            if room.comfort_ends is not None:
                left = min(left, room.comfort_ends - now)
            if outdoor is not None and left > timedelta(0) and room.target > outdoor:
                soon_goal = min(hold_temperature(room.target, outdoor, tau, left), cap)
            if room.comfort_ends is None or room.comfort_ends - now >= SINK_MIN_COMFORT_LEFT:
                sink_goal = cap
        elif room.comfort_starts is not None:
            heat_from = room.comfort_starts - room.preheat_lead
            if heat_from - params.preheat_pull <= now < room.comfort_starts:
                preheat_goal = room.comfort

    return RoomForecast(
        room_id=room.room_id,
        temperature=temperature,
        need_in=need,
        soon_goal=soon_goal,
        preheat_goal=preheat_goal,
        sink_goal=sink_goal,
        min_gain=max(MIN_GAIN, overshoot),
        overshoot=overshoot,
        radiators=max(room.radiators, 1),
        valve=room.valve,
        demanding=room.demanding,
        eligible=room.eligible,
    )


def _order(item: tuple[RoomForecast, CoHeatReason]) -> tuple[int, float]:
    forecast, reason = item
    need = forecast.need_in.total_seconds() if forecast.need_in is not None else math.inf
    return _PRIORITY[reason], need


def bundle_room(
    forecasts: dict[str, RoomForecast],
    *,
    sink: float | None,
    sink_needed: float,
    co_heating: bool,
    params: NetworkParams,
) -> str | None:
    """Room worth waiting for before a start, if the heat sink is too small now."""
    if params.bundle_wait <= timedelta(0):
        return None
    potential = sink or 0.0
    if co_heating:
        for forecast in forecasts.values():
            if forecast.candidate() is not None:
                potential += forecast.radiators * (1.0 - min(forecast.valve or 0.0, 1.0))
    if potential >= sink_needed:
        return None
    joining = [
        f
        for f in forecasts.values()
        if not f.demanding
        and f.need_in is not None
        and timedelta(0) < f.need_in <= params.bundle_wait
    ]
    if not joining:
        return None
    return min(joining, key=lambda f: f.need_in or timedelta(0)).room_id


# -- the network -----------------------------------------------------------------


@dataclass(slots=True)
class _Active:
    reason: CoHeatReason
    since: datetime
    goal: float


class HeatNetwork:
    """Co-heating state of all rooms."""

    def __init__(self) -> None:
        self.active: dict[str, _Active] = {}
        self.executing = False
        self.phase = NetworkPhase.IDLE
        self._residual_since: datetime | None = None
        self._counts: dict[str, int] = {}
        self._count_day: date | None = None
        self._last_end: dict[str, tuple[datetime, CoHeatEnd]] = {}
        self._masked_until: dict[str, datetime] = {}
        self.kpi = KpiTracker()

    def masked_rooms(self, now: datetime) -> frozenset[str]:
        """Rooms whose valves must not count as demand."""
        masked = {rid for rid, until in self._masked_until.items() if now < until}
        if self.executing:
            masked.update(self.active)
        return frozenset(masked)

    def step(self, inp: NetworkInputs, params: NetworkParams) -> NetworkState:
        """Start and stop co-heating."""
        now = inp.now
        if self._count_day != now.date():
            self._count_day = now.date()
            self._counts.clear()
        executing = inp.blocked is None
        ended: list[tuple[str, CoHeatEnd]] = []
        if executing != self.executing:
            ended.extend(self._end_all(now, CoHeatEnd.STOPPED))
            self.executing = executing

        self.phase = self._phase(inp, params)
        rooms = {r.room_id: r for r in inp.rooms}

        for room_id, active in list(self.active.items()):
            forecast = inp.forecasts.get(room_id)
            room = rooms.get(room_id)
            reason: CoHeatEnd | None = None
            if self.phase is NetworkPhase.IDLE:
                reason = CoHeatEnd.RELEASE_ENDED
            elif forecast is None or room is None or not room.eligible:
                reason = CoHeatEnd.INELIGIBLE
            elif now - active.since >= MAX_DURATION:
                reason = CoHeatEnd.MAX_DURATION
            else:
                goal = forecast.goal(active.reason)
                if goal is None:
                    reason = CoHeatEnd.INELIGIBLE
                else:
                    active.goal = goal
                    if (
                        forecast.temperature is not None
                        and forecast.temperature >= goal - forecast.overshoot
                    ):
                        reason = CoHeatEnd.REACHED
            if reason is not None:
                self._end(room_id, now, reason)
                ended.append((room_id, reason))

        started = 0
        if self.phase is not NetworkPhase.IDLE and self._may_start(inp):
            sink = self._sink_estimate(inp)
            candidates = sorted(
                (
                    (forecast, reason)
                    for forecast in inp.forecasts.values()
                    if forecast.room_id not in self.active
                    and (reason := forecast.candidate()) is not None
                    and self._allowed(forecast.room_id, now, params)
                ),
                key=_order,
            )
            for forecast, reason in candidates:
                if reason is CoHeatReason.SINK and sink >= inp.sink_needed:
                    continue
                goal = forecast.goal(reason)
                assert goal is not None
                self.active[forecast.room_id] = _Active(reason, now, goal)
                sink += forecast.radiators * (1.0 - min(forecast.valve or 0.0, 1.0))
                started += 1
                if executing:
                    self._counts[forecast.room_id] = self._counts.get(forecast.room_id, 0) + 1

        return self._state(inp, started, tuple(ended))

    # -- helpers ---------------------------------------------------------------

    def _phase(self, inp: NetworkInputs, params: NetworkParams) -> NetworkPhase:
        if inp.boiler_not_heating:
            self._residual_since = None
            return NetworkPhase.IDLE
        if inp.release:
            self._residual_since = None
            return NetworkPhase.RELEASE
        if self.phase is NetworkPhase.IDLE or not params.residual_use:
            self._residual_since = None
            return NetworkPhase.IDLE
        if self._residual_since is None:
            self._residual_since = inp.now
        if inp.now - self._residual_since >= params.residual_max or not self._residual_heat(inp):
            self._residual_since = None
            return NetworkPhase.IDLE
        return NetworkPhase.RESIDUAL

    def _residual_heat(self, inp: NetworkInputs) -> bool:
        """Whether boiler and pipes still hold heat worth moving into the rooms."""
        if inp.pump_on is False:
            return False
        if inp.flow is None:
            return True
        temperatures = [
            f.temperature
            for rid, f in inp.forecasts.items()
            if f.temperature is not None and (rid in self.active or not self.active)
        ]
        warmest = max(temperatures, default=20.0)
        return inp.flow >= warmest + RESIDUAL_MARGIN

    def _may_start(self, inp: NetworkInputs) -> bool:
        if inp.blocked is not None:
            return True  # preview: nothing is written
        return inp.duty_cycle is None or inp.duty_cycle <= inp.duty_cycle_limit - DUTY_RESERVE

    def _allowed(self, room_id: str, now: datetime, params: NetworkParams) -> bool:
        last = self._last_end.get(room_id)
        if last is not None and now - last[0] < RESTART_GAP:
            return False
        return not self.executing or self._counts.get(room_id, 0) < params.max_per_day

    def _sink_estimate(self, inp: NetworkInputs) -> float:
        """Open heating surface, counting co-heated rooms as fully open."""
        total = 0.0
        for forecast in inp.forecasts.values():
            if forecast.room_id in self.active:
                total += forecast.radiators
            else:
                total += forecast.radiators * min(forecast.valve or 0.0, 1.0)
        return total

    def _end(self, room_id: str, now: datetime, reason: CoHeatEnd) -> None:
        self.active.pop(room_id, None)
        self._last_end[room_id] = (now, reason)
        if self.executing:
            self._masked_until[room_id] = now + VALVE_SETTLE

    def _end_all(self, now: datetime, reason: CoHeatEnd) -> list[tuple[str, CoHeatEnd]]:
        ended = [(room_id, reason) for room_id in self.active]
        for room_id, _ in ended:
            self._end(room_id, now, reason)
        return ended

    def _state(
        self, inp: NetworkInputs, started: int, ended: tuple[tuple[str, CoHeatEnd], ...]
    ) -> NetworkState:
        now = inp.now
        plans = []
        next_room, next_at = None, None
        for forecast in inp.forecasts.values():
            active = self.active.get(forecast.room_id)
            last = self._last_end.get(forecast.room_id)
            plans.append(
                RoomPlan(
                    room_id=forecast.room_id,
                    need_in=forecast.need_in,
                    candidate=forecast.candidate(),
                    active=active is not None,
                    reason=active.reason if active else None,
                    goal=active.goal if active else None,
                    since=active.since if active else None,
                    last_end=last[1] if last else None,
                    today=self._counts.get(forecast.room_id, 0),
                )
            )
            if forecast.need_in is not None and (
                next_at is None or now + forecast.need_in < next_at
            ):
                next_room, next_at = forecast.room_id, now + forecast.need_in
        self._masked_until = {k: v for k, v in self._masked_until.items() if now < v}
        return NetworkState(
            enabled=inp.enabled,
            executing=self.executing,
            blocked=inp.blocked,
            phase=self.phase,
            sink=inp.sink,
            sink_needed=inp.sink_needed,
            sink_learned=inp.sink_learned,
            rooms=tuple(plans),
            next_need_room=next_room,
            next_need_at=next_at,
            bundle_room=inp.bundle_room,
            started=started,
            ended=ended,
        )

    # -- persistence -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize. Running co-heats are not kept: a restart ends them."""
        return {
            "counts": self._counts,
            "count_day": self._count_day.isoformat() if self._count_day else None,
            "kpi": self.kpi.to_dict(),
        }

    def restore(self, data: dict[str, Any] | None) -> None:
        """Restore state saved by to_dict."""
        if not data:
            return
        counts = data.get("counts")
        if isinstance(counts, dict):
            self._counts = {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}
        day = data.get("count_day")
        if isinstance(day, str):
            try:
                self._count_day = date.fromisoformat(day)
            except ValueError:
                self._count_day = None
        self.kpi = KpiTracker.from_dict(data.get("kpi"))


# -- learning the needed heat sink -------------------------------------------------


SINK_DECAY = 0.97
SINK_MIN_SAMPLES = 6
SINK_MIN_SPREAD = 0.5  # radiators, standard deviation of the observed sinks
SINK_POINTS = 150


class SinkLearner:
    """How much open heating surface the boiler needs for a burner run of a given length.

    While the burner is on, the boiler delivers at least its minimum output and the
    open radiators take some of it away. The rest heats the water until the boiler
    stops. So the inverse run length falls linearly with the open heating surface:
    1/run = a - b * sink. Every burner run within a release (except the first,
    which also heats up the cold water) is one sample; older runs fade out.
    """

    def __init__(self) -> None:
        self.n = 0.0
        self.sx = 0.0
        self.sy = 0.0
        self.sxx = 0.0
        self.sxy = 0.0
        self.samples = 0
        self.points: deque[tuple[float, float]] = deque(maxlen=SINK_POINTS)
        self._runs_in_release = 0
        self._last_burner: bool | None = None
        self._run_start: datetime | None = None
        self._sink_sum = 0.0
        self._sink_time = 0.0
        self._last: datetime | None = None
        self._last_sink: float | None = None

    def update(
        self, now: datetime, *, burner: bool | None, release: bool | None, sink: float | None
    ) -> None:
        """Feed burner state, release and open heating surface."""
        if release is not True or burner is None:
            self._runs_in_release = 0
            self._run_start = None
            self._last_burner = None if release is not True else burner
            self._last, self._last_sink = now, sink
            return
        if self._run_start is not None and self._last is not None and self._last_sink is not None:
            dt = (now - self._last).total_seconds()
            if 0 < dt <= 600:
                self._sink_sum += self._last_sink * dt
                self._sink_time += dt
        if burner and self._last_burner is False:
            self._runs_in_release += 1
            self._run_start = now
            self._sink_sum = self._sink_time = 0.0
        elif burner and self._last_burner is None:
            self._runs_in_release += 1  # already burning: its start is unknown
        elif not burner and self._last_burner and self._run_start is not None:
            minutes = (now - self._run_start).total_seconds() / 60.0
            if self._runs_in_release >= 2 and self._sink_time > 0 and 0.5 <= minutes <= 240:
                self.add(self._sink_sum / self._sink_time, minutes)
            self._run_start = None
        self._last_burner = burner
        self._last, self._last_sink = now, sink

    def add(self, sink: float, minutes: float) -> None:
        """Add one burner run."""
        y = 1.0 / minutes
        self.n = self.n * SINK_DECAY + 1
        self.sx = self.sx * SINK_DECAY + sink
        self.sy = self.sy * SINK_DECAY + y
        self.sxx = self.sxx * SINK_DECAY + sink * sink
        self.sxy = self.sxy * SINK_DECAY + sink * y
        self.samples += 1
        self.points.append((round(sink, 2), round(minutes, 1)))

    def fit(self) -> tuple[float, float] | None:
        """(a, b) of 1/run = a - b * sink, in 1/min."""
        if self.samples < SINK_MIN_SAMPLES or self.n <= 0:
            return None
        mean_x = self.sx / self.n
        var_x = self.sxx / self.n - mean_x * mean_x
        if var_x < SINK_MIN_SPREAD**2:
            return None
        slope = (self.sxy / self.n - mean_x * self.sy / self.n) / var_x
        intercept = self.sy / self.n - slope * mean_x
        if slope >= 0 or intercept <= 0:
            return None
        return intercept, -slope

    def needed(self, target_run: timedelta, default: float) -> tuple[float, bool]:
        """(open heating surface for the target run length, learned)."""
        fit = self.fit()
        minutes = target_run.total_seconds() / 60.0
        if fit is None or minutes <= 0:
            return default, False
        a, b = fit
        return min(max((a - 1.0 / minutes) / b, 0.5), 30.0), True

    def summary(self, target_run: timedelta, default: float) -> dict[str, Any]:
        """Values for display."""
        fit = self.fit()
        needed, learned = self.needed(target_run, default)
        return {
            "samples": self.samples,
            "a": round(fit[0], 4) if fit else None,
            "b": round(fit[1], 4) if fit else None,
            "needed": round(needed, 2),
            "learned": learned,
            "continuous": round(fit[0] / fit[1], 2) if fit else None,
            "target_run": target_run.total_seconds() / 60.0,
            "points": list(self.points),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "n": self.n,
            "sx": self.sx,
            "sy": self.sy,
            "sxx": self.sxx,
            "sxy": self.sxy,
            "samples": self.samples,
            "points": list(self.points),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SinkLearner:
        """Restore."""
        learner = cls()
        if not data:
            return learner
        for key in ("n", "sx", "sy", "sxx", "sxy"):
            setattr(learner, key, float(data.get(key, 0.0)))
        learner.samples = int(data.get("samples", 0))
        learner.points.extend(tuple(p) for p in data.get("points", []))
        return learner


# -- daily key figures -------------------------------------------------------------


@dataclass(slots=True)
class _Day:
    burner_starts: int = 0
    burner_seconds: float = 0.0
    short_runs: int = 0
    releases: int = 0
    co_heats: int = 0
    enabled_seconds: float = 0.0
    seconds: float = 0.0


@dataclass(slots=True)
class KpiTracker:
    """Daily burner and release figures, to compare days with and without the network."""

    history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=KPI_DAYS))
    day: date | None = None
    today: _Day = field(default_factory=_Day)
    _last: datetime | None = None
    _burner: bool | None = None
    _burner_since: datetime | None = None
    _release: bool | None = None

    def update(
        self,
        now: datetime,
        *,
        burner: bool | None,
        release: bool | None,
        co_heats: int,
        enabled: bool,
        energy: EnergySnapshot | None,
    ) -> None:
        """Feed one evaluation."""
        if self.day is None:
            self.day = now.date()
        elif now.date() != self.day:
            self.history.append(self._record(self.day, self.today, energy, finished=True))
            self.day = now.date()
            self.today = _Day()
        dt = (now - self._last).total_seconds() if self._last is not None else 0.0
        if 0 < dt <= 600:
            self.today.seconds += dt
            if enabled:
                self.today.enabled_seconds += dt
            if self._burner:
                self.today.burner_seconds += dt
        if burner is not None:
            if burner and self._burner is False:
                self.today.burner_starts += 1
                self._burner_since = now
            elif not burner and self._burner and self._burner_since is not None:
                if now - self._burner_since < SHORT_RUN:
                    self.today.short_runs += 1
                self._burner_since = None
            self._burner = burner
        if release is not None:
            if release and self._release is False:
                self.today.releases += 1
            self._release = release
        self.today.co_heats += co_heats
        self._last = now

    @staticmethod
    def _record(
        day: date, values: _Day, energy: EnergySnapshot | None, *, finished: bool
    ) -> dict[str, Any]:
        gas = None
        degree_days = None
        if energy is not None:
            gas = energy.gas_energy_yesterday if finished else energy.gas_energy_today
            degree_days = energy.degree_days_yesterday if finished else None
        return {
            "day": day.isoformat(),
            "burner_starts": values.burner_starts,
            "burner_minutes": round(values.burner_seconds / 60.0, 1),
            "short_runs": values.short_runs,
            "releases": values.releases,
            "co_heats": values.co_heats,
            "network": values.seconds > 0 and values.enabled_seconds >= values.seconds / 2,
            "gas_kwh": round(gas, 2) if gas is not None else None,
            "degree_days": round(degree_days, 1) if degree_days is not None else None,
        }

    def summary(self, energy: EnergySnapshot | None) -> dict[str, Any]:
        """Past days and today."""
        today = (
            self._record(self.day, self.today, energy, finished=False)
            if self.day is not None
            else None
        )
        return {"days": list(self.history), "today": today}

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        t = self.today
        return {
            "history": list(self.history),
            "day": self.day.isoformat() if self.day else None,
            "today": {
                "burner_starts": t.burner_starts,
                "burner_seconds": t.burner_seconds,
                "short_runs": t.short_runs,
                "releases": t.releases,
                "co_heats": t.co_heats,
                "enabled_seconds": t.enabled_seconds,
                "seconds": t.seconds,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> KpiTracker:
        """Restore."""
        tracker = cls()
        if not data:
            return tracker
        tracker.history.extend(d for d in data.get("history", []) if isinstance(d, dict))
        day = data.get("day")
        if isinstance(day, str):
            try:
                tracker.day = date.fromisoformat(day)
            except ValueError:
                tracker.day = None
        today = data.get("today")
        if isinstance(today, dict):
            tracker.today = _Day(
                burner_starts=int(today.get("burner_starts", 0)),
                burner_seconds=float(today.get("burner_seconds", 0.0)),
                short_runs=int(today.get("short_runs", 0)),
                releases=int(today.get("releases", 0)),
                co_heats=int(today.get("co_heats", 0)),
                enabled_seconds=float(today.get("enabled_seconds", 0.0)),
                seconds=float(today.get("seconds", 0.0)),
            )
        return tracker
