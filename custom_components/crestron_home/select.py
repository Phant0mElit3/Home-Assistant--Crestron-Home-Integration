"""Crestron Home select entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CrestronHomeApiError
from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity
from .media_sources import (
    payload_keys,
    raw_source_keys,
    source_id,
    source_map,
    source_name,
    source_options,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home selects."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeMediaRoomSourceSelect(coordinator, item)
        for item in coordinator.data.get("mediarooms", [])
        if item.get("id") is not None
    )


class CrestronHomeMediaRoomSourceSelect(CrestronHomeEntity, SelectEntity):
    """A Crestron Home media room source selector."""

    _attr_translation_key = "media_room_source"

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="mediarooms")
        self._attr_unique_id = f"{DOMAIN}_mediarooms_{self._id}_source"

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        room_name = self.item.get("name")
        return f"{room_name} Source" if room_name else "Source"

    @property
    def options(self) -> list[str]:
        """Return source options."""
        return [source["name"] for source in source_options(self.item)]

    @property
    def current_option(self) -> str | None:
        """Return the selected source option."""
        item = self.item
        provider_id = source_id(item)
        if provider_id is not None:
            for source in source_options(item):
                if str(source["id"]) == str(provider_id):
                    return source["name"]
        current = item.get("currentProvider", item.get("currentSource", item.get("source")))
        return source_name(current) if current is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return source diagnostic attributes."""
        attributes = super().extra_state_attributes
        attributes.update(
            {
                "current_source_id": source_id(self.item),
                "media_room_payload_keys": payload_keys(self.item),
                "source_map": source_map(self.item),
                "source_payload_keys": raw_source_keys(self.item),
            }
        )
        return attributes

    async def async_select_option(self, option: str) -> None:
        """Select a media room source."""
        source_id = None
        for source in source_options(self.item):
            if source["name"] == option:
                source_id = source["id"]
                break
        if source_id is None:
            raise HomeAssistantError(f"Unknown Crestron Home media source: {option}")
        try:
            await self.coordinator.api.async_set_media_room_source(self._id, source_id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home media source failed: {err}") from err
        await self.coordinator.async_request_refresh()
