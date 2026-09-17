"""Automatic vacation detection from presence.

Nobody at home for a long time switches the installation to vacation; somebody
being back for a while switches it off again. The state is persisted, so a
restart does not restart the timers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class VacationParams:
    """When automatic vacation starts and ends."""

    enabled: bool = True
    absence: timedelta = timedelta(days=2)
    presence: timedelta = timedelta(hours=3)


@dataclass(slots=True)
class AutoVacation:
    """Tracks how long nobody has been at home."""

    active: bool = False
    absent_since: datetime | None = None
    present_since: datetime | None = None
    since: datetime | None = None  # when the automatic vacation started

    def update(self, now: datetime, present: bool | None, params: VacationParams) -> bool:
        """Advance the timers and return whether automatic vacation is active."""
        if not params.enabled:
            self.reset(now)
            return False
        if present is None:
            # Without presence information absence cannot be claimed.
            self.absent_since = None
            self.present_since = None
            return self.active

        if present:
            self.absent_since = None
            if self.present_since is None:
                self.present_since = now
            if self.active and now - self.present_since >= params.presence:
                self.active = False
                self.since = None
        else:
            self.present_since = None
            if self.absent_since is None:
                self.absent_since = now
            if not self.active and now - self.absent_since >= params.absence:
                self.active = True
                self.since = now
        return self.active

    def reset(self, now: datetime | None = None) -> None:
        """End an automatic vacation; a new one needs the full absence again."""
        self.active = False
        self.since = None
        self.absent_since = now
        self.present_since = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {
            "active": self.active,
            "absent_since": _iso(self.absent_since),
            "present_since": _iso(self.present_since),
            "since": _iso(self.since),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AutoVacation:
        """Restore."""
        if not data:
            return cls()
        return cls(
            active=bool(data.get("active", False)),
            absent_since=_parse(data.get("absent_since")),
            present_since=_parse(data.get("present_since")),
            since=_parse(data.get("since")),
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
