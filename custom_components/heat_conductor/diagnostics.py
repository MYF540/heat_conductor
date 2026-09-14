"""Diagnostics download for HeatConductor."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import HeatConductorConfigEntry


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HeatConductorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "options": dict(entry.options),
        "rooms": [_jsonable(asdict(room)) for room in coordinator.rooms],
        "settings": _jsonable(asdict(coordinator.settings)),
        "params": _jsonable(asdict(coordinator.params)),
        "engine_state": coordinator.engine.to_dict(),
        "last_result": _jsonable(asdict(coordinator.data)) if coordinator.data else None,
        "inputs": {
            entity_id: (
                {
                    "state": state.state,
                    "attributes": dict(state.attributes),
                    "last_reported": state.last_reported.isoformat(),
                }
                if (state := hass.states.get(entity_id))
                else None
            )
            for entity_id in sorted(coordinator.tracked_entities)
        },
    }
