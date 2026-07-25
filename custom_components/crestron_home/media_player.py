"""Crestron Home media room entities."""

from __future__ import annotations

from time import monotonic
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
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

CRESTRON_LEVEL_MAX = 65535
OPTIMISTIC_MUTE_TIMEOUT = 45


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home media rooms."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeMediaRoom(coordinator, item)
        for item in coordinator.data.get("mediarooms", [])
        if item.get("id") is not None
    )


class CrestronHomeMediaRoom(CrestronHomeEntity, MediaPlayerEntity):
    """A Crestron Home media room."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="mediarooms")
        self._optimistic_mute: bool | None = None
        self._optimistic_mute_expires_at: float | None = None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported media room features."""
        features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )
        if self.source_list:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        return features

    @property
    def state(self) -> MediaPlayerState:
        """Return current media room state."""
        item = self.item
        power = item.get("currentPowerState", item.get("powerState", item.get("power")))
        if str(power).lower() in ("off", "false", "0"):
            return MediaPlayerState.OFF
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        """Return current volume as a 0.0-1.0 value."""
        item = self.item
        if item.get("currentVolumeLevel") is not None:
            return _bounded_level(int(item["currentVolumeLevel"]) / CRESTRON_LEVEL_MAX)
        value = item.get("volume", item.get("level"))
        if value is None:
            return None
        level = int(value)
        scale = CRESTRON_LEVEL_MAX if level > 100 else 100
        return _bounded_level(level / scale)

    @property
    def is_volume_muted(self) -> bool | None:
        """Return whether the media room is muted."""
        if self._optimistic_mute is not None and not self._optimistic_mute_expired:
            return self._optimistic_mute
        self._clear_optimistic_mute()
        return self._polled_mute_state

    @property
    def _polled_mute_state(self) -> bool | None:
        """Return the mute state from the latest Crestron poll."""
        value = self.item.get("currentMuteState", self.item.get("muteState", self.item.get("muted")))
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value).lower() in ("muted", "mute", "true", "1", "on")

    @property
    def source(self) -> str | None:
        """Return current selected source."""
        item = self.item
        source = item.get("currentProvider", item.get("currentSource", item.get("source")))
        if source is not None:
            return source_name(source)
        provider_id = source_id(item)
        for source_item in self._sources:
            if str(source_item.get("id")) == str(provider_id):
                return source_item["name"]
        return None

    @property
    def source_list(self) -> list[str]:
        """Return available source names."""
        return [source["name"] for source in self._sources]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common and media source diagnostic attributes."""
        attributes = super().extra_state_attributes
        attributes.update(
            {
                "current_source_id": source_id(self.item),
                "optimistic_mute": self._optimistic_mute,
                "media_room_payload_keys": payload_keys(self.item),
                "source_map": source_map(self.item),
                "source_payload_keys": raw_source_keys(self.item),
            }
        )
        return attributes

    async def async_turn_on(self) -> None:
        """Turn on the media room."""
        await self._async_set_power(True)

    async def async_turn_off(self) -> None:
        """Turn off the media room."""
        await self._async_set_power(False)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the media room."""
        try:
            await self.coordinator.api.async_set_media_room_mute(self._id, mute)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home media mute failed: {err}") from err
        self._set_optimistic_mute(mute)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set media room volume."""
        level = round(max(0.0, min(1.0, float(volume))) * CRESTRON_LEVEL_MAX)
        try:
            await self.coordinator.api.async_set_media_room_volume(self._id, level)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home media volume failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select a media room source."""
        source_id = self._source_id_for_name(source)
        if source_id is None:
            raise HomeAssistantError(f"Unknown Crestron Home media source: {source}")
        try:
            await self.coordinator.api.async_set_media_room_source(self._id, source_id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home media source failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def _async_set_power(self, on: bool) -> None:
        try:
            await self.coordinator.api.async_set_media_room_power(self._id, on)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home media power failed: {err}") from err
        await self.coordinator.async_request_refresh()

    @property
    def _sources(self) -> list[dict[str, Any]]:
        return source_options(self.item)

    def _source_id_for_name(self, source_name: str) -> Any:
        for source in self._sources:
            if source["name"] == source_name:
                return source["id"]
        return None

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic mute once Crestron confirms or the override expires."""
        if (
            self._optimistic_mute is not None
            and (
                self._polled_mute_state == self._optimistic_mute
                or self._optimistic_mute_expired
            )
        ):
            self._clear_optimistic_mute()
        super()._handle_coordinator_update()

    @property
    def _optimistic_mute_expired(self) -> bool:
        """Return whether the optimistic mute state is stale."""
        return (
            self._optimistic_mute_expires_at is not None
            and monotonic() >= self._optimistic_mute_expires_at
        )

    def _set_optimistic_mute(self, mute: bool) -> None:
        """Temporarily reflect an accepted mute command before the next poll."""
        self._optimistic_mute = mute
        self._optimistic_mute_expires_at = monotonic() + OPTIMISTIC_MUTE_TIMEOUT

    def _clear_optimistic_mute(self) -> None:
        """Clear optimistic mute state."""
        self._optimistic_mute = None
        self._optimistic_mute_expires_at = None


def _bounded_level(value: float) -> float:
    """Return value clamped to Home Assistant's volume range."""
    return max(0.0, min(1.0, value))
