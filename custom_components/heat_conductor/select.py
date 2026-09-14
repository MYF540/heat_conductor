"""Operating mode select of HeatConductor."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator
from .core.models import OperatingMode
from .entity import HeatConductorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatConductorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mode select."""
    async_add_entities([OperatingModeSelect(entry.runtime_data)])


class OperatingModeSelect(HeatConductorEntity, SelectEntity):
    """Global operating mode."""

    def __init__(self, coordinator: HeatConductorCoordinator) -> None:
        super().__init__(coordinator, "operating_mode")
        self._attr_options = [m.value for m in OperatingMode]

    @property
    def current_option(self) -> str:
        """Return the active mode."""
        return self.coordinator.settings.mode.value

    async def async_select_option(self, option: str) -> None:
        """Change the mode."""
        await self.coordinator.async_set_mode(OperatingMode(option))
