"""Watchdog heartbeat, weather forecast and repair issues."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import DOMAIN, ISSUE_DELAY
from .core.engine import EngineResult
from .core.models import BoilerState, Reason

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 5


async def async_send_heartbeat(hass: HomeAssistant, url: str, armed: bool) -> bool:
    """Tell the relay watchdog script that HeatConductor is alive."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(HEARTBEAT_TIMEOUT):
            response = await session.get(url, params={"armed": "1" if armed else "0"})
            response.raise_for_status()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.debug("Watchdog heartbeat to %s failed: %s", url, err)
        return False
    return True


async def async_fetch_forecast(
    hass: HomeAssistant, weather_entity: str, now: datetime
) -> tuple[float | None, float | None]:
    """Mean forecast temperature of the next 6 and 12 hours."""
    for forecast_type in ("hourly", "twice_daily"):
        try:
            response: Any = await hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": forecast_type},
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.debug(
                "Forecast %s for %s not available: %s", forecast_type, weather_entity, err
            )
            continue
        forecast = ((response or {}).get(weather_entity) or {}).get("forecast") or []
        points: list[tuple[datetime, float]] = []
        for item in forecast:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            temperature = item.get("temperature")
            if when is not None and isinstance(temperature, (int, float)):
                points.append((when, float(temperature)))
        if points:
            return _mean_until(points, now, 6), _mean_until(points, now, 12)
    return None, None


def _mean_until(points: list[tuple[datetime, float]], now: datetime, hours: int) -> float | None:
    end = now + timedelta(hours=hours)
    values = [t for when, t in points if now - timedelta(hours=1) <= when <= end]
    return sum(values) / len(values) if values else None


@dataclass
class IssueTracker:
    """Raises repair issues for problems that last longer than ISSUE_DELAY."""

    hass: HomeAssistant
    since: dict[str, datetime] = field(default_factory=dict)
    active: set[str] = field(default_factory=set)

    def update(self, result: EngineResult, now: datetime, watchdog_problem: bool) -> None:
        """Create or delete issues according to the latest result."""
        decision = result.decision
        conditions = {
            "no_data": decision.state is BoilerState.FAILSAFE and decision.reason is Reason.NO_DATA,
            "relay_unavailable": decision.reason is Reason.RELAY_UNAVAILABLE,
            "watchdog_unreachable": watchdog_problem,
        }
        for issue_id, present in conditions.items():
            if not present:
                self.since.pop(issue_id, None)
                if issue_id in self.active:
                    ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                    self.active.discard(issue_id)
                continue
            started = self.since.setdefault(issue_id, now)
            if issue_id not in self.active and now - started >= ISSUE_DELAY:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=issue_id,
                )
                self.active.add(issue_id)

    def clear(self) -> None:
        """Remove all issues (on unload)."""
        for issue_id in list(self.active):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self.active.clear()
        self.since.clear()
