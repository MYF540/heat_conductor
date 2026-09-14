"""Daily start and runtime counters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Counters of the current local day."""

    starts: int
    runtime: timedelta


class DailyRuntime:
    """Counts off->on transitions and on-time per local calendar day."""

    def __init__(self) -> None:
        self.day: date | None = None
        self.starts = 0
        self.on_seconds = 0.0
        self._last_on: bool | None = None
        self._last_update: datetime | None = None

    def update(self, now: datetime, is_on: bool | None) -> RuntimeSnapshot:
        """Feed the current state; now must be timezone-aware local time."""
        if self.day != now.date():
            if self.day is not None and self._last_update is not None:
                self._last_update = datetime.combine(now.date(), time.min, now.tzinfo)
            self.day = now.date()
            self.starts = 0
            self.on_seconds = 0.0

        if self._last_on and self._last_update is not None and now > self._last_update:
            self.on_seconds += (now - self._last_update).total_seconds()
        if is_on and self._last_on is False:
            self.starts += 1

        if is_on is not None:
            self._last_on = is_on
        self._last_update = now
        return self.snapshot()

    def snapshot(self) -> RuntimeSnapshot:
        """Return the current counters."""
        return RuntimeSnapshot(self.starts, timedelta(seconds=self.on_seconds))

    def to_dict(self) -> dict[str, Any]:
        """Serialize counters."""
        return {
            "day": self.day.isoformat() if self.day else None,
            "starts": self.starts,
            "on_seconds": self.on_seconds,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore counters saved by to_dict (only for the same day)."""
        try:
            self.day = date.fromisoformat(data["day"]) if data.get("day") else None
        except TypeError, ValueError:
            return
        self.starts = int(data.get("starts", 0))
        self.on_seconds = float(data.get("on_seconds", 0.0))
