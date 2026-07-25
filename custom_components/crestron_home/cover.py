"""Crestron Home shade entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CrestronHomeApiError
from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity

ATTR_POSITION = "position"
CRESTRON_SHADE_POSITION_MAX = 65535


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home shades."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeShade(coordinator, item)
        for item in coordinator.data.get("shades", [])
        if item.get("id") is not None
    )


class CrestronHomeShade(CrestronHomeEntity, CoverEntity):
    """A Crestron Home shade."""

    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="shades")

    @property
    def current_cover_position(self) -> int | None:
        """Return current shade position."""
        item = self.item
        value = item.get("position", item.get("level"))
        if value is None:
            return None
        bounded_position = max(0, min(CRESTRON_SHADE_POSITION_MAX, int(value)))
        return round(bounded_position * 100 / CRESTRON_SHADE_POSITION_MAX)

    @property
    def is_closed(self) -> bool | None:
        """Return whether the shade is closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position <= 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._async_set_position(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self._async_set_position(0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        await self._async_set_position(int(kwargs[ATTR_POSITION]))

    async def _async_set_position(self, position: int) -> None:
        """Set the shade position and refresh state from the processor."""
        bounded_position = max(0, min(100, int(position)))
        crestron_position = round(bounded_position * CRESTRON_SHADE_POSITION_MAX / 100)
        try:
            await self.coordinator.api.async_set_shade_position(
                self._id,
                crestron_position,
            )
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home shade command failed: {err}") from err
        await self.coordinator.async_request_refresh()
