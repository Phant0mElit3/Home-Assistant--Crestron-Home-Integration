"""Crestron Home door lock entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
    """Set up Crestron Home door locks."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeDoorLock(coordinator, item)
        for item in coordinator.data.get("doorlocks", [])
        if item.get("id") is not None
    )


class CrestronHomeDoorLock(CrestronHomeEntity, LockEntity):
    """A Crestron Home door lock."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="doorlocks")

    @property
    def is_locked(self) -> bool | None:
        """Return whether the lock is locked."""
        item = self.item
        value = item.get("status", item.get("state", item.get("lockState")))
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value).lower() in ("locked", "lock", "true", "1")

    @property
    def is_locking(self) -> bool:
        """Return whether the lock is locking."""
        return str(self.item.get("status", "")).lower() in ("locking", "lockinprogress")

    @property
    def is_unlocking(self) -> bool:
        """Return whether the lock is unlocking."""
        return str(self.item.get("status", "")).lower() in ("unlocking", "unlockinprogress")

    @property
    def is_jammed(self) -> bool:
        """Return whether the lock reports a jam."""
        return str(self.item.get("status", "")).lower() in ("jammed", "lockjammed")

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door."""
        try:
            await self.coordinator.api.async_lock_door(self._id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home lock command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door."""
        try:
            await self.coordinator.api.async_unlock_door(self._id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home unlock command failed: {err}") from err
        await self.coordinator.async_request_refresh()
