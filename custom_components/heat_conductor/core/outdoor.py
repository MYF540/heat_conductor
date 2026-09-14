"""Outdoor temperature fusion and smoothing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from statistics import median

from .models import Reading

PLAUSIBLE_MIN = -45.0
PLAUSIBLE_MAX = 55.0


@dataclass(frozen=True, slots=True)
class OutdoorResult:
    """Fused outdoor temperature."""

    value: float | None
    source: str
    sensors_used: int


def fuse_outdoor(
    sensors: tuple[Reading, ...],
    weather: Reading | None,
    now: datetime,
    max_age: timedelta,
    max_spread: float,
) -> OutdoorResult:
    """Combine several outdoor sensors into one value.

    Two sensors that disagree by more than max_spread are assumed to suffer
    from sun exposure, so the colder one wins. With three or more, the median
    discards a single outlier. The weather entity is only a fallback.
    """
    values = [
        v
        for r in sensors
        if (v := r.valid_value(now, max_age)) is not None and PLAUSIBLE_MIN < v < PLAUSIBLE_MAX
    ]
    if len(values) >= 3:
        return OutdoorResult(median(values), "sensors", len(values))
    if len(values) == 2:
        low, high = sorted(values)
        value = (low + high) / 2 if high - low <= max_spread else low
        return OutdoorResult(value, "sensors", 2)
    if len(values) == 1:
        return OutdoorResult(values[0], "sensors", 1)
    if weather is not None:
        v = weather.valid_value(now, max_age)
        if v is not None and PLAUSIBLE_MIN < v < PLAUSIBLE_MAX:
            return OutdoorResult(v, "weather", 0)
    return OutdoorResult(None, "none", 0)


class ExponentialSmoother:
    """Time-aware exponential moving average."""

    def __init__(self, time_constant: timedelta) -> None:
        self._tau = time_constant.total_seconds()
        self.value: float | None = None
        self.updated_at: datetime | None = None

    def update(self, value: float | None, now: datetime) -> float | None:
        """Feed a new sample and return the smoothed value."""
        if value is None:
            return self.value
        if self.value is None or self.updated_at is None or self._tau <= 0:
            self.value = value
            self.updated_at = now
            return self.value
        dt = (now - self.updated_at).total_seconds()
        if dt <= 0:
            return self.value
        alpha = 1.0 - math.exp(-dt / self._tau)
        self.value += alpha * (value - self.value)
        self.updated_at = now
        return self.value
