"""Suggests a better heating curve for the boiler controller.

Evidence is collected only while the burner runs steadily. For every sample the
"bottleneck room" is the room with the widest open valve: it decides how warm the
flow has to be. Per outdoor temperature band the collected evidence answers:

- valves of the bottleneck room far from fully open and all rooms warm
  -> the thermostats throttle heat away, the curve can go down;
- bottleneck valve fully open and the room still too cold -> the curve is too low.

The required mean radiator temperature follows from the radiator characteristic
(heat output proportional to the over-temperature to the power of 1.3). Valve
opening is used as a rough measure of the heat a radiator actually delivers, so
the result is a guide value: after changing the curve the learned curve shows
whether the change hit the target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
from typing import Any

SAMPLE_INTERVAL = timedelta(minutes=5)
STEADY_AFTER = timedelta(minutes=20)  # flow temperature and valves need time to settle
BAND_WIDTH = 3.0  # K outdoor temperature per band
MIN_BAND_SAMPLES = 24  # two hours of steady heating
DEFAULT_SPREAD = 10.0  # K, if no return temperature is known
RADIATOR_EXPONENT = 1.3
SATURATED_VALVE = 0.95
DEFICIT_LIMIT = 0.5  # K
SATURATED_SHARE = 0.25  # share of samples that makes a band "too cold"
MAX_LOWER = 15.0  # K the suggestion may lower the flow of one band
MAX_RAISE = 10.0  # K the suggestion may raise it
MIN_OVERTEMPERATURE = 3.0  # K mean radiator temperature above the room
CURVE_ROOM_SETPOINT = 20.0  # reference room temperature of the controller's curves
MIN_FIT_SPAN = 4.0  # K outdoor range for a slope


@dataclass(frozen=True, slots=True)
class CurveRoomSample:
    """One room in one sample."""

    room_id: str
    temperature: float
    target: float
    valve: float


@dataclass(slots=True)
class BandEvidence:
    """Running means of one outdoor temperature band."""

    samples: int = 0
    outdoor: float = 0.0
    flow_setpoint: float = 0.0
    flow: float = 0.0
    spread: float = 0.0
    valve: float = 0.0
    overtemperature: float = 0.0  # mean radiator temperature minus bottleneck room
    room_target: float = 0.0
    saturated: int = 0  # samples with the bottleneck valve open and the room too cold
    demand_ratio: float = 0.0  # mean over saturated samples
    bottlenecks: dict[str, int] = field(default_factory=dict)

    def add(
        self,
        *,
        outdoor: float,
        flow_setpoint: float,
        flow: float,
        spread: float,
        room: CurveRoomSample,
    ) -> None:
        """Add one sample."""
        self.samples += 1
        weight = 1.0 / self.samples
        mean = flow - spread / 2
        self.outdoor += weight * (outdoor - self.outdoor)
        self.flow_setpoint += weight * (flow_setpoint - self.flow_setpoint)
        self.flow += weight * (flow - self.flow)
        self.spread += weight * (spread - self.spread)
        self.valve += weight * (room.valve - self.valve)
        self.overtemperature += weight * (mean - room.temperature - self.overtemperature)
        self.room_target += weight * (room.target - self.room_target)
        self.bottlenecks[room.room_id] = self.bottlenecks.get(room.room_id, 0) + 1
        if room.valve >= SATURATED_VALVE and room.target - room.temperature >= DEFICIT_LIMIT:
            self.saturated += 1
            # Heat needed for the target compared with what kept the room where it is.
            ratio = (room.target - outdoor) / max(room.temperature - outdoor, 1.0)
            self.demand_ratio += (max(ratio, 1.0) - self.demand_ratio) / self.saturated

    def recommendation(self, target_valve: float) -> float | None:
        """Suggested controller flow setpoint for this band."""
        if self.samples < MIN_BAND_SAMPLES or self.overtemperature <= 0:
            return None
        if self.saturated / self.samples >= SATURATED_SHARE:
            factor = self.demand_ratio
        else:
            # Never suggest more heat while the rooms are warm enough.
            factor = min(self.valve / target_valve, 1.0)
        overtemperature = self.overtemperature * factor ** (1 / RADIATOR_EXPONENT)
        overtemperature = max(overtemperature, MIN_OVERTEMPERATURE)
        required_flow = self.room_target + overtemperature + self.spread / 2
        change = min(max(required_flow - self.flow, -MAX_LOWER), MAX_RAISE)
        return self.flow_setpoint + change

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "samples": self.samples,
            "outdoor": self.outdoor,
            "flow_setpoint": self.flow_setpoint,
            "flow": self.flow,
            "spread": self.spread,
            "valve": self.valve,
            "overtemperature": self.overtemperature,
            "room_target": self.room_target,
            "saturated": self.saturated,
            "demand_ratio": self.demand_ratio,
            "bottlenecks": dict(self.bottlenecks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BandEvidence:
        """Restore."""
        band = cls()
        for key in (
            "outdoor",
            "flow_setpoint",
            "flow",
            "spread",
            "valve",
            "overtemperature",
            "room_target",
            "demand_ratio",
        ):
            value = data.get(key)
            if isinstance(value, (int, float)):
                setattr(band, key, float(value))
        for key in ("samples", "saturated"):
            value = data.get(key)
            if isinstance(value, int):
                setattr(band, key, value)
        bottlenecks = data.get("bottlenecks")
        if isinstance(bottlenecks, dict):
            band.bottlenecks = {str(k): int(v) for k, v in bottlenecks.items()}
        return band


def band_key(outdoor: float) -> int:
    """Lower edge of the outdoor band."""
    return int(math.floor(outdoor / BAND_WIDTH) * BAND_WIDTH)


class CurveAdvisor:
    """Collects evidence during steady heating and derives a suggested curve."""

    def __init__(self) -> None:
        self.bands: dict[int, BandEvidence] = {}
        self._heating_since: datetime | None = None
        self._last_sample: datetime | None = None

    def update(
        self,
        now: datetime,
        *,
        heating: bool | None,
        outdoor: float | None,
        flow_setpoint: float | None,
        flow: float | None,
        return_temperature: float | None,
        pump_on: bool | None,
        rooms: list[CurveRoomSample],
    ) -> None:
        """Feed one evaluation."""
        if not heating or pump_on is False:
            self._heating_since = None
            return
        if self._heating_since is None:
            self._heating_since = now
        if now - self._heating_since < STEADY_AFTER:
            return
        if self._last_sample is not None and now - self._last_sample < SAMPLE_INTERVAL:
            return
        if outdoor is None or flow_setpoint is None or not rooms:
            return
        water = flow if flow is not None else flow_setpoint
        spread = (
            water - return_temperature
            if return_temperature is not None and water > return_temperature
            else DEFAULT_SPREAD
        )
        self._last_sample = now
        bottleneck = max(rooms, key=lambda r: r.valve)
        self.bands.setdefault(band_key(outdoor), BandEvidence()).add(
            outdoor=outdoor,
            flow_setpoint=flow_setpoint,
            flow=water,
            spread=spread,
            room=bottleneck,
        )

    def summary(
        self,
        names: dict[str, str],
        *,
        current: tuple[float, float] | None,
        target_valve: float,
        curve_setting: float,
    ) -> dict[str, Any]:
        """Evidence per band, the suggested curve and its VRC-style curve number."""
        bands: list[dict[str, Any]] = []
        points: list[tuple[float, float, int, float]] = []  # outdoor, suggested, samples, now
        for key in sorted(self.bands):
            band = self.bands[key]
            recommended = band.recommendation(target_valve)
            room_id, count = max(
                band.bottlenecks.items(), key=lambda item: item[1], default=("", 0)
            )
            bands.append(
                {
                    "from": key,
                    "to": key + BAND_WIDTH,
                    "samples": band.samples,
                    "outdoor": _round(band.outdoor),
                    "flow_setpoint": _round(band.flow_setpoint),
                    "flow": _round(band.flow),
                    "spread": _round(band.spread),
                    "valve": round(band.valve, 3),
                    "too_cold_share": round(band.saturated / band.samples, 3)
                    if band.samples
                    else 0,
                    "bottleneck": names.get(room_id, room_id) if room_id else None,
                    "bottleneck_share": round(count / band.samples, 3) if band.samples else 0,
                    "recommended": _round(recommended),
                    "change": _round(recommended - band.flow_setpoint)
                    if recommended is not None
                    else None,
                }
            )
            if recommended is not None:
                points.append((band.outdoor, recommended, band.samples, band.flow_setpoint))

        suggested = _weighted_fit(points)
        shift = (
            sum((p[1] - p[3]) * p[2] for p in points) / sum(p[2] for p in points)
            if points
            else None
        )
        return {
            "ready": bool(points),
            "min_samples": MIN_BAND_SAMPLES,
            "target_valve": target_valve,
            "bands": bands,
            "current": {"slope": _round(current[0], 3), "flow_at_0": _round(current[1])}
            if current
            else None,
            "suggested": {"slope": _round(suggested[0], 3), "flow_at_0": _round(suggested[1])}
            if suggested
            else None,
            "shift": _round(shift),
            "curve_setting": curve_setting or None,
            "suggested_setting": _curve_number(curve_setting, current, suggested, points),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {str(key): band.to_dict() for key, band in self.bands.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CurveAdvisor:
        """Restore."""
        advisor = cls()
        for key, band in (data or {}).items():
            try:
                advisor.bands[int(key)] = BandEvidence.from_dict(band)
            except TypeError, ValueError, AttributeError:
                continue
        return advisor


def _weighted_fit(points: list[tuple[float, float, int, float]]) -> tuple[float, float] | None:
    """Weighted straight line through (outdoor, flow) if the bands span enough."""
    if len(points) < 2 or max(p[0] for p in points) - min(p[0] for p in points) < MIN_FIT_SPAN:
        return None
    w = sum(p[2] for p in points)
    mx = sum(p[0] * p[2] for p in points) / w
    my = sum(p[1] * p[2] for p in points) / w
    sxx = sum(p[2] * (p[0] - mx) ** 2 for p in points)
    if sxx < 1e-6:
        return None
    slope = sum(p[2] * (p[0] - mx) * (p[1] - my) for p in points) / sxx
    return slope, my - slope * mx


def _curve_number(
    setting: float,
    current: tuple[float, float] | None,
    suggested: tuple[float, float] | None,
    points: list[tuple[float, float, int, float]],
) -> float | None:
    """Scale the controller's curve number by the ratio of flow over-temperatures.

    Evaluated at the coldest observed band, where the curve number matters most.
    Only a guide: the controller's curves are not exactly proportional.
    """
    if setting <= 0 or current is None or not points:
        return None
    reference = min(p[0] for p in points)
    now = current[0] * reference + current[1] - CURVE_ROOM_SETPOINT
    if suggested is not None:
        wanted = suggested[0] * reference + suggested[1] - CURVE_ROOM_SETPOINT
    else:
        # Only one band: shift by what that band needs.
        coldest = min(points, key=lambda p: p[0])
        wanted = now + (coldest[1] - coldest[3])
    if now <= 1 or wanted <= 0:
        return None
    return round(setting * wanted / now, 1)


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None
