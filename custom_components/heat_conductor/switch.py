"""Switches of HeatConductor."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HeatConductorConfigEntry, HeatConductorCoordinator, Settings
from .entity import HeatConductorEntity


@dataclass(frozen=True, kw_only=True)
class HeatConductorSwitchDescription(SwitchEntityDescription):
    """Describes a settings switch."""

    value_fn: Callable[[Settings], bool]
    set_fn: Callable[[HeatConductorCoordinator, bool], Awaitable[None]]


SWITCHES: tuple[HeatConductorSwitchDescription, ...] = (
    HeatConductorSwitchDescription(
        key="automation",
        value_fn=lambda s: s.automation_enabled,
        set_fn=lambda c, v: c.async_set_automation(v),
    ),
    HeatConductorSwitchDescription(
        key="observation_mode",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.observation_mode,
        set_fn=lambda c, v: c.async_set_observation(v),
    ),
    HeatConductorSwitchDescription(
        key="room_control",
        value_fn=lambda s: s.room_control_enabled,
        set_fn=lambda c, v: c.async_set_room_control(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatConductorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities(SettingsSwitch(coordinator, d) for d in SWITCHES)


class SettingsSwitch(HeatConductorEntity, SwitchEntity):
    """Switch bound to a controller setting."""

    entity_description: HeatConductorSwitchDescription

    def __init__(
        self, coordinator: HeatConductorCoordinator, description: HeatConductorSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the setting."""
        return self.entity_description.value_fn(self.coordinator.settings)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the setting."""
        await self.entity_description.set_fn(self.coordinator, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the setting."""
        await self.entity_description.set_fn(self.coordinator, False)
