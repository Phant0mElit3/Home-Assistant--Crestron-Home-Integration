"""Crestron Home button entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CrestronHomeApiError
from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home buttons."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeQuickActionButton(coordinator, item)
        for item in coordinator.data.get("quickactions", [])
        if item.get("id") is not None
    )


class CrestronHomeQuickActionButton(CrestronHomeEntity, ButtonEntity):
    """A Crestron Home quick action button."""

    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="quickactions")

    async def async_press(self) -> None:
        """Press the quick action."""
        try:
            await self.coordinator.api.async_recall_quick_action(self._id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home quick action failed: {err}") from err
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return quick action attributes."""
        attrs = super().extra_state_attributes
        item = self.item
        attrs.update(
            {
                "action_type": item.get("type"),
                "category": item.get("category"),
            }
        )
        return attrs
