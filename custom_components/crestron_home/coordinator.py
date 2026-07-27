"""Data coordinator for Crestron Home."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import CrestronHomeApi
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .media_sources import payload_keys, raw_source_keys, source_map

_LOGGER = logging.getLogger(__name__)

BINARY_SENSOR_SUBTYPES = {
    "contact",
    "doorsensor",
    "doorbell",
    "gate",
    "motionsensor",
    "occupancysensor",
    "presence",
    "sensorcontact",
}
SENSOR_VALUE_KEYS = (
    "level",
    "value",
    "batteryLevel",
    "battery level",
    "battery",
    "temperature",
    "humidity",
    "illuminance",
    "lux",
)


class CrestronHomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll Crestron Home inventory/state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CrestronHomeApi,
        *,
        scan_interval=DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        inventory = await self.api.async_get_inventory()
        rooms = _extract_items(inventory.get("rooms"), "rooms")
        devices = _extract_items(inventory.get("devices"), "devices")
        lights = _extract_items(inventory.get("lights"), "lights")
        shades = _extract_items(inventory.get("shades"), "shades")
        thermostats = _extract_items(inventory.get("thermostats"), "thermostats")
        scenes = _extract_items(inventory.get("scenes"), "scenes")
        doorlocks = _merge_by_id(
            [device for device in devices if _is_lock_device(device)],
            _extract_items(
                inventory.get("doorlocks"),
                "doorLocks",
                "doorlocks",
                "locks",
            ),
        )
        mediarooms = _extract_items(
            inventory.get("mediarooms"),
            "mediaRooms",
            "mediarooms",
            "rooms",
        )
        securitydevices = _extract_items(
            inventory.get("securitydevices"),
            "securityDevices",
            "securitydevices",
            "devices",
        )
        quickactions = _extract_items(
            inventory.get("quickactions"),
            "quickActions",
            "quickactions",
            "actions",
        )
        sensors = _merge_by_id(
            _extract_items(inventory.get("sensors"), "sensors"),
            [device for device in devices if str(device.get("type", "")).lower() == "sensor"],
        )
        binary_sensors = [sensor for sensor in sensors if _is_binary_sensor(sensor)]
        sensor_entities = _sensor_entities(sensors)

        data = {
            "rooms": rooms,
            "rooms_by_id": _rooms_by_id(rooms),
            "devices": devices,
            "lights": lights,
            "shades": shades,
            "thermostats": thermostats,
            "scenes": scenes,
            "doorlocks": doorlocks,
            "mediarooms": mediarooms,
            "securitydevices": securitydevices,
            "quickactions": quickactions,
            "sensors": sensors,
            "binary_sensors": binary_sensors,
            "sensor_entities": sensor_entities,
        }
        _LOGGER.debug(
            "Crestron Home inventory refreshed: %s rooms, %s devices, %s lights, "
            "%s shades, %s thermostats, %s scenes, %s door locks, %s media rooms, "
            "%s security devices, %s sensors, %s quick actions",
            len(rooms),
            len(devices),
            len(lights),
            len(shades),
            len(thermostats),
            len(scenes),
            len(doorlocks),
            len(mediarooms),
            len(securitydevices),
            len(sensors),
            len(quickactions),
        )
        for media_room in mediarooms:
            _LOGGER.debug(
                "Crestron Home media room source diagnostics: id=%s name=%s keys=%s "
                "source_keys=%s source_map=%s",
                media_room.get("id"),
                media_room.get("name"),
                payload_keys(media_room),
                raw_source_keys(media_room),
                source_map(media_room),
            )
        for quickaction in quickactions:
            _LOGGER.debug(
                "Crestron Home quick action diagnostics: id=%s name=%s keys=%s payload=%s",
                quickaction.get("id"),
                quickaction.get("name"),
                sorted(str(key) for key in quickaction),
                quickaction,
            )
        for thermostat in thermostats:
            _LOGGER.debug(
                "Crestron Home thermostat diagnostics: id=%s name=%s keys=%s "
                "mode=%s fan_mode=%s schedule=%s units=%s setpoints=%s "
                "available_modes=%s available_fan_modes=%s available_scheduler_states=%s",
                thermostat.get("id"),
                thermostat.get("name"),
                sorted(str(key) for key in thermostat),
                thermostat.get("currentMode", thermostat.get("mode")),
                thermostat.get("currentFanMode", thermostat.get("fanMode")),
                thermostat.get("currentSchedulerState", thermostat.get("schedulerState")),
                thermostat.get("temperatureUnits"),
                thermostat.get("currentSetPoint", thermostat.get("setPoint")),
                thermostat.get("availableSystemModes"),
                thermostat.get("availableFanModes"),
                thermostat.get("availableSchedulerStates"),
            )
        return data


def _extract_items(payload: Any, *keys: str) -> list[dict[str, Any]]:
    """Extract a list from a Crestron endpoint payload."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    for value in payload.values():
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _rooms_by_id(rooms: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    """Build a tolerant room lookup for Crestron payload id variations."""
    rooms_by_id: dict[Any, dict[str, Any]] = {}
    for room in rooms:
        room_id = room.get("id", room.get("roomId"))
        if room_id is None:
            continue
        rooms_by_id[room_id] = room
        rooms_by_id[str(room_id)] = room
        if isinstance(room_id, str) and room_id.isdigit():
            rooms_by_id[int(room_id)] = room
    return rooms_by_id


def _merge_by_id(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge item lists, preferring later groups with the same id."""
    merged: dict[Any, dict[str, Any]] = {}
    without_id: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            item_id = item.get("id")
            if item_id is None:
                without_id.append(item)
                continue
            merged[item_id] = item
    return list(merged.values()) + without_id


def _is_binary_sensor(item: dict[str, Any]) -> bool:
    """Return whether a Crestron sensor should be a binary sensor."""
    subtype = str(item.get("subType", item.get("type", ""))).replace(" ", "").lower()
    if subtype in BINARY_SENSOR_SUBTYPES:
        return True
    for key in ("status", "state", "value", "occupied", "pressed", "open"):
        value = item.get(key)
        if isinstance(value, bool):
            return True
        if isinstance(value, str) and value.lower() in {
            "active",
            "closed",
            "false",
            "inactive",
            "off",
            "on",
            "open",
            "occupied",
            "pressed",
            "true",
        }:
            return True
    return False


def _is_lock_device(item: dict[str, Any]) -> bool:
    """Return whether a generic Crestron device payload looks like a door lock."""
    device_type = str(item.get("type", "")).replace(" ", "").lower()
    subtype = str(item.get("subType", "")).replace(" ", "").lower()
    return device_type in {"lock", "doorlock", "doorlocks"} or subtype in {
        "lock",
        "doorlock",
        "doorlocks",
    }


def _sensor_entities(sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build derived sensor entities from non-binary Crestron sensor values."""
    entities: list[dict[str, Any]] = []
    for sensor in sensors:
        for value_key in SENSOR_VALUE_KEYS:
            if value_key not in sensor:
                continue
            item = dict(sensor)
            item["value_key"] = value_key
            entities.append(item)
            break
    return entities
