"""Weekly patterns learned from one yes/no observation per evaluation.

Observations are decimated to a fixed sampling interval and averaged per weekday
and half-hour slot. The result is a probability grid that the panel shows and
from which windows are derived (comfort periods, night periods). A pattern is
only used once enough days have been observed.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

SLOT_MINUTES = 30
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES
DAYS = 7
SAMPLE_INTERVAL = timedelta(minutes=5)
MIN_ALPHA = 0.05
# Enough data for a suggestion: at least two observations of every weekday.
MIN_DAYS = 14
PRESENT_THRESHOLD = 0.5
MIN_WINDOW = timedelta(minutes=60)
MERGE_GAP = timedelta(minutes=60)


def slot_of(moment: datetime) -> tuple[int, int]:
    """(weekday 0=Monday, slot index) of a point in time."""
    return moment.weekday(), (moment.hour * 60 + moment.minute) // SLOT_MINUTES


class WeeklyPattern:
    """Probability of a yes/no observation per weekday and half hour."""

    min_days: int = MIN_DAYS
    threshold: float = PRESENT_THRESHOLD
    min_window: timedelta = MIN_WINDOW
    merge_gap: timedelta = MERGE_GAP

    def __init__(self) -> None:
        self.grid: list[list[float]] = [[0.0] * SLOTS_PER_DAY for _ in range(DAYS)]
        self.counts: list[list[int]] = [[0] * SLOTS_PER_DAY for _ in range(DAYS)]
        self.days_observed: int = 0
        self._last_date: date | None = None
        self._last_sample: datetime | None = None

    # -- learning ----------------------------------------------------------

    def update(self, now: datetime, value: bool | None) -> None:
        """Add one observation (ignored without information)."""
        if value is None:
            return
        if self._last_sample is not None and now - self._last_sample < SAMPLE_INTERVAL:
            return
        self._last_sample = now
        if self._last_date != now.date():
            self._last_date = now.date()
            self.days_observed += 1

        day, slot = slot_of(now)
        self.counts[day][slot] += 1
        alpha = max(1.0 / self.counts[day][slot], MIN_ALPHA)
        self.grid[day][slot] += alpha * (float(value) - self.grid[day][slot])

    # -- windows -----------------------------------------------------------

    @property
    def ready(self) -> bool:
        """Whether enough days have been observed."""
        return self.days_observed >= self.min_days and all(
            any(count > 0 for count in day) for day in self.counts
        )

    def windows(self, threshold: float | None = None) -> list[list[tuple[int, int]]]:
        """Windows per weekday as (start minute, end minute)."""
        limit = self.threshold if threshold is None else threshold
        merge = int(self.merge_gap.total_seconds() // 60)
        minimum = int(self.min_window.total_seconds() // 60)
        result: list[list[tuple[int, int]]] = []
        for day in range(DAYS):
            blocks: list[tuple[int, int]] = []
            for slot in range(SLOTS_PER_DAY):
                if self.counts[day][slot] == 0 or self.grid[day][slot] < limit:
                    continue
                start = slot * SLOT_MINUTES
                end = start + SLOT_MINUTES
                if blocks and start - blocks[-1][1] <= merge:
                    blocks[-1] = (blocks[-1][0], end)
                else:
                    blocks.append((start, end))
            result.append([b for b in blocks if b[1] - b[0] >= minimum])
        return result

    def schedule_state(self, now: datetime) -> tuple[bool | None, datetime | None]:
        """(inside a window now, next window start)."""
        if not self.ready:
            return None, None
        windows = self.windows()
        minute = now.hour * 60 + now.minute
        on = any(start <= minute < end for start, end in windows[now.weekday()])
        if on:
            return True, None
        midnight = datetime.combine(now.date(), time(), tzinfo=now.tzinfo)
        for offset in range(DAYS + 1):
            day = (now.weekday() + offset) % DAYS
            for start, _end in windows[day]:
                moment = midnight + timedelta(days=offset, minutes=start)
                if moment > now:
                    return False, moment
        return False, None

    def summary(self) -> dict[str, Any]:
        """Everything the panel needs."""
        return {
            "ready": self.ready,
            "days_observed": self.days_observed,
            "slot_minutes": SLOT_MINUTES,
            "min_days": self.min_days,
            "threshold": self.threshold,
            "grid": [
                [
                    round(value, 3) if count else None
                    for value, count in zip(day, counts, strict=True)
                ]
                for day, counts in zip(self.grid, self.counts, strict=True)
            ],
            "windows": [
                [{"start": start, "end": end} for start, end in day] for day in self.windows()
            ],
        }

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "grid": [[round(value, 4) for value in day] for day in self.grid],
            "counts": self.counts,
            "days_observed": self.days_observed,
            "last_date": self._last_date.isoformat() if self._last_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None):  # type: ignore[no-untyped-def]
        """Restore."""
        pattern = cls()
        if not data:
            return pattern
        grid = data.get("grid")
        counts = data.get("counts")
        if _is_grid(grid) and _is_grid(counts):
            pattern.grid = [[float(v) for v in day] for day in grid]
            pattern.counts = [[int(v) for v in day] for day in counts]
        observed = data.get("days_observed")
        pattern.days_observed = int(observed) if isinstance(observed, int) else 0
        last = data.get("last_date")
        if isinstance(last, str):
            try:
                pattern._last_date = date.fromisoformat(last)
            except ValueError:
                pattern._last_date = None
        return pattern


class PresenceLearner(WeeklyPattern):
    """Probability of somebody being at home per weekday and half hour."""


def _is_grid(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == DAYS
        and all(isinstance(day, list) and len(day) == SLOTS_PER_DAY for day in value)
    )
