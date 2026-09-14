"""Sidebar panel registration."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PANEL_ELEMENT, PANEL_STATIC_URL, PANEL_URL

FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = "heat-conductor-panel.js"
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Add the HeatConductor entry to the sidebar (visible to all users)."""
    if "frontend" not in hass.config.components or getattr(hass, "http", None) is None:
        return
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[_STATIC_REGISTERED] = True
    if PANEL_URL in hass.data.get(frontend.DATA_PANELS, {}):
        return
    version = await hass.async_add_executor_job(_file_hash)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="HeatConductor",
        sidebar_icon="mdi:radiator",
        module_url=f"{PANEL_STATIC_URL}/{PANEL_FILE}?v={version}",
        require_admin=False,
        config={},
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar entry."""
    if PANEL_URL in hass.data.get(frontend.DATA_PANELS, {}):
        frontend.async_remove_panel(hass, PANEL_URL)


def _file_hash() -> str:
    return hashlib.sha256((FRONTEND_DIR / PANEL_FILE).read_bytes()).hexdigest()[:12]
