"""Config flow for Watt Watcher."""
from __future__ import annotations

import voluptuous as vol
from typing import Any, Dict

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get,
)

from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_NAME,
    CONF_DEVICE_TYPE,
    DEVICE_PROFILES,
    DEFAULT_NAME,
    DEFAULT_DEVICE_TYPE,
)


class WattWatcherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watt Watcher."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Generate unique ID for the entry
            await self.async_set_unique_id(
                f"{DOMAIN}_{user_input[CONF_POWER_SENSOR]}"
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        # Get all sensor entities
        entity_registry = async_get(self.hass)
        sensor_entities = [
            entity.entity_id
            for entity in entity_registry.entities.values()
            if entity.domain == "sensor"
            and ("power" in entity.entity_id.lower() 
                 or "watt" in entity.entity_id.lower())
        ]

        schema = vol.Schema({
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=False)
            ),
            vol.Required(CONF_DEVICE_TYPE, default=DEFAULT_DEVICE_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(DEVICE_PROFILES.keys()),
                    translation_key="device_type",
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WattWatcherOptionsFlow(config_entry)


class WattWatcherOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Watt Watcher."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_basic()

    async def async_step_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage basic options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current configuration
        config = dict(self.config_entry.data)

        schema = vol.Schema({
            vol.Optional(
                "scan_interval",
                default=self.config_entry.options.get("scan_interval", 10)
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
        })

        return self.async_show_form(
            step_id="basic",
            data_schema=schema,
        )
