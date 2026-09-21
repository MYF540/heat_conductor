"""Online learning of the thermal behaviour of rooms and the boiler.

All learners are fed with one observation per evaluation, decimate it to a fixed
sampling interval and derive robust statistics. Every learned value carries its
sample count and spread so the panel can show how trustworthy it is.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from typing import Any

from .curve_advice import CurveAdvisor
from .presence import PresenceLearner
from .sleep import NightPattern

SAMPLE_INTERVAL = timedelta(minutes=5)
HEAT_WINDOW_SAMPLES = 7  # 30 min
COOL_WINDOW_SAMPLES = 13  # 60 min
HEAT_EVAL_INTERVAL = timedelta(minutes=30)
COOL_EVAL_INTERVAL = timedelta(minutes=60)
MIN_VALVE_HEATING = 0.5
MAX_VALVE_COOLING = 0.05
MIN_COOLING_DELTA = 5.0
DEAD_TIME_RISE = 0.2
MAX_DEAD_TIME = timedelta(minutes=120)
MIN_SAMPLES_FOR_USE = 3
MIN_ALPHA = 0.05
POINTS_MAX = 150
HISTORY_DAYS = 90
CURVE_INTERVAL = timedelta(minutes=10)
CURVE_DECAY = 0.998

OUTDOOR_BINS: tuple[tuple[float, float, str], ...] = (
    (-math.inf, 0.0, "below_0"),
    (0.0, 5.0, "0_5"),
    (5.0, 10.0, "5_10"),
    (10.0, math.inf, "above_10"),
)
CYCLE_BUCKETS: tuple[float, ...] = (5, 10, 20, 40, 60)  # minutes, last bucket open


def outdoor_bin(value: float | None) -> str | None:
    """Temperature band of an outdoor value."""
    if value is None:
        return None
    return next(name for low, high, name in OUTDOOR_BINS if low <= value < high)


@dataclass(slots=True)
class Stat:
    """Adaptive mean/variance: exact average first, then exponential forgetting."""

    count: int = 0
    mean: float = 0.0
    var: float = 0.0
    updated: datetime | None = None

    def add(self, value: float, now: datetime) -> None:
        """Add a sample."""
        self.count += 1
        alpha = max(1.0 / self.count, MIN_ALPHA)
        diff = value - self.mean
        self.mean += alpha * diff
        self.var = (1.0 - alpha) * (self.var + alpha * diff * diff)
        self.updated = now

    @property
    def std(self) -> float:
        """Standard deviation."""
        return math.sqrt(max(self.var, 0.0))

    def usable(self) -> bool:
        """Enough samples to act on."""
        return self.count >= MIN_SAMPLES_FOR_USE

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "count": self.count,
            "mean": self.mean,
            "var": self.var,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    def summary(self, digits: int = 2) -> dict[str, Any]:
        """Values for display."""
        return {
            "count": self.count,
            "mean": round(self.mean, digits) if self.count else None,
            "std": round(self.std, digits) if self.count > 1 else None,
            "usable": self.usable(),
            "updated": self.updated.isoformat() if self.updated else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Stat:
        """Restore."""
        if not data:
            return cls()
        updated = data.get("updated")
        try:
            parsed = datetime.fromisoformat(updated) if isinstance(updated, str) else None
        except ValueError:
            parsed = None
        return cls(
            count=int(data.get("count", 0)),
            mean=float(data.get("mean", 0.0)),
            var=float(data.get("var", 0.0)),
            updated=parsed,
        )


@dataclass(frozen=True, slots=True)
class Sample:
    """One decimated observation of a room."""

    time: datetime
    temperature: float
    outdoor: float | None
    valve: float | None
    heating: bool
    window_open: bool


def _slope_per_hour(samples: list[Sample]) -> float | None:
    """Least-squares slope of temperature over time in K/h."""
    if len(samples) < 3:
        return None
    t0 = samples[0].time
    xs = [(s.time - t0).total_seconds() / 3600.0 for s in samples]
    ys = [s.temperature for s in samples]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sxx


class RoomLearner:
    """Heat-up rate, cooling time constant and dead time of one room."""

    def __init__(self) -> None:
        self.heat_rate: dict[str, Stat] = {"all": Stat()}
        self.cooling_tau = Stat()  # hours
        self.dead_time = Stat()  # minutes
        self.heat_points: deque[tuple[float, float]] = deque(maxlen=POINTS_MAX)
        self.cool_points: deque[tuple[float, float]] = deque(maxlen=POINTS_MAX)
        self.history: deque[dict[str, Any]] = deque(maxlen=HISTORY_DAYS)
        self._samples: deque[Sample] = deque(maxlen=COOL_WINDOW_SAMPLES)
        self._last_sample: datetime | None = None
        self._last_heat_eval: datetime | None = None
        self._last_cool_eval: datetime | None = None
        self._dead_start: tuple[datetime, float] | None = None
        self._day: date | None = None

    def update(
        self,
        now: datetime,
        *,
        temperature: float | None,
        outdoor: float | None,
        valve: float | None,
        heating: bool | None,
        window_open: bool,
    ) -> None:
        """Feed one evaluation."""
        if self._day != now.date():
            if self._day is not None and self.heat_rate["all"].count:
                self.history.append(
                    {
                        "day": self._day.isoformat(),
                        "heat_rate": round(self.heat_rate["all"].mean, 3),
                        "cooling_tau": round(self.cooling_tau.mean, 2)
                        if self.cooling_tau.count
                        else None,
                    }
                )
            self._day = now.date()

        if temperature is None or heating is None:
            return
        if self._last_sample is not None and now - self._last_sample < SAMPLE_INTERVAL:
            return
        if self._last_sample is not None and now - self._last_sample > SAMPLE_INTERVAL * 3:
            self._samples.clear()  # gap: windows must be continuous
        self._last_sample = now
        sample = Sample(now, temperature, outdoor, valve, heating, window_open)
        previous = self._samples[-1] if self._samples else None
        self._samples.append(sample)

        self._learn_dead_time(sample, previous)
        self._learn_heating(now)
        self._learn_cooling(now)

    def _learn_heating(self, now: datetime) -> None:
        window = list(self._samples)[-HEAT_WINDOW_SAMPLES:]
        if len(window) < HEAT_WINDOW_SAMPLES:
            return
        if self._last_heat_eval is not None and now - self._last_heat_eval < HEAT_EVAL_INTERVAL:
            return
        if not all(
            s.heating and (s.valve or 0.0) >= MIN_VALVE_HEATING and not s.window_open
            for s in window
        ):
            return
        slope = _slope_per_hour(window)
        if slope is None or not 0.05 < slope < 10.0:
            return
        self._last_heat_eval = now
        self.heat_rate["all"].add(slope, now)
        outdoor_values = [s.outdoor for s in window if s.outdoor is not None]
        if outdoor_values:
            mean_outdoor = sum(outdoor_values) / len(outdoor_values)
            band = outdoor_bin(mean_outdoor)
            if band is not None:
                self.heat_rate.setdefault(band, Stat()).add(slope, now)
            self.heat_points.append((round(mean_outdoor, 1), round(slope, 3)))

    def _learn_cooling(self, now: datetime) -> None:
        window = list(self._samples)
        if len(window) < COOL_WINDOW_SAMPLES:
            return
        if self._last_cool_eval is not None and now - self._last_cool_eval < COOL_EVAL_INTERVAL:
            return
        if not all(
            not s.heating
            and (s.valve or 0.0) <= MAX_VALVE_COOLING
            and not s.window_open
            and s.outdoor is not None
            for s in window
        ):
            return
        delta = sum(s.temperature - (s.outdoor or 0.0) for s in window) / len(window)
        if delta < MIN_COOLING_DELTA:
            return
        slope = _slope_per_hour(window)
        if slope is None or slope >= -0.02:
            return
        tau = delta / -slope
        if not 5.0 < tau < 1000.0:
            return
        self._last_cool_eval = now
        self.cooling_tau.add(tau, now)
        self.cool_points.append((round(delta, 1), round(tau, 1)))

    def _learn_dead_time(self, sample: Sample, previous: Sample | None) -> None:
        valve = sample.valve or 0.0
        if self._dead_start is None:
            if (
                previous is not None
                and sample.heating
                and valve >= MIN_VALVE_HEATING
                and (previous.valve or 0.0) < 0.2
            ):
                self._dead_start = (sample.time, sample.temperature)
            return
        start_time, start_temp = self._dead_start
        if valve < 0.2 or sample.window_open or sample.time - start_time > MAX_DEAD_TIME:
            self._dead_start = None
            return
        if sample.temperature >= start_temp + DEAD_TIME_RISE:
            minutes = (sample.time - start_time).total_seconds() / 60.0
            self.dead_time.add(minutes, sample.time)
            self._dead_start = None

    def heat_rate_for(self, outdoor: float | None) -> float | None:
        """Learned K/h for the given outdoor temperature (band, then overall)."""
        band = outdoor_bin(outdoor)
        if band is not None and band in self.heat_rate and self.heat_rate[band].usable():
            return self.heat_rate[band].mean
        overall = self.heat_rate["all"]
        return overall.mean if overall.usable() else None

    def dead_time_value(self) -> timedelta | None:
        """Learned dead time."""
        return timedelta(minutes=self.dead_time.mean) if self.dead_time.usable() else None

    def summary(self) -> dict[str, Any]:
        """Values for display."""
        return {
            "heat_rate": {band: stat.summary(3) for band, stat in self.heat_rate.items()},
            "cooling_tau": self.cooling_tau.summary(1),
            "dead_time": self.dead_time.summary(0),
            "heat_points": list(self.heat_points),
            "cool_points": list(self.cool_points),
            "history": list(self.history),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "heat_rate": {band: stat.to_dict() for band, stat in self.heat_rate.items()},
            "cooling_tau": self.cooling_tau.to_dict(),
            "dead_time": self.dead_time.to_dict(),
            "heat_points": list(self.heat_points),
            "cool_points": list(self.cool_points),
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RoomLearner:
        """Restore."""
        learner = cls()
        if not data:
            return learner
        learner.heat_rate = {
            band: Stat.from_dict(stat) for band, stat in (data.get("heat_rate") or {}).items()
        }
        learner.heat_rate.setdefault("all", Stat())
        learner.cooling_tau = Stat.from_dict(data.get("cooling_tau"))
        learner.dead_time = Stat.from_dict(data.get("dead_time"))
        learner.heat_points.extend(tuple(p) for p in data.get("heat_points", []))
        learner.cool_points.extend(tuple(p) for p in data.get("cool_points", []))
        learner.history.extend(data.get("history", []))
        return learner


class BoilerCycleLearner:
    """Burner run and pause durations per outdoor band."""

    def __init__(self) -> None:
        self.runs: dict[str, Stat] = {}
        self.pauses: dict[str, Stat] = {}
        self.run_histogram = [0] * (len(CYCLE_BUCKETS) + 1)
        self.pause_histogram = [0] * (len(CYCLE_BUCKETS) + 1)
        self._state: bool | None = None
        self._since: datetime | None = None

    def update(self, now: datetime, burner: bool | None, outdoor: float | None) -> None:
        """Feed the burner state."""
        if burner is None:
            return
        if self._state is None:
            self._state, self._since = burner, None  # unknown start of the first phase
            return
        if burner == self._state:
            return
        if self._since is not None:
            minutes = (now - self._since).total_seconds() / 60.0
            band = outdoor_bin(outdoor) or "unknown"
            stats, histogram = (
                (self.runs, self.run_histogram)
                if self._state
                else (self.pauses, self.pause_histogram)
            )
            stats.setdefault(band, Stat()).add(minutes, now)
            stats.setdefault("all", Stat()).add(minutes, now)
            histogram[_bucket(minutes)] += 1
        self._state, self._since = burner, now

    def summary(self) -> dict[str, Any]:
        """Values for display."""
        return {
            "runs": {band: stat.summary(1) for band, stat in self.runs.items()},
            "pauses": {band: stat.summary(1) for band, stat in self.pauses.items()},
            "run_histogram": list(self.run_histogram),
            "pause_histogram": list(self.pause_histogram),
            "buckets": list(CYCLE_BUCKETS),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "runs": {band: stat.to_dict() for band, stat in self.runs.items()},
            "pauses": {band: stat.to_dict() for band, stat in self.pauses.items()},
            "run_histogram": self.run_histogram,
            "pause_histogram": self.pause_histogram,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BoilerCycleLearner:
        """Restore."""
        learner = cls()
        if not data:
            return learner
        learner.runs = {b: Stat.from_dict(s) for b, s in (data.get("runs") or {}).items()}
        learner.pauses = {b: Stat.from_dict(s) for b, s in (data.get("pauses") or {}).items()}
        size = len(CYCLE_BUCKETS) + 1
        learner.run_histogram = (list(data.get("run_histogram", [])) + [0] * size)[:size]
        learner.pause_histogram = (list(data.get("pause_histogram", [])) + [0] * size)[:size]
        return learner


def _bucket(minutes: float) -> int:
    return next((i for i, limit in enumerate(CYCLE_BUCKETS) if minutes < limit), len(CYCLE_BUCKETS))


class HeatingCurveLearner:
    """Flow setpoint of the boiler controller as a linear function of outdoor temperature."""

    def __init__(self) -> None:
        self.n = 0.0
        self.sx = 0.0
        self.sy = 0.0
        self.sxx = 0.0
        self.sxy = 0.0
        self.samples = 0
        self.points: deque[tuple[float, float]] = deque(maxlen=POINTS_MAX)
        self._last: datetime | None = None

    def update(self, now: datetime, outdoor: float | None, flow_setpoint: float | None) -> None:
        """Feed outdoor temperature and the controller's flow setpoint."""
        if outdoor is None or flow_setpoint is None or flow_setpoint < 20:
            return
        if self._last is not None and now - self._last < CURVE_INTERVAL:
            return
        self._last = now
        self.n = self.n * CURVE_DECAY + 1
        self.sx = self.sx * CURVE_DECAY + outdoor
        self.sy = self.sy * CURVE_DECAY + flow_setpoint
        self.sxx = self.sxx * CURVE_DECAY + outdoor * outdoor
        self.sxy = self.sxy * CURVE_DECAY + outdoor * flow_setpoint
        self.samples += 1
        self.points.append((round(outdoor, 1), round(flow_setpoint, 1)))

    def fit(self) -> tuple[float, float] | None:
        """(slope K/K, flow temperature at 0 °C outdoor)."""
        if self.samples < 10:
            return None
        denominator = self.n * self.sxx - self.sx * self.sx
        if abs(denominator) < 1e-6:
            return None
        slope = (self.n * self.sxy - self.sx * self.sy) / denominator
        intercept = (self.sy - slope * self.sx) / self.n
        return slope, intercept

    def summary(self) -> dict[str, Any]:
        """Values for display."""
        fit = self.fit()
        return {
            "samples": self.samples,
            "slope": round(fit[0], 3) if fit else None,
            "flow_at_0": round(fit[1], 1) if fit else None,
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
    def from_dict(cls, data: dict[str, Any] | None) -> HeatingCurveLearner:
        """Restore."""
        learner = cls()
        if not data:
            return learner
        for key in ("n", "sx", "sy", "sxx", "sxy"):
            setattr(learner, key, float(data.get(key, 0.0)))
        learner.samples = int(data.get("samples", 0))
        learner.points.extend(tuple(p) for p in data.get("points", []))
        return learner


class Learner:
    """All learners of an installation."""

    def __init__(self) -> None:
        self.rooms: dict[str, RoomLearner] = {}
        self.boiler = BoilerCycleLearner()
        self.curve = HeatingCurveLearner()
        self.presence = PresenceLearner()
        self.night = NightPattern()
        self.curve_advice = CurveAdvisor()

    def room(self, room_id: str) -> RoomLearner:
        """Learner of a room (created on demand)."""
        return self.rooms.setdefault(room_id, RoomLearner())

    def reset(self, room_id: str | None = None) -> None:
        """Forget learned values of one room or everything."""
        if room_id is None:
            self.rooms.clear()
            self.boiler = BoilerCycleLearner()
            self.curve = HeatingCurveLearner()
            self.presence = PresenceLearner()
            self.night = NightPattern()
            self.curve_advice = CurveAdvisor()
        else:
            self.rooms.pop(room_id, None)

    def summary(
        self, names: dict[str, str], *, target_valve: float = 0.85, curve_setting: float = 0.0
    ) -> dict[str, Any]:
        """Everything for the panel."""
        return {
            "rooms": [
                {"room_id": room_id, "name": names.get(room_id, room_id), **learner.summary()}
                for room_id, learner in self.rooms.items()
                if room_id in names
            ],
            "boiler": self.boiler.summary(),
            "heating_curve": self.curve.summary(),
            "presence": self.presence.summary(),
            "night": self.night.summary(),
            "curve_advice": self.curve_advice.summary(
                names,
                current=self.curve.fit(),
                target_valve=target_valve,
                curve_setting=curve_setting,
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "rooms": {room_id: learner.to_dict() for room_id, learner in self.rooms.items()},
            "boiler": self.boiler.to_dict(),
            "curve": self.curve.to_dict(),
            "presence": self.presence.to_dict(),
            "night": self.night.to_dict(),
            "curve_advice": self.curve_advice.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Learner:
        """Restore."""
        learner = cls()
        if not data:
            return learner
        learner.rooms = {
            room_id: RoomLearner.from_dict(room)
            for room_id, room in (data.get("rooms") or {}).items()
        }
        learner.boiler = BoilerCycleLearner.from_dict(data.get("boiler"))
        learner.curve = HeatingCurveLearner.from_dict(data.get("curve"))
        learner.presence = PresenceLearner.from_dict(data.get("presence"))
        learner.night = NightPattern.from_dict(data.get("night"))
        learner.curve_advice = CurveAdvisor.from_dict(data.get("curve_advice"))
        return learner
