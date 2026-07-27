"""Shared entity helpers for Crestron Home."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator

ROOM_ID_KEYS = ("roomId", "roomID", "room_id", "room")
ROOM_NAME_KEYS = ("roomName", "room name", "area", "areaName")


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
    def suggested_area(self) -> str | None:
        """Return the Home Assistant suggested area from the Crestron room."""
        return self.room_name

    @property
    def room_id(self) -> Any:
        """Return the Crestron room id for this entity."""
        item = self.item
        for key in ROOM_ID_KEYS:
            value = item.get(key)
            if isinstance(value, dict):
                room_id = value.get("id", value.get("roomId"))
                if room_id is not None:
                    return room_id
            elif value is not None:
                return value
        return None

    @property
    def room_info(self) -> dict[str, Any]:
        """Return the Crestron room payload for this entity."""
        room_id = self.room_id
        rooms_by_id = self.coordinator.data.get("rooms_by_id", {})
        return rooms_by_id.get(room_id) or rooms_by_id.get(str(room_id)) or {}

    @property
    def room_name(self) -> str | None:
        """Return the Crestron room name for this entity."""
        room = self.room_info
        for key in ("name", *ROOM_NAME_KEYS):
            value = room.get(key)
            if value:
                return str(value)
        item = self.item
        for key in ROOM_NAME_KEYS:
            value = item.get(key)
            if value:
                return str(value)
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        item = self.item
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._id))},
            name=item.get("name"),
            manufacturer="Crestron",
            model=item.get("type") or item.get("subType") or "Crestron Home Device",
            suggested_area=self.room_name,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common Crestron attributes."""
        item = self.item
        return {
            "crestron_id": self._id,
            "room_id": self.room_id,
            "room_name": self.room_name,
            "connection_status": item.get("connectionStatus"),
            "sub_type": item.get("subType"),
        }
