"""Crestron Home sensor entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
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
        CrestronHomeSensor(coordinator, item)
        for item in coordinator.data.get("sensor_entities", [])
        if item.get("id") is not None and item.get("value_key") is not None
    )


class CrestronHomeSensor(CrestronHomeEntity, SensorEntity):
    """A Crestron Home sensor."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="sensor_entities")
        self._value_key = item["value_key"]
        unique_value_key = str(self._value_key).replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_sensor_{self._id}_{unique_value_key}"

    @property
    def name(self) -> str | None:
        """Return the sensor entity name."""
        item = self.item
        base_name = item.get("name")
        value_key = self._value_key.replace("_", " ").title()
        return f"{base_name} {value_key}" if base_name else value_key

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        return self.item.get(self._value_key)

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the sensor device class."""
        key = self._value_key.lower()
        if "battery" in key and isinstance(self.native_value, (int, float)):
            return SensorDeviceClass.BATTERY
        if key == "temperature":
            return SensorDeviceClass.TEMPERATURE
        if key == "humidity":
            return SensorDeviceClass.HUMIDITY
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        key = self._value_key.lower()
        if "battery" in key and isinstance(self.native_value, (int, float)):
            return PERCENTAGE
        if key == "temperature":
            return UnitOfTemperature.FAHRENHEIT
        if key == "humidity":
            return PERCENTAGE
        return None
