"""Shared entity helpers for Crestron Home."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator


class CrestronHomeEntity(CoordinatorEntity[CrestronHomeCoordinator]):
    """Base class for Crestron Home entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CrestronHomeCoordinator,
        item: dict[str, Any],
        *,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._id = item["id"]
        self._key = key
        self._attr_unique_id = f"{DOMAIN}_{key}_{self._id}"

    @property
    def item(self) -> dict[str, Any]:
        """Return the latest item payload."""
        for item in self.coordinator.data.get(self._key, []):
            if item.get("id") == self._id:
                return item
        return {}

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return self.item.get("name")

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        item = self.item
        if not item:
            return False
        status = item.get("connectionStatus")
        return status in (None, "online")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        item = self.item
        room = self.coordinator.data.get("rooms_by_id", {}).get(item.get("roomId"), {})
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._id))},
            name=item.get("name"),
            manufacturer="Crestron",
            model=item.get("type") or item.get("subType") or "Crestron Home Device",
            suggested_area=room.get("name"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common Crestron attributes."""
        item = self.item
        room = self.coordinator.data.get("rooms_by_id", {}).get(item.get("roomId"), {})
        return {
            "crestron_id": self._id,
            "room_id": item.get("roomId"),
            "room_name": room.get("name"),
            "connection_status": item.get("connectionStatus"),
            "sub_type": item.get("subType"),
        }
