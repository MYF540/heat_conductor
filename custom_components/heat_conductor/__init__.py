"""HeatConductor: holistic heating control for Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator
from .panel import async_register_panel, async_remove_panel
from .services import async_setup_services
from .websocket_api import async_setup_websocket_api

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services and the WebSocket API once."""
    async_setup_services(hass)
    async_setup_websocket_api(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HeatConductorConfigEntry) -> bool:
    """Set up HeatConductor from a config entry."""
    coordinator = HeatConductorCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(coordinator.async_start_tracking())
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeatConductorConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_persist_now()
        async_remove_panel(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: HeatConductorConfigEntry) -> None:
    """Apply parameter changes live; reload for entity or room changes."""
    if entry.runtime_data.async_apply_options(entry):
        return
    await hass.config_entries.async_reload(entry.entry_id)
