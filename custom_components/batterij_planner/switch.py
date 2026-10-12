"""Schakelaar om de sturing van de omvormer aan/uit te zetten."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import BatterijPlannerConfigEntry
from .entity import BatterijPlannerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: BatterijPlannerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SturingSwitch(entry.runtime_data)])


class SturingSwitch(BatterijPlannerEntity, SwitchEntity, RestoreEntity):
    """Uit = alleen rekenen (meekijken), aan = omvormer aansturen."""

    _attr_name = "Sturing actief"
    _attr_icon = "mdi:robot"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sturing")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        vorig = await self.async_get_last_state()
        if vorig is not None and vorig.state == "on":
            self.coordinator.actief = True
            self.hass.async_create_task(self.coordinator.async_request_refresh())

    @property
    def is_on(self) -> bool:
        return self.coordinator.actief

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.actief = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.actief = False
        self.async_write_ha_state()
        await self.coordinator.async_naar_zelfverbruik()
