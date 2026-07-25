"""Crestron Home binary sensor entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home sensors."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeBinarySensor(coordinator, item)
        for item in coordinator.data.get("binary_sensors", [])
        if item.get("id") is not None
    )


class CrestronHomeBinarySensor(CrestronHomeEntity, BinarySensorEntity):
    """A Crestron Home binary sensor."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="binary_sensors")

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the sensor device class."""
        subtype = str(self.item.get("subType", ""))
        if subtype == "OccupancySensor":
            return BinarySensorDeviceClass.OCCUPANCY
        if subtype in ("Contact", "DoorSensor", "SensorContact"):
            return BinarySensorDeviceClass.DOOR
        if subtype == "Doorbell":
            return getattr(BinarySensorDeviceClass, "SOUND", None)
        return None

    @property
    def is_on(self) -> bool | None:
        """Return sensor state when exposed by Crestron."""
        item = self.item
        for key in (
            "status",
            "state",
            "value",
            "presence",
            "door status",
            "occupied",
            "pressed",
            "open",
        ):
            if key in item:
                value = item[key]
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    if value.lower() == "unavailable":
                        return None
                    return value.lower() in (
                        "true",
                        "on",
                        "active",
                        "occupied",
                        "pressed",
                        "open",
                    )
                if isinstance(value, int):
                    return value != 0
        return None
