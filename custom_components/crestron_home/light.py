"""Crestron Home light entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CrestronHomeApiError
from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity

CRESTRON_LIGHT_LEVEL_MAX = 65535


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home lights."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeLight(coordinator, item)
        for item in coordinator.data.get("lights", [])
        if item.get("id") is not None
    )


class CrestronHomeLight(CrestronHomeEntity, LightEntity):
    """A Crestron Home light."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="lights")

    @property
    def is_on(self) -> bool | None:
        """Return true if the light is on."""
        level = self.item.get("level")
        if level is None:
            return None
        return int(level) > 0

    @property
    def color_mode(self) -> ColorMode:
        """Return the current color mode."""
        return ColorMode.BRIGHTNESS if self._is_dimmer else ColorMode.ONOFF

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return supported color modes."""
        return {ColorMode.BRIGHTNESS} if self._is_dimmer else {ColorMode.ONOFF}

    @property
    def brightness(self) -> int | None:
        """Return Home Assistant brightness from Crestron 16-bit level."""
        if not self._is_dimmer:
            return None
        level = self.item.get("level")
        if level is None:
            return None
        bounded_level = max(0, min(CRESTRON_LIGHT_LEVEL_MAX, int(level)))
        return round(bounded_level * 255 / CRESTRON_LIGHT_LEVEL_MAX)

    @property
    def _is_dimmer(self) -> bool:
        return self.item.get("subType") == "Dimmer"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        level = (
            round(int(brightness) * CRESTRON_LIGHT_LEVEL_MAX / 255)
            if brightness is not None
            else CRESTRON_LIGHT_LEVEL_MAX
        )
        await self._async_set_level(level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self._async_set_level(0)

    async def _async_set_level(self, level: int) -> None:
        """Set the light level and refresh state from the processor."""
        try:
            await self.coordinator.api.async_set_light_level(self._id, level)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home light command failed: {err}") from err
        await self.coordinator.async_request_refresh()
