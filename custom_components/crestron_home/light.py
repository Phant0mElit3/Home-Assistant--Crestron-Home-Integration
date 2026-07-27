"""Crestron Home light entities."""

from __future__ import annotations

from time import monotonic
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
OPTIMISTIC_LIGHT_TIMEOUT = 45


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
        self._optimistic_level: int | None = None
        self._optimistic_expires_at: float | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if the light is on."""
        level = self._current_level
        if level is None:
            return None
        return level > 0

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
        level = self._current_level
        if level is None:
            return None
        return _level_to_brightness(level)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return light diagnostic attributes."""
        attributes = super().extra_state_attributes
        attributes.update(
            {
                "crestron_level": self._polled_level,
                "optimistic_level": self._optimistic_level,
            }
        )
        return attributes

    @property
    def _is_dimmer(self) -> bool:
        return self.item.get("subType") == "Dimmer"

    @property
    def _current_level(self) -> int | None:
        """Return the current light level, including short-lived optimistic state."""
        if self._optimistic_level is not None and not self._optimistic_expired:
            return self._optimistic_level
        self._clear_optimistic_level()
        return self._polled_level

    @property
    def _polled_level(self) -> int | None:
        """Return the light level from the latest Crestron poll."""
        level = self.item.get("level")
        if level is None:
            return None
        return _clamp_level(level)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        level = (
            _brightness_to_level(brightness)
            if brightness is not None
            else CRESTRON_LIGHT_LEVEL_MAX
        )
        await self._async_set_level(level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self._async_set_level(0)

    async def _async_set_level(self, level: int) -> None:
        """Set the light level and refresh state from the processor."""
        bounded_level = _clamp_level(level)
        try:
            await self.coordinator.api.async_set_light_level(self._id, bounded_level)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home light command failed: {err}") from err
        self._set_optimistic_level(bounded_level)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic light state once Crestron confirms it or it expires."""
        if (
            self._optimistic_level is not None
            and (
                self._optimistic_expired
                or self._polled_level == self._optimistic_level
            )
        ):
            self._clear_optimistic_level()
        super()._handle_coordinator_update()

    @property
    def _optimistic_expired(self) -> bool:
        """Return whether the optimistic light state is stale."""
        return (
            self._optimistic_expires_at is not None
            and monotonic() >= self._optimistic_expires_at
        )

    def _set_optimistic_level(self, level: int) -> None:
        """Set a short-lived optimistic light level."""
        self._optimistic_level = level
        self._optimistic_expires_at = monotonic() + OPTIMISTIC_LIGHT_TIMEOUT

    def _clear_optimistic_level(self) -> None:
        """Clear optimistic light state."""
        self._optimistic_level = None
        self._optimistic_expires_at = None


def _brightness_to_level(brightness: Any) -> int:
    """Convert Home Assistant brightness to a Crestron 16-bit level."""
    return round(max(0, min(255, int(brightness))) * CRESTRON_LIGHT_LEVEL_MAX / 255)


def _level_to_brightness(level: Any) -> int:
    """Convert a Crestron 16-bit level to Home Assistant brightness."""
    return round(_clamp_level(level) * 255 / CRESTRON_LIGHT_LEVEL_MAX)


def _clamp_level(level: Any) -> int:
    """Return a Crestron light level bounded to the documented 16-bit range."""
    return max(0, min(CRESTRON_LIGHT_LEVEL_MAX, int(level)))
