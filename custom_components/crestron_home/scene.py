"""Crestron Home scene entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.scene import Scene
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
    """Set up Crestron Home scenes."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeScene(coordinator, item)
        for item in coordinator.data.get("scenes", [])
        if item.get("id") is not None
    )


class CrestronHomeScene(CrestronHomeEntity, Scene):
    """A Crestron Home scene."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="scenes")

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene."""
        try:
            await self.coordinator.api.async_recall_scene(self._id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home scene activation failed: {err}") from err
        await self.coordinator.async_request_refresh()
