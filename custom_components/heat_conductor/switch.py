"""Switches of HeatConductor."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    HeatConductorConfigEntry,
    HeatConductorCoordinator,
    RoomConfig,
    Settings,
)
from .core.models import RoomKind
from .entity import HeatConductorEntity, RoomEntity


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
    HeatConductorSwitchDescription(
        key="learned_schedule",
        value_fn=lambda s: s.learned_schedule_enabled,
        set_fn=lambda c, v: c.async_set_learned_schedule(v),
    ),
    HeatConductorSwitchDescription(
        key="heat_network",
        value_fn=lambda s: s.network_enabled,
        set_fn=lambda c, v: c.async_set_network(v),
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
    for room in coordinator.rooms:
        if room.kind is not RoomKind.REGULATED:
            continue
        entities: list[SwitchEntity] = []
        if room.usage_entities:
            entities.append(RoomUsageSwitch(coordinator, room))
        if room.climates:
            entities.append(RoomCoHeatSwitch(coordinator, room))
        if entities:
            async_add_entities(entities, config_subentry_id=room.room_id)


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


class RoomCoHeatSwitch(RoomEntity, SwitchEntity):
    """Whether the heat network may heat this room along."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HeatConductorCoordinator, room: RoomConfig) -> None:
        super().__init__(coordinator, room, "co_heating")

    @property
    def is_on(self) -> bool:
        """Return whether co-heating is allowed."""
        return self.coordinator.engine.runtime(self.room.room_id).co_heat_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allow co-heating."""
        await self.coordinator.async_set_room_co_heat(self.room.room_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Never co-heat this room."""
        await self.coordinator.async_set_room_co_heat(self.room.room_id, False)


class RoomUsageSwitch(RoomEntity, SwitchEntity):
    """Whether the room follows its activity sensors."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HeatConductorCoordinator, room: RoomConfig) -> None:
        super().__init__(coordinator, room, "usage_detection")

    @property
    def is_on(self) -> bool:
        """Return whether usage detection is active for this room."""
        return self.coordinator.engine.runtime(self.room.room_id).usage_enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show which entities report usage."""
        return {"activity_entities": list(self.room.usage_entities)}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Follow the activity sensors."""
        await self.coordinator.async_set_room_usage(self.room.room_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ignore the activity sensors."""
        await self.coordinator.async_set_room_usage(self.room.room_id, False)
