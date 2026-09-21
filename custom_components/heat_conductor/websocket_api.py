"""WebSocket API for the HeatConductor panel."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .const import ALL_DEFAULTS, DOMAIN
from .coordinator import HeatConductorCoordinator
from .core.models import RoomKind
from .params import GROUPS, PARAMS, curve_advice_params, validate

CENTRAL_HISTORY_KEYS = (
    "total_demand",
    "heat_request",
    "burner_active",
    "outdoor_temperature",
    "outdoor_temperature_smoothed",
    "boiler_state",
    "decision_reason",
)


@callback
def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Register all commands."""
    for command in (
        ws_state,
        ws_params,
        ws_params_set,
        ws_params_reset,
        ws_changelog,
        ws_learning,
        ws_learning_reset,
        ws_simulate,
    ):
        websocket_api.async_register_command(hass, command)


def _coordinator(hass: HomeAssistant) -> HeatConductorCoordinator | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data if entries else None


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


def _not_loaded(connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_error(msg["id"], "not_loaded", "HeatConductor is not set up")


def build_state(hass: HomeAssistant, coordinator: HeatConductorCoordinator) -> dict[str, Any]:
    """Everything the overview needs."""
    result = coordinator.data
    registry = er.async_get(hass)
    entry_id = coordinator.config_entry.entry_id

    def entity_id(platform: str, unique_id: str) -> str | None:
        return registry.async_get_entity_id(platform, DOMAIN, unique_id)

    history_entities = {
        key: entity_id(platform, f"{entry_id}_{key}")
        for key in CENTRAL_HISTORY_KEYS
        for platform in ("sensor", "binary_sensor")
        if entity_id(platform, f"{entry_id}_{key}")
    }
    for key in ("flow_temperature", "return_temperature"):
        if (source := getattr(coordinator.entities, key)) is not None:
            history_entities[key] = source

    rooms: list[dict[str, Any]] = []
    for room in coordinator.rooms:
        data = result.room(room.room_id) if result else None
        setpoint = result.setpoint(room.room_id) if result else None
        runtime = (
            coordinator.engine.runtime(room.room_id) if room.kind is RoomKind.REGULATED else None
        )
        rooms.append(
            {
                "room_id": room.room_id,
                "name": room.name,
                "kind": room.kind.value,
                "weight": room.weight,
                "status": data.status.value if data else None,
                "demand": data.demand if data else None,
                "temperature": data.temperature if data else None,
                "target": data.target if data else None,
                "deficit": data.deficit if data else None,
                "valve": data.valve if data else None,
                "setpoint": _jsonable(asdict(setpoint)) if setpoint else None,
                "comfort": runtime.comfort if runtime else None,
                "eco": runtime.eco if runtime else None,
                "enabled": runtime.enabled if runtime else None,
                "usage_entities": len(room.usage_entities),
                "usage_enabled": runtime.usage_enabled if runtime else None,
                "in_use": setpoint.room_active if setpoint else None,
                "temperature_entity": entity_id("sensor", f"{room.room_id}_room_temperature"),
                "target_entity": entity_id("sensor", f"{room.room_id}_room_target"),
            }
        )

    state: dict[str, Any] = {
        "loaded": result is not None,
        "settings": coordinator.settings.to_dict(),
        "actuator_active": coordinator.actuator_active,
        "watchdog": coordinator.watchdog_connected(),
        "params": {meta.key: coordinator.options.get(meta.key, meta.default) for meta in PARAMS},
        "history_entities": history_entities,
        "rooms": rooms,
        "changelog_times": [entry["time"] for entry in coordinator.changelog[-100:]],
    }
    if result is None:
        return state
    decision = result.decision
    state.update(
        {
            "decision": {
                "state": decision.state.value,
                "reason": decision.reason.value,
                "request_heat": decision.request_heat,
                "remaining_seconds": decision.remaining.total_seconds()
                if decision.remaining
                else None,
                "starts_last_hour": decision.starts_last_hour,
                "on_since": _jsonable(coordinator.engine.boiler.on_since),
                "off_since": _jsonable(coordinator.engine.boiler.off_since),
            },
            "demand": _jsonable(asdict(result.demand)),
            "outdoor": {
                "value": result.outdoor.value,
                "source": result.outdoor.source,
                "smoothed": result.outdoor_smoothed,
                "forecast_6h": result.forecast_6h,
                "forecast_12h": result.forecast_12h,
            },
            "boiler": {
                "flow_temperature": result.flow_temperature,
                "return_temperature": result.return_temperature,
                "spread": result.spread,
                "burner_active": result.burner_active,
                "diagnosis": _jsonable(asdict(result.diagnosis)),
                "feedback_configured": {
                    "relay_feedback": coordinator.entities.relay_feedback is not None,
                    "burner_lock": coordinator.entities.burner_lock is not None,
                    "winter_mode": coordinator.entities.boiler_winter_mode is not None,
                    "pump": coordinator.entities.pump is not None,
                    "boiler_flow": coordinator.entities.boiler_flow_temperature is not None,
                },
                "boiler_stats": _jsonable(asdict(result.boiler_stats)),
                "burner_stats": _jsonable(asdict(result.burner_stats))
                if result.burner_stats
                else None,
            },
            "energy": _jsonable(asdict(result.energy)),
            "room_control_active": result.room_control_active,
            "vacation": {
                "active": result.vacation_active,
                "automatic": result.auto_vacation_active,
                "since": _jsonable(coordinator.engine.auto_vacation.since),
                "nobody_home_since": _jsonable(coordinator.engine.auto_vacation.absent_since),
            },
            "sleep": {
                "sleeping": result.sleep.sleeping,
                "source": result.sleep.source.value,
                "since": _jsonable(result.sleep.since),
                "sensor": result.sleep.sensor_sleeping,
                "window": {
                    "start": coordinator.sleep_params.window_start,
                    "end": coordinator.sleep_params.window_end,
                },
            },
            "learned_schedule": {
                "enabled": coordinator.settings.learned_schedule_enabled,
                "comfort_now": result.learned_schedule_on,
            },
            "duty_cycle_ok": result.duty_cycle_ok,
            "solar_ratio": result.solar_ratio,
        }
    )
    return state


@websocket_api.websocket_command({vol.Required("type"): "heat_conductor/state"})
@websocket_api.async_response
async def ws_state(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Current state."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    connection.send_result(msg["id"], build_state(hass, coordinator))


@websocket_api.websocket_command({vol.Required("type"): "heat_conductor/params"})
@websocket_api.async_response
async def ws_params(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Parameter metadata with current values."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    connection.send_result(
        msg["id"],
        {
            "groups": list(GROUPS),
            "params": [
                {**meta.as_dict(), "value": coordinator.options.get(meta.key, meta.default)}
                for meta in PARAMS
            ],
            "can_edit": connection.user.is_admin,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "heat_conductor/params/set", vol.Required("values"): dict}
)
@websocket_api.async_response
async def ws_params_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change parameters (admins only)."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    try:
        values = validate(msg["values"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    await coordinator.async_set_params(values, connection.user.name)
    connection.send_result(msg["id"], {"changed": sorted(values)})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "heat_conductor/params/reset", vol.Optional("keys"): [str]}
)
@websocket_api.async_response
async def ws_params_reset(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Reset parameters to defaults (admins only)."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    keys = msg.get("keys") or [meta.key for meta in PARAMS]
    unknown = [key for key in keys if key not in ALL_DEFAULTS]
    if unknown:
        connection.send_error(msg["id"], "invalid_format", f"Unknown parameters: {unknown}")
        return
    await coordinator.async_set_params(
        {key: ALL_DEFAULTS[key] for key in keys}, connection.user.name
    )
    connection.send_result(msg["id"], {"reset": keys})


@websocket_api.websocket_command({vol.Required("type"): "heat_conductor/changelog"})
@websocket_api.async_response
async def ws_changelog(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Parameter change log, newest first."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    connection.send_result(msg["id"], {"entries": list(reversed(coordinator.changelog))})


@websocket_api.websocket_command({vol.Required("type"): "heat_conductor/learning"})
@websocket_api.async_response
async def ws_learning(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Learned values."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    names = {
        room.room_id: room.name for room in coordinator.rooms if room.kind is RoomKind.REGULATED
    }
    target_valve, curve_setting = curve_advice_params(coordinator.options)
    summary = coordinator.engine.learner.summary(
        names, target_valve=target_valve, curve_setting=curve_setting
    )
    connection.send_result(msg["id"], {**summary, "can_edit": connection.user.is_admin})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "heat_conductor/learning/reset", vol.Optional("room_id"): str}
)
@websocket_api.async_response
async def ws_learning_reset(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Forget learned values (admins only)."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    await coordinator.async_reset_learning(msg.get("room_id"))
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "heat_conductor/simulate",
        vol.Optional("values", default={}): dict,
        vol.Optional("hours", default=24): vol.All(int, vol.Range(min=1, max=168)),
    }
)
@websocket_api.async_response
async def ws_simulate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Replay recorded data with draft parameters (read-only, all users)."""
    if (coordinator := _coordinator(hass)) is None:
        _not_loaded(connection, msg)
        return
    if "recorder" not in hass.config.components:
        connection.send_error(msg["id"], "not_supported", "The recorder is not running")
        return
    try:
        values = validate(msg["values"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    from .simulation import async_simulate

    connection.send_result(msg["id"], await async_simulate(hass, coordinator, values, msg["hours"]))
