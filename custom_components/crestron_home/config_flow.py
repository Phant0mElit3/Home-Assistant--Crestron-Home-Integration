"""Config flow for Crestron Home."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL, CONF_TOKEN
from homeassistant.core import callback

from .const import CONF_USE_SSL, CONF_VERIFY_SSL, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL, DOMAIN


class CrestronHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Crestron Home config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_TOKEN): str,
                    vol.Optional(CONF_USE_SSL, default=True): bool,
                    vol.Optional(CONF_VERIFY_SSL, default=False): bool,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ): int,
                }
            ),
        )

    async def async_step_import(
        self,
        user_input: dict[str, Any],
    ) -> config_entries.FlowResult:
        """Import YAML configuration."""
        data = dict(user_input)
        scan_interval = data.get(CONF_SCAN_INTERVAL)
        if hasattr(scan_interval, "total_seconds"):
            data[CONF_SCAN_INTERVAL] = int(scan_interval.total_seconds())
        await self.async_set_unique_id(data[CONF_HOST])
        self._abort_if_unique_id_configured(updates=data)
        return self.async_create_entry(title=DEFAULT_NAME, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return CrestronHomeOptionsFlow(config_entry)


class CrestronHomeOptionsFlow(config_entries.OptionsFlow):
    """Handle Crestron Home options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options or self.config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current.get(
                            CONF_SCAN_INTERVAL,
                            int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                        ),
                    ): int,
                }
            ),
        )
