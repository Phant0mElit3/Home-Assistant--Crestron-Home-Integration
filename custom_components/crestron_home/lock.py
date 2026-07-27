"""Crestron Home door lock entities."""

from __future__ import annotations

from time import monotonic
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

OPTIMISTIC_LOCK_TIMEOUT = 45
LOCKED_VALUES = {"1", "lock", "locked", "secure", "secured", "true"}
UNLOCKED_VALUES = {"0", "false", "unlock", "unlocked", "unsecure", "unsecured"}
LOCKING_VALUES = {"lockinprogress", "locking"}
UNLOCKING_VALUES = {"unlockinprogress", "unlocking"}
JAMMED_VALUES = {"jam", "jammed", "lockjammed"}
STATE_KEYS = (
    "status",
    "state",
    "lockState",
    "doorLockStatus",
    "lock status",
    "locked",
    "isLocked",
)


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
        self._optimistic_locked: bool | None = None
        self._optimistic_expires_at: float | None = None

    @property
    def is_locked(self) -> bool | None:
        """Return whether the lock is locked."""
        if self._optimistic_locked is not None and not self._optimistic_expired:
            return self._optimistic_locked
        self._clear_optimistic_state()
        return self._polled_locked

    @property
    def _polled_locked(self) -> bool | None:
        """Return lock state from the latest Crestron poll."""
        for value in self._state_values:
            parsed = _parse_locked_value(value)
            if parsed is not None:
                return parsed
        return None

    @property
    def _state_values(self) -> list[Any]:
        """Return the Crestron payload values that may contain lock state."""
        item = self.item
        return [item[key] for key in STATE_KEYS if key in item and item[key] is not None]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return lock diagnostic attributes."""
        attributes = super().extra_state_attributes
        attributes.update(
            {
                "crestron_lock_status": self.item.get("status"),
                "crestron_lock_state": self.item.get("state", self.item.get("lockState")),
                "crestron_door_lock_status": self.item.get(
                    "doorLockStatus",
                    self.item.get("lock status"),
                ),
                "optimistic_lock": self._optimistic_locked,
                "lock_payload_keys": sorted(str(key) for key in self.item),
            }
        )
        return attributes

    @property
    def is_locking(self) -> bool:
        """Return whether the lock is locking."""
        return any(_normalize_lock_value(value) in LOCKING_VALUES for value in self._state_values)

    @property
    def is_unlocking(self) -> bool:
        """Return whether the lock is unlocking."""
        return any(_normalize_lock_value(value) in UNLOCKING_VALUES for value in self._state_values)

    @property
    def is_jammed(self) -> bool:
        """Return whether the lock reports a jam."""
        return any(_normalize_lock_value(value) in JAMMED_VALUES for value in self._state_values)

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door."""
        try:
            await self.coordinator.api.async_lock_door(self._id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home lock command failed: {err}") from err
        self._set_optimistic_state(True)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door."""
        try:
            await self.coordinator.api.async_unlock_door(self._id)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home unlock command failed: {err}") from err
        self._set_optimistic_state(False)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic lock state once Crestron confirms it or it expires."""
        if (
            self._optimistic_locked is not None
            and (
                self._optimistic_expired
                or self._polled_locked == self._optimistic_locked
            )
        ):
            self._clear_optimistic_state()
        super()._handle_coordinator_update()

    @property
    def _optimistic_expired(self) -> bool:
        """Return whether the optimistic lock state is stale."""
        return (
            self._optimistic_expires_at is not None
            and monotonic() >= self._optimistic_expires_at
        )

    def _set_optimistic_state(self, locked: bool) -> None:
        """Set a short-lived optimistic lock state."""
        self._optimistic_locked = locked
        self._optimistic_expires_at = monotonic() + OPTIMISTIC_LOCK_TIMEOUT

    def _clear_optimistic_state(self) -> None:
        """Clear optimistic lock state."""
        self._optimistic_locked = None
        self._optimistic_expires_at = None


def _parse_locked_value(value: Any) -> bool | None:
    """Parse a Crestron lock state value."""
    if isinstance(value, bool):
        return value
    normalized = _normalize_lock_value(value)
    if normalized in UNLOCKED_VALUES:
        return False
    if normalized in LOCKED_VALUES:
        return True
    return None


def _normalize_lock_value(value: Any) -> str:
    """Normalize Crestron lock state strings for loose matching."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return "".join(character for character in str(value).lower() if character.isalnum())
