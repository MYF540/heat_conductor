"""Night setback: when the home sleeps, even though somebody is there.

Three sources decide it, any of them is enough:

- a **night window** set by hand, e.g. 23:00 to 06:30;
- an optional **sleep sensor** (bed occupancy and the like) after a confirmation time;
- a **learned night window**, trained by that sensor per weekday and half hour.

A sensor that reports "awake" for the wake-up time ends the night even inside a
window: whoever gets up at 05:30 gets warmth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .presence import WeeklyPattern

MINUTES_PER_DAY = 24 * 60


class SleepSource(StrEnum):
    """Why the home counts as sleeping."""

    NONE = "none"
    SENSOR = "sensor"
    WINDOW = "window"
    LEARNED = "learned"


class NightPattern(WeeklyPattern):
    """Probability of sleeping per weekday and half hour."""

    # Nights are more regular than presence, and a night window is long.
    threshold: float = 0.6
    min_window: timedelta = timedelta(minutes=90)
    merge_gap: timedelta = timedelta(minutes=60)


@dataclass(frozen=True, slots=True)
class SleepParams:
    """When the night setback starts and ends."""

    window_start: int | None = None  # minute of day, None: no manual window
    window_end: int | None = None
    confirm: timedelta = timedelta(minutes=20)
    wake_confirm: timedelta = timedelta(minutes=15)
    use_learned: bool = True

    @property
    def has_window(self) -> bool:
        """Whether a manual night window is configured."""
        return self.window_start is not None and self.window_end is not None

    def in_window(self, now: datetime) -> bool:
        """Whether the given time lies inside the manual night window."""
        if not self.has_window or self.window_start == self.window_end:
            return False
        minute = now.hour * 60 + now.minute
        start, end = self.window_start, self.window_end
        assert start is not None and end is not None
        if start < end:
            return start <= minute < end
        return minute >= start or minute < end  # across midnight


@dataclass(frozen=True, slots=True)
class SleepState:
    """Result of one evaluation."""

    sleeping: bool = False
    source: SleepSource = SleepSource.NONE
    since: datetime | None = None
    sensor_sleeping: bool | None = None  # confirmed state of the sleep sensor


class SleepTracker:
    """Confirmation timers of the sleep sensor plus the window decision."""

    def __init__(self) -> None:
        self.sensor_sleeping: bool | None = None
        self.since: datetime | None = None
        self._on_since: datetime | None = None
        self._off_since: datetime | None = None

    def update(
        self, now: datetime, sensor: bool | None, pattern: NightPattern, params: SleepParams
    ) -> SleepState:
        """Advance the timers and decide whether the home sleeps."""
        self._update_sensor(now, sensor, params)

        awake = sensor is not None and self.sensor_sleeping is False
        learned = params.use_learned and pattern.ready and bool(pattern.schedule_state(now)[0])
        source = SleepSource.NONE
        if self.sensor_sleeping:
            source = SleepSource.SENSOR
        elif awake:
            # The sensor knows better than any window.
            source = SleepSource.NONE
        elif params.in_window(now):
            source = SleepSource.WINDOW
        elif learned:
            source = SleepSource.LEARNED

        sleeping = source is not SleepSource.NONE
        if not sleeping:
            self.since = None
        elif self.since is None:
            self.since = now
        return SleepState(
            sleeping=sleeping,
            source=source,
            since=self.since,
            sensor_sleeping=self.sensor_sleeping,
        )

    def _update_sensor(self, now: datetime, sensor: bool | None, params: SleepParams) -> None:
        if sensor is None:
            self.sensor_sleeping = None
            self._on_since = self._off_since = None
            return
        if sensor:
            self._off_since = None
            if self._on_since is None:
                self._on_since = now
            if now - self._on_since >= params.confirm:
                self.sensor_sleeping = True
        else:
            self._on_since = None
            if self._off_since is None:
                self._off_since = now
            if now - self._off_since >= params.wake_confirm:
                self.sensor_sleeping = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "sensor_sleeping": self.sensor_sleeping,
            "since": self.since.isoformat() if self.since else None,
        }

    def restore(self, data: dict[str, Any] | None) -> None:
        """Restore."""
        if not data:
            return
        value = data.get("sensor_sleeping")
        self.sensor_sleeping = value if isinstance(value, bool) else None
        since = data.get("since")
        if isinstance(since, str):
            try:
                self.since = datetime.fromisoformat(since)
            except ValueError:
                self.since = None


def parse_time_of_day(value: str | None) -> int | None:
    """Minute of day from "HH:MM" or "HH:MM:SS"; None if unset or unreadable."""
    if not isinstance(value, str) or not value.strip():
        return None
    parts = value.split(":")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except IndexError, ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute
