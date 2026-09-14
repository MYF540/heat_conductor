"""Boiler state machine: decides whether heat is requested.

Protects the boiler against short cycling (minimum run time, minimum pause,
maximum starts per hour) and applies the safety rules. In observation mode the
same logic runs against a virtual boiler, so its decisions can be compared with
reality before it is allowed to switch anything.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .demand import DemandSummary
from .models import BoilerState, ControlParams, OperatingMode, Reason

HOUR = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class BoilerInputs:
    """Everything the state machine needs for one step."""

    now: datetime
    demand: DemandSummary
    outdoor_smoothed: float | None
    flow_temperature: float | None
    mode: OperatingMode
    automation_enabled: bool
    actuator_active: bool
    relay_on: bool | None


@dataclass(frozen=True, slots=True)
class BoilerDecision:
    """Result of one step."""

    state: BoilerState
    reason: Reason
    request_heat: bool
    command_allowed: bool
    remaining: timedelta | None
    starts_last_hour: int


class BoilerController:
    """Short-cycle protected on/off controller with safety overrides."""

    def __init__(self, params: ControlParams) -> None:
        self.params = params
        self.is_on = False
        self.on_since: datetime | None = None
        self.off_since: datetime | None = None
        self.starts: deque[datetime] = deque()
        self.frost_active = False
        # True while the state mirrors the physical relay (not the virtual boiler).
        self.follows_relay = False
        self._started_at: datetime | None = None
        self._demand_since: datetime | None = None
        self._manual_until: datetime | None = None
        self._last_command: bool | None = None
        self._last_relay: bool | None = None

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize state that must survive a restart."""
        return {
            "is_on": self.is_on,
            "on_since": _iso(self.on_since),
            "off_since": _iso(self.off_since),
            "starts": [s.isoformat() for s in self.starts],
            "follows_relay": self.follows_relay,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore state saved by to_dict."""
        self.is_on = bool(data.get("is_on", False))
        self.on_since = _parse(data.get("on_since"))
        self.off_since = _parse(data.get("off_since"))
        self.starts = deque(s for s in map(_parse, data.get("starts", [])) if s is not None)
        self.follows_relay = bool(data.get("follows_relay", False))

    # -- commands ----------------------------------------------------------

    def note_command(self, value: bool) -> None:
        """Remember what was last sent to the relay (for manual detection)."""
        self._last_command = value

    # -- main step ---------------------------------------------------------

    def step(self, inp: BoilerInputs) -> BoilerDecision:
        """Advance the state machine by one evaluation."""
        p = self.params
        now = inp.now
        if self._started_at is None:
            self._started_at = now
        while self.starts and now - self.starts[0] >= HOUR:
            self.starts.popleft()

        if not inp.automation_enabled:
            self._last_relay = None
            self.follows_relay = False
            if inp.relay_on is not None and inp.relay_on != self.is_on:
                self._switch(inp.relay_on, now)
            return self._decide(BoilerState.DISABLED, Reason.AUTOMATION_DISABLED, command=False)

        if inp.actuator_active:
            if inp.relay_on is None:
                return self._decide(BoilerState.FAILSAFE, Reason.RELAY_UNAVAILABLE, command=False)
            self._track_relay(inp.relay_on, now)
            if self._manual_until is not None:
                if now < self._manual_until:
                    return self._decide(
                        BoilerState.MANUAL,
                        Reason.MANUAL_OVERRIDE,
                        command=False,
                        remaining=self._manual_until - now,
                    )
                self._manual_until = None
                self._last_command = inp.relay_on
        else:
            self._last_relay = None
            self._manual_until = None
            self.follows_relay = False

        demand = inp.demand
        if demand.total is None:
            if now - self._started_at < p.startup_grace:
                return self._decide(BoilerState.STARTING, Reason.STARTUP, command=False)
            self.frost_active = False
            return self._stop(now, BoilerState.FAILSAFE, Reason.NO_DATA, hard=True)

        if inp.flow_temperature is not None and inp.flow_temperature >= p.max_flow_temperature:
            self.frost_active = False
            return self._stop(now, BoilerState.FAILSAFE, Reason.OVERTEMPERATURE, hard=True)

        if demand.min_temperature is not None:
            if demand.min_temperature < p.frost_limit:
                self.frost_active = True
            elif demand.min_temperature >= p.frost_limit + p.frost_release_hysteresis:
                self.frost_active = False
        if self.frost_active:
            if self.is_on:
                return self._decide(BoilerState.FROST_PROTECTION, Reason.FROST_PROTECTION)
            return self._start(now, BoilerState.FROST_PROTECTION, Reason.FROST_PROTECTION)

        if inp.mode is OperatingMode.OFF:
            return self._stop(now, BoilerState.OFF, Reason.MODE_OFF, hard=True)
        if inp.mode is OperatingMode.FROST_PROTECTION:
            return self._stop(now, BoilerState.OFF, Reason.FROST_ONLY)
        if (
            inp.mode is not OperatingMode.COMFORT
            and inp.outdoor_smoothed is not None
            and inp.outdoor_smoothed >= p.heating_limit
        ):
            return self._stop(now, BoilerState.SUMMER, Reason.SUMMER_MODE)

        total = demand.total
        immediate = (demand.max_deficit or 0.0) >= p.immediate_start_deficit

        if self.is_on:
            self._demand_since = None
            if total <= p.stop_threshold and not immediate:
                return self._stop(now, BoilerState.OFF, Reason.DEMAND_SATISFIED)
            return self._decide(BoilerState.HEATING, Reason.DEMAND_CONTINUES)

        if total < p.start_threshold:
            self._demand_since = None
            if not immediate:
                return self._decide(BoilerState.OFF, Reason.NO_DEMAND)
        elif self._demand_since is None:
            self._demand_since = now

        if not immediate:
            waited = now - self._demand_since if self._demand_since else timedelta(0)
            if waited < p.start_confirm:
                return self._decide(
                    BoilerState.OFF,
                    Reason.WAITING_CONFIRMATION,
                    remaining=p.start_confirm - waited,
                )
        return self._start(
            now, BoilerState.HEATING, Reason.DEFICIT_START if immediate else Reason.DEMAND_START
        )

    # -- helpers -----------------------------------------------------------

    def _track_relay(self, relay_on: bool, now: datetime) -> None:
        """Follow the physical relay and detect switching we did not command."""
        previous = self._last_relay
        self._last_relay = relay_on
        if previous is None:
            self._last_command = relay_on
            if self.follows_relay and relay_on == self.is_on:
                # Restart while in control: the persisted timers are still valid.
                return
            # Taking over (e.g. leaving observation mode): adopt the physical state.
            # How long the relay has been off is unknown, so no pause is enforced.
            self.follows_relay = True
            if relay_on and not self.is_on:
                self.on_since = now
            if not relay_on:
                self.off_since = None
            self.is_on = relay_on
            return
        if relay_on == previous:
            # A relay lagging behind a command is retried by the coordinator.
            return
        if relay_on != self._last_command:
            self._manual_until = now + self.params.manual_override
        if relay_on != self.is_on:
            self._switch(relay_on, now)

    def _start(self, now: datetime, state: BoilerState, reason: Reason) -> BoilerDecision:
        p = self.params
        if self.off_since is not None and now - self.off_since < p.min_pause:
            return self._decide(
                BoilerState.OFF,
                Reason.WAITING_MIN_PAUSE,
                remaining=p.min_pause - (now - self.off_since),
            )
        if len(self.starts) >= p.max_starts_per_hour:
            return self._decide(
                BoilerState.OFF,
                Reason.WAITING_MAX_STARTS,
                remaining=self.starts[0] + HOUR - now,
            )
        self._switch(True, now)
        return self._decide(state, reason)

    def _stop(
        self, now: datetime, state: BoilerState, reason: Reason, *, hard: bool = False
    ) -> BoilerDecision:
        p = self.params
        if self.is_on and not hard and self.on_since is not None:
            ran = now - self.on_since
            if ran < p.min_run:
                return self._decide(
                    BoilerState.HEATING, Reason.MIN_RUNTIME, remaining=p.min_run - ran
                )
        if self.is_on:
            self._switch(False, now)
        return self._decide(state, reason)

    def _switch(self, on: bool, now: datetime) -> None:
        if on == self.is_on:
            return
        self.is_on = on
        if on:
            self.on_since = now
            self.starts.append(now)
            self._demand_since = None
        else:
            self.off_since = now

    def _decide(
        self,
        state: BoilerState,
        reason: Reason,
        *,
        command: bool = True,
        remaining: timedelta | None = None,
    ) -> BoilerDecision:
        return BoilerDecision(
            state=state,
            reason=reason,
            request_heat=self.is_on,
            command_allowed=command,
            remaining=remaining,
            starts_last_hour=len(self.starts),
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
