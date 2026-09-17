"""What-if simulation: replay recorded inputs with different parameters."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from .coordinator import HeatConductorCoordinator
from .core.engine import HeatingEngine
from .inputs import ControlState, EntityConfig, InputReader, build_snapshot
from .params import control_params, energy_params, setpoint_params, solar_reference

STEP = timedelta(minutes=1)
SERIES_STEP = timedelta(minutes=5)
DEFICIT_LIMIT = 0.5
MAX_HOURS = 168


@dataclass
class Timeline:
    """Recorded states of one entity, sorted by time."""

    times: list[float]
    states: list[State]

    def at(self, when: float) -> State | None:
        index = bisect_right(self.times, when) - 1
        return self.states[index] if index >= 0 else None


def _run(
    entities: EntityConfig,
    timelines: dict[str, Timeline],
    options: dict[str, Any],
    control_template: ControlState,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    engine = HeatingEngine(
        control_params(options),
        energy_params(options),
        setpoint_params(options),
        solar_reference(options),
    )
    now = start
    request_prev: bool | None = None
    burner_prev: bool | None = None
    starts = burner_starts = steps = deficit_steps = 0
    runtime = burner_runtime = 0.0
    series: list[dict[str, Any]] = []
    next_series = start
    while now <= end:
        timestamp = now.timestamp()
        getter: Callable[[str], State | None] = lambda entity_id, ts=timestamp: (  # noqa: E731
            timelines[entity_id].at(ts) if entity_id in timelines else None
        )
        snapshot = build_snapshot(
            entities, InputReader(getter, replay_time=now), now, control_template
        )
        result = engine.evaluate(snapshot)
        request = result.decision.request_heat
        burner = result.burner_active
        steps += 1
        if request:
            runtime += STEP.total_seconds() / 60
            if request_prev is False:
                starts += 1
        if burner:
            burner_runtime += STEP.total_seconds() / 60
            if burner_prev is False:
                burner_starts += 1
        if result.demand.max_deficit is not None and result.demand.max_deficit > DEFICIT_LIMIT:
            deficit_steps += 1
        request_prev, burner_prev = request, burner
        if now >= next_series:
            series.append(
                {
                    "t": now.isoformat(),
                    "demand": round((result.demand.total or 0.0) * 100, 1),
                    "request": 1 if request else 0,
                    "burner": None if burner is None else (1 if burner else 0),
                    "reason": result.decision.reason.value,
                }
            )
            next_series = now + SERIES_STEP
        now += STEP
    return {
        "starts": starts,
        "runtime_minutes": round(runtime),
        "deficit_share": round(deficit_steps / steps * 100, 1) if steps else None,
        "real_burner_starts": burner_starts if burner_prev is not None else None,
        "real_burner_runtime_minutes": round(burner_runtime) if burner_prev is not None else None,
        "series": series,
    }


async def async_simulate(
    hass: HomeAssistant,
    coordinator: HeatConductorCoordinator,
    draft: dict[str, float | bool],
    hours: int,
) -> dict[str, Any]:
    """Replay the last hours with current and draft parameters."""
    from homeassistant.components.recorder import get_instance, history

    hours = max(1, min(hours, MAX_HOURS))
    end = dt_util.now().replace(second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    entity_ids = sorted(coordinator.entities.tracked_entities)

    recorded: dict[str, list[State]] = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start - timedelta(hours=1),
            end,
            entity_ids,
            None,
            True,
            False,
            False,
            False,
            False,
        )
    )
    timelines = {
        entity_id: Timeline([s.last_updated.timestamp() for s in states], list(states))
        for entity_id, states in recorded.items()
        if states
    }
    control = ControlState(
        mode=coordinator.settings.mode,
        automation_enabled=True,
        actuator_active=False,
        room_control_enabled=False,
        learned_schedule_enabled=False,
        vacation_active=False,
    )
    current_options = dict(coordinator.options)
    draft_options = {**current_options, **draft}

    def _both() -> dict[str, Any]:
        return {
            "hours": hours,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "entities_with_history": len(timelines),
            "current": _run(coordinator.entities, timelines, current_options, control, start, end),
            "draft": _run(coordinator.entities, timelines, draft_options, control, start, end),
        }

    return await hass.async_add_executor_job(_both)
