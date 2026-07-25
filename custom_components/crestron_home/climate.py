"""Crestron Home climate entities."""

from __future__ import annotations

import re
from time import monotonic
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CrestronHomeApiError
from .const import DOMAIN
from .coordinator import CrestronHomeCoordinator
from .entity import CrestronHomeEntity

ATTR_TEMPERATURE = "temperature"
ATTR_TARGET_TEMP_HIGH = "target_temp_high"
ATTR_TARGET_TEMP_LOW = "target_temp_low"

MODE_MAP = {
    "0": HVACMode.OFF,
    "off": HVACMode.OFF,
    "auto": HVACMode.HEAT_COOL,
    "dualauto": HVACMode.HEAT_COOL,
    "heatcool": HVACMode.HEAT_COOL,
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "auxheat": HVACMode.HEAT,
}
REVERSE_MODE_MAP = {
    HVACMode.OFF: "Off",
    HVACMode.HEAT_COOL: "Auto",
    HVACMode.COOL: "Cool",
    HVACMode.HEAT: "Heat",
}
SETPOINT_TYPE_MAP = {
    "auto": "Auto",
    "cool": "Cool",
    "heat": "Heat",
    "auxheat": "Heat",
}
SETPOINT_TYPE_BY_MODE = {
    HVACMode.COOL: "Cool",
    HVACMode.HEAT: "Heat",
    HVACMode.HEAT_COOL: "Auto",
}
PRESET_RUN = "run"
PRESET_HOLD = "hold"
OPTIMISTIC_THERMOSTAT_TIMEOUT = 45
DOCUMENTED_FAN_MODES = ("Auto", "On")
DOCUMENTED_PRESET_MODES = (PRESET_RUN, PRESET_HOLD)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home thermostats."""
    coordinator: CrestronHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CrestronHomeThermostat(coordinator, item)
        for item in coordinator.data.get("thermostats", [])
        if item.get("id") is not None
    )


class CrestronHomeThermostat(CrestronHomeEntity, ClimateEntity):
    """A Crestron Home thermostat."""

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1.0

    def __init__(self, coordinator: CrestronHomeCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, item, key="thermostats")
        self._optimistic_values: dict[str, Any] = {}
        self._optimistic_expires_at: float | None = None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported thermostat features."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._has_heat_cool_range:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self.preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        return features

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        return self._convert_temperature(
            self.item.get("currentTemperature", self.item.get("temperature"))
        )

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        if (temperature := self._optimistic_temperature_for_mode(self.hvac_mode)) is not None:
            return temperature
        setpoints = self._current_setpoints
        if not setpoints:
            return None
        active_type = self._setpoint_type_for_mode(self.hvac_mode)
        for setpoint in setpoints:
            if _normalize_setpoint_type(setpoint.get("type")) == active_type:
                return self._convert_temperature(setpoint.get("temperature"))
        return self._convert_temperature(setpoints[0].get("temperature"))

    @property
    def target_temperature_high(self) -> float | None:
        """Return cooling setpoint for heat/cool mode."""
        if (temperature := self._optimistic_temperature_for_type("Cool")) is not None:
            return temperature
        return self._temperature_for_setpoint_type("Cool")

    @property
    def target_temperature_low(self) -> float | None:
        """Return heating setpoint for heat/cool mode."""
        if (temperature := self._optimistic_temperature_for_type("Heat")) is not None:
            return temperature
        return self._temperature_for_setpoint_type("Heat")

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        if not self._optimistic_expired and "hvac_mode" in self._optimistic_values:
            return self._optimistic_values["hvac_mode"]
        return self._polled_hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return available HVAC modes."""
        modes: list[HVACMode] = []
        for mode in self.item.get("availableSystemModes") or []:
            mapped_mode = self._parse_hvac_mode(mode)
            if mapped_mode is not None and mapped_mode not in modes:
                modes.append(mapped_mode)
        current_mode = self._polled_hvac_mode
        if current_mode is not None and current_mode not in modes:
            modes.append(current_mode)
        return modes or [HVACMode.OFF]

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode."""
        if not self._optimistic_expired and "fan_mode" in self._optimistic_values:
            return self._optimistic_values["fan_mode"]
        return self._polled_fan_mode

    @property
    def _polled_fan_mode(self) -> str | None:
        """Return the fan mode from the latest Crestron poll."""
        mode = self.item.get("currentFanMode", self.item.get("fanMode"))
        return self._option_display_value(mode, self.item.get("availableFanModes") or [])

    @property
    def fan_modes(self) -> list[str]:
        """Return documented fan modes plus the active value if different."""
        modes = [
            mode
            for mode in DOCUMENTED_FAN_MODES
            if self._has_available_option(mode, self.item.get("availableFanModes") or [])
        ]
        fan_mode = self._polled_fan_mode
        if fan_mode is not None and fan_mode not in modes:
            modes.append(fan_mode)
        return modes

    @property
    def preset_mode(self) -> str | None:
        """Return thermostat schedule preset."""
        if not self._optimistic_expired and "preset_mode" in self._optimistic_values:
            return self._optimistic_values["preset_mode"]
        return self._polled_preset_mode

    @property
    def _polled_preset_mode(self) -> str | None:
        """Return the schedule state from the latest Crestron poll."""
        state = self.item.get("currentSchedulerState", self.item.get("schedulerState"))
        return self._option_display_value(
            state,
            self.item.get("availableSchedulerStates") or [PRESET_RUN, PRESET_HOLD],
        )

    @property
    def preset_modes(self) -> list[str]:
        """Return documented schedule modes plus the active value if different."""
        modes = list(DOCUMENTED_PRESET_MODES)
        preset_mode = self._polled_preset_mode
        if preset_mode is not None and preset_mode not in modes:
            modes.append(preset_mode)
        return modes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return thermostat diagnostic attributes."""
        attributes = super().extra_state_attributes
        attributes.update(
            {
                "crestron_hvac_mode": self.item.get("currentMode", self.item.get("mode")),
                "crestron_fan_mode": self.item.get("currentFanMode", self.item.get("fanMode")),
                "crestron_schedule_state": self.item.get(
                    "currentSchedulerState",
                    self.item.get("schedulerState"),
                ),
                "crestron_temperature_units": self.item.get("temperatureUnits"),
                "crestron_setpoints": self._current_setpoints,
                "available_system_modes": self.item.get("availableSystemModes"),
                "available_fan_modes": self.item.get("availableFanModes"),
                "available_scheduler_states": self.item.get("availableSchedulerStates"),
                "optimistic_thermostat": dict(self._optimistic_values),
                "thermostat_payload_keys": sorted(str(key) for key in self.item),
            }
        )
        return attributes

    @property
    def temperature_unit(self) -> str:
        """Return thermostat temperature unit."""
        units = str(self.item.get("temperatureUnits", "")).lower()
        if "celsius" in units:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def target_temperature_step(self) -> float:
        """Return target temperature step."""
        units = str(self.item.get("temperatureUnits", "")).lower()
        return 0.5 if "half" in units else 1.0

    @property
    def min_temp(self) -> float:
        """Return minimum setpoint."""
        values = [
            item.get("minValue")
            for item in self.item.get("availableSetPoints") or []
            if isinstance(item, dict) and item.get("minValue") is not None
        ]
        return self._convert_temperature(min(values)) if values else 40.0

    @property
    def max_temp(self) -> float:
        """Return maximum setpoint."""
        values = [
            item.get("maxValue")
            for item in self.item.get("availableSetPoints") or []
            if isinstance(item, dict) and item.get("maxValue") is not None
        ]
        return self._convert_temperature(max(values)) if values else 90.0

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if hvac_mode := kwargs.get("hvac_mode"):
            await self.async_set_hvac_mode(hvac_mode)

        setpoints: list[dict[str, Any]] = []
        if ATTR_TARGET_TEMP_LOW in kwargs or ATTR_TARGET_TEMP_HIGH in kwargs:
            if ATTR_TARGET_TEMP_LOW in kwargs:
                setpoints.append(self._setpoint_payload("Heat", kwargs[ATTR_TARGET_TEMP_LOW]))
            if ATTR_TARGET_TEMP_HIGH in kwargs:
                setpoints.append(self._setpoint_payload("Cool", kwargs[ATTR_TARGET_TEMP_HIGH]))
        elif ATTR_TEMPERATURE in kwargs:
            mode = kwargs.get("hvac_mode") or self.hvac_mode
            setpoint_type = self._setpoint_type_for_mode(mode)
            setpoints.append(self._setpoint_payload(setpoint_type, kwargs[ATTR_TEMPERATURE]))

        if not setpoints:
            return

        try:
            await self.coordinator.api.async_set_thermostat_setpoints(self._id, setpoints)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home thermostat command failed: {err}") from err
        self._set_optimistic_setpoints(setpoints)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        hvac_mode = self._normalize_hvac_mode(hvac_mode)
        mode = REVERSE_MODE_MAP.get(hvac_mode)
        if mode is None:
            raise HomeAssistantError(f"Unsupported Crestron Home HVAC mode: {hvac_mode}")
        try:
            await self.coordinator.api.async_set_thermostat_mode(self._id, mode)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home thermostat mode failed: {err}") from err
        self._set_optimistic_value("hvac_mode", hvac_mode)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on the thermostat using the first available non-off mode."""
        for mode in (HVACMode.HEAT_COOL, HVACMode.COOL, HVACMode.HEAT):
            if mode in self.hvac_modes:
                await self.async_set_hvac_mode(mode)
                return
        raise HomeAssistantError("No non-off Crestron Home HVAC mode is available")

    async def async_turn_off(self) -> None:
        """Turn off the thermostat."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        crestron_fan_mode = self._crestron_option_value(
            fan_mode,
            list(DOCUMENTED_FAN_MODES),
        )
        try:
            await self.coordinator.api.async_set_thermostat_fan_mode(self._id, crestron_fan_mode)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home thermostat fan mode failed: {err}") from err
        self._set_optimistic_value(
            "fan_mode",
            self._option_display_value(crestron_fan_mode, self.fan_modes),
        )
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set schedule preset."""
        crestron_preset_mode = self._crestron_option_value(
            preset_mode,
            list(DOCUMENTED_PRESET_MODES),
        )
        try:
            await self.coordinator.api.async_set_thermostat_schedule(self._id, crestron_preset_mode)
        except CrestronHomeApiError as err:
            raise HomeAssistantError(f"Crestron Home thermostat preset failed: {err}") from err
        self._set_optimistic_value(
            "preset_mode",
            self._option_display_value(crestron_preset_mode, self.preset_modes),
        )
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def _current_setpoints(self) -> list[dict[str, Any]]:
        setpoints = self.item.get("currentSetPoint", self.item.get("setPoint")) or []
        if isinstance(setpoints, dict):
            return [setpoints]
        if isinstance(setpoints, list):
            return [setpoint for setpoint in setpoints if isinstance(setpoint, dict)]
        return []

    @property
    def _has_heat_cool_range(self) -> bool:
        types = {_normalize_setpoint_type(setpoint.get("type")) for setpoint in self._current_setpoints}
        return {"Heat", "Cool"}.issubset(types)

    def _temperature_for_setpoint_type(self, setpoint_type: str) -> float | None:
        for setpoint in self._current_setpoints:
            if _normalize_setpoint_type(setpoint.get("type")) == setpoint_type:
                return self._convert_temperature(setpoint.get("temperature"))
        return None

    def _setpoint_type_for_mode(self, mode: HVACMode | str | None) -> str:
        mode = self._normalize_hvac_mode(mode)
        return SETPOINT_TYPE_BY_MODE.get(mode, "Auto")

    def _normalize_hvac_mode(self, mode: HVACMode | str | None) -> HVACMode | None:
        if isinstance(mode, HVACMode) or mode is None:
            return mode
        return self._parse_hvac_mode(mode)

    @property
    def _polled_hvac_mode(self) -> HVACMode | None:
        """Return the HVAC mode from the latest Crestron poll."""
        return self._parse_hvac_mode(self.item.get("currentMode", self.item.get("mode")))

    @staticmethod
    def _parse_hvac_mode(mode: Any) -> HVACMode | None:
        return MODE_MAP.get(_normalize_key(mode))

    def _setpoint_payload(self, setpoint_type: str, temperature: float) -> dict[str, Any]:
        return {
            "type": setpoint_type,
            "temperature": round(float(temperature) * 10),
        }

    @staticmethod
    def _convert_temperature(value: Any) -> float | None:
        if value is None:
            return None
        return float(value) / 10

    def _optimistic_temperature_for_mode(self, mode: HVACMode | None) -> float | None:
        """Return optimistic target temperature for an HVAC mode."""
        return self._optimistic_temperature_for_type(self._setpoint_type_for_mode(mode))

    def _optimistic_temperature_for_type(self, setpoint_type: str) -> float | None:
        """Return optimistic target temperature for a Crestron setpoint type."""
        if self._optimistic_expired:
            return None
        setpoints = self._optimistic_values.get("setpoints")
        if not isinstance(setpoints, dict):
            return None
        value = setpoints.get(setpoint_type)
        return float(value) if value is not None else None

    @property
    def _optimistic_expired(self) -> bool:
        """Return whether optimistic thermostat state is stale."""
        if self._optimistic_expires_at is None:
            return False
        if monotonic() < self._optimistic_expires_at:
            return False
        self._clear_optimistic_values()
        return True

    def _set_optimistic_value(self, key: str, value: Any) -> None:
        """Set a short-lived optimistic thermostat value."""
        self._optimistic_values[key] = value
        self._optimistic_expires_at = monotonic() + OPTIMISTIC_THERMOSTAT_TIMEOUT

    def _set_optimistic_setpoints(self, setpoints: list[dict[str, Any]]) -> None:
        """Set short-lived optimistic thermostat setpoints."""
        optimistic_setpoints = dict(self._optimistic_values.get("setpoints") or {})
        for setpoint in setpoints:
            setpoint_type = _normalize_setpoint_type(setpoint.get("type"))
            temperature = self._convert_temperature(setpoint.get("temperature"))
            if setpoint_type and temperature is not None:
                optimistic_setpoints[setpoint_type] = temperature
        self._set_optimistic_value("setpoints", optimistic_setpoints)

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state once Crestron confirms it or it expires."""
        if self._optimistic_expired:
            super()._handle_coordinator_update()
            return
        self._clear_confirmed_optimistic_values()
        super()._handle_coordinator_update()

    def _clear_confirmed_optimistic_values(self) -> None:
        """Remove optimistic values that match the latest polled state."""
        if self._optimistic_values.get("hvac_mode") == self._polled_hvac_mode:
            self._optimistic_values.pop("hvac_mode", None)
        if (
            "fan_mode" in self._optimistic_values
            and self._polled_fan_mode is not None
        ):
            self._optimistic_values.pop("fan_mode", None)
        if self._optimistic_values.get("preset_mode") == self._polled_preset_mode:
            self._optimistic_values.pop("preset_mode", None)

        setpoints = dict(self._optimistic_values.get("setpoints") or {})
        for setpoint_type, temperature in list(setpoints.items()):
            if self._temperature_for_setpoint_type(setpoint_type) == temperature:
                setpoints.pop(setpoint_type)
        if setpoints:
            self._optimistic_values["setpoints"] = setpoints
        else:
            self._optimistic_values.pop("setpoints", None)

        if not self._optimistic_values:
            self._optimistic_expires_at = None

    def _clear_optimistic_values(self) -> None:
        """Clear all optimistic thermostat state."""
        self._optimistic_values.clear()
        self._optimistic_expires_at = None

    @staticmethod
    def _has_available_option(option: str, available_options: list[Any]) -> bool:
        """Return whether an option is advertised by Crestron."""
        option_key = _normalize_key(option)
        return any(_normalize_key(candidate) == option_key for candidate in available_options)

    @staticmethod
    def _crestron_option_value(option: str, available_options: list[Any]) -> str:
        """Return the exact option string advertised by Crestron when possible."""
        option_key = _normalize_key(option)
        for candidate in available_options:
            if _normalize_key(candidate) == option_key:
                return str(candidate)
        return str(option)

    @staticmethod
    def _option_display_value(value: Any, available_options: list[Any]) -> str | None:
        """Return the HA option label matching a Crestron value."""
        if value is None:
            return None
        value_key = _normalize_key(value)
        for option in available_options:
            if _normalize_key(option) == value_key:
                return str(option)
        return str(value)


def _normalize_setpoint_type(value: Any) -> str | None:
    """Normalize a Crestron setpoint type to the documented title-case value."""
    return SETPOINT_TYPE_MAP.get(_normalize_key(value))


def _normalize_key(value: Any) -> str:
    """Return a lowercase alphanumeric key for loose Crestron string matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower()) if value is not None else ""
