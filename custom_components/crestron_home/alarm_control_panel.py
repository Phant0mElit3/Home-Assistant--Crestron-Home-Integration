"""Crestron Home security device entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity

STATE_MAP = {
    "alarm": AlarmControlPanelState.TRIGGERED,
    "armed": AlarmControlPanelState.ARMED_AWAY,
    "armedaway": AlarmControlPanelState.ARMED_AWAY,
    "armedhome": AlarmControlPanelState.ARMED_HOME,
    "armedinstant": AlarmControlPanelState.ARMED_NIGHT,
    "armednight": AlarmControlPanelState.ARMED_NIGHT,
    "armstay": AlarmControlPanelState.ARMED_HOME,
    "disarmed": AlarmControlPanelState.DISARMED,
    "entrydelay": AlarmControlPanelState.PENDING,
    "exitdelay": AlarmControlPanelState.ARMING,
    "fire": AlarmControlPanelState.TRIGGERED,
    "notready": AlarmControlPanelState.DISARMED,
    "ready": AlarmControlPanelState.DISARMED,
    "triggered": AlarmControlPanelState.TRIGGERED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home security devices."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeSecurityDevice(coordinator, item)
        for item in coordinator.data.get("securitydevices", [])
        if item.get("id") is not None
    )


class CrestronHomeSecurityDevice(CrestronHomeEntity, AlarmControlPanelEntity):
    """A read-only Crestron Home security device."""

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="securitydevices")

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return current alarm state."""
        item = self.item
        value = item.get("currentState", item.get("status", item.get("state")))
        if value is None:
            return None
        normalized = str(value).replace(" ", "").replace("_", "").lower()
        return STATE_MAP.get(normalized)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common and security-specific attributes."""
        attributes = super().extra_state_attributes
        item = self.item
        attributes.update(
            {
                "current_state": item.get("currentState"),
                "ready": item.get("ready"),
                "partition": item.get("partition"),
            }
        )
        return attributes
