"""HeatConductor: holistic heating control for Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: HeatConductorConfigEntry) -> bool:
    """Set up HeatConductor from a config entry."""
    coordinator = HeatConductorCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(coordinator.async_start_tracking())
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeatConductorConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_persist_now()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: HeatConductorConfigEntry) -> None:
    """Reload when options or rooms change."""
    await hass.config_entries.async_reload(entry.entry_id)
