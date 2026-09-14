"""Orchestrates one evaluation: rooms -> demand -> outdoor -> boiler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .boiler_fsm import BoilerController, BoilerDecision, BoilerInputs
from .demand import DemandSummary, RoomDemand, RoomInput, evaluate_room, summarize
from .models import ControlParams, OperatingMode, Reading
from .outdoor import ExponentialSmoother, OutdoorResult, fuse_outdoor
from .stats import DailyRuntime, RuntimeSnapshot


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    """All inputs of one evaluation, read from Home Assistant."""

    now: datetime
    rooms: tuple[RoomInput, ...]
    outdoor_sensors: tuple[Reading, ...]
    weather_temperature: Reading | None
    flow_temperature: Reading | None
    return_temperature: Reading | None
    gas_flow: Reading | None
    burner_on: bool | None
    relay_on: bool | None
    mode: OperatingMode
    automation_enabled: bool
    actuator_active: bool


@dataclass(frozen=True, slots=True)
class EngineResult:
    """Outputs of one evaluation."""

    rooms: tuple[RoomDemand, ...]
    demand: DemandSummary
    outdoor: OutdoorResult
    outdoor_smoothed: float | None
    decision: BoilerDecision
    flow_temperature: float | None
    return_temperature: float | None
    spread: float | None
    burner_active: bool | None
    boiler_stats: RuntimeSnapshot
    burner_stats: RuntimeSnapshot | None

    def room(self, room_id: str) -> RoomDemand | None:
        """Return the evaluated room with the given id."""
        return next((r for r in self.rooms if r.room_id == room_id), None)


class HeatingEngine:
    """Stateful evaluation pipeline."""

    def __init__(self, params: ControlParams) -> None:
        self.params = params
        self.boiler = BoilerController(params)
        self.outdoor_smoother = ExponentialSmoother(params.outdoor_smoothing)
        self.boiler_stats = DailyRuntime()
        self.burner_stats = DailyRuntime()

    def evaluate(self, snap: EngineSnapshot) -> EngineResult:
        """Run one evaluation."""
        p = self.params
        now = snap.now

        rooms = tuple(evaluate_room(room, now, p) for room in snap.rooms)
        demand = summarize(rooms)

        outdoor = fuse_outdoor(
            snap.outdoor_sensors, snap.weather_temperature, now, p.stale_after, p.outdoor_max_spread
        )
        smoothed = self.outdoor_smoother.update(outdoor.value, now)

        flow = (
            snap.flow_temperature.valid_value(now, p.stale_after) if snap.flow_temperature else None
        )
        ret = (
            snap.return_temperature.valid_value(now, p.stale_after)
            if snap.return_temperature
            else None
        )

        decision = self.boiler.step(
            BoilerInputs(
                now=now,
                demand=demand,
                outdoor_smoothed=smoothed,
                flow_temperature=flow,
                mode=snap.mode,
                automation_enabled=snap.automation_enabled,
                actuator_active=snap.actuator_active,
                relay_on=snap.relay_on,
            )
        )

        burner = snap.burner_on
        if burner is None and snap.gas_flow is not None:
            gas = snap.gas_flow.valid_value(now, p.stale_after)
            burner = gas >= p.burner_flow_threshold if gas is not None else None
        has_burner_source = snap.burner_on is not None or snap.gas_flow is not None

        return EngineResult(
            rooms=rooms,
            demand=demand,
            outdoor=outdoor,
            outdoor_smoothed=smoothed,
            decision=decision,
            flow_temperature=flow,
            return_temperature=ret,
            spread=flow - ret if flow is not None and ret is not None else None,
            burner_active=burner,
            boiler_stats=self.boiler_stats.update(now, decision.request_heat),
            burner_stats=self.burner_stats.update(now, burner) if has_burner_source else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize persistent state."""
        return {
            "boiler": self.boiler.to_dict(),
            "outdoor_smoothed": self.outdoor_smoother.value,
            "outdoor_smoothed_at": (
                self.outdoor_smoother.updated_at.isoformat()
                if self.outdoor_smoother.updated_at
                else None
            ),
            "boiler_stats": self.boiler_stats.to_dict(),
            "burner_stats": self.burner_stats.to_dict(),
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore state saved by to_dict."""
        self.boiler.restore(data.get("boiler", {}))
        value = data.get("outdoor_smoothed")
        at = data.get("outdoor_smoothed_at")
        if isinstance(value, (int, float)) and isinstance(at, str):
            try:
                self.outdoor_smoother.updated_at = datetime.fromisoformat(at)
                self.outdoor_smoother.value = float(value)
            except ValueError:
                pass
        self.boiler_stats.restore(data.get("boiler_stats", {}))
        self.burner_stats.restore(data.get("burner_stats", {}))
