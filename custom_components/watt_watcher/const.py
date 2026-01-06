"""Config flow for Watt Watcher."""
from __future__ import annotations

import voluptuous as vol
from typing import Any, Dict, List
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_NAME,
    CONF_DEVICE_TYPE,
    CONF_STATES,
    CONF_STATE_NAME,
    CONF_THRESHOLD,
    CONF_COMPARISON,
    CONF_ICON,
    CONF_ACTIVE_DELAY,
    CONF_FINISHED_DELAY,
    CONF_IDLE_DELAY,
    DEFAULT_NAME,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_ACTIVE_DELAY,
    DEFAULT_FINISHED_DELAY,
    DEFAULT_IDLE_DELAY,
    COMPARISON_GREATER,
    COMPARISON_LESS,
)

_LOGGER = logging.getLogger(__name__)


def _get_default_states(device_type: str) -> List[str]:
    """Get default state names based on device type."""
    if device_type == "washing_machine":
        return ["çalışıyor", "yıkıyor", "sıkıyor", "bitti"]
    elif device_type == "dishwasher":
        return ["çalışıyor", "yıkıyor", "kuruluyor", "bitti"]
    elif device_type == "kettle":
        return ["çalışıyor", "kaynıyor", "bitti"]
    elif device_type == "coffee_maker":
        return ["çalışıyor", "ısınıyor", "demliyor", "bitti"]
    else:  # custom
        return ["çalışıyor", "bitti"]


class WattWatcherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watt Watcher."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self.config_data: Dict[str, Any] = {}
        self.state_names: List[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Basic setup."""
        errors = {}

        if user_input is not None:
            self.config_data.update(user_input)
            
            # Generate unique ID
            await self.async_set_unique_id(
                f"{DOMAIN}_{user_input[CONF_POWER_SENSOR]}"
            )
            self._abort_if_unique_id_configured()
            
            # Get default state names
            device_type = user_input[CONF_DEVICE_TYPE]
            self.state_names = _get_default_states(device_type)
            
            return await self.async_step_state_names()

        # Simple form for basic settings
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=False)
            ),
            vol.Required(CONF_DEVICE_TYPE, default=DEFAULT_DEVICE_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "washing_machine", "label": "Çamaşır Makinesi"},
                        {"value": "dishwasher", "label": "Bulaşık Makinesi"},
                        {"value": "kettle", "label": "Su Isıtıcı"},
                        {"value": "coffee_maker", "label": "Kahve Makinesi"},
                        {"value": "custom", "label": "Özel Cihaz"}
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_state_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Enter state names."""
        errors = {}

        if user_input is not None:
            # Get state names from multiple input field
            if "state_names" in user_input:
                state_names = [name.strip() for name in user_input["state_names"] if name.strip()]
                if state_names:
                    self.state_names = state_names
                    return await self.async_step_state_thresholds()
                else:
                    errors["state_names"] = "no_states"

        # Multiple input field for state names
        # Home Assistant versiyonuna göre farklı yöntemler
        try:
            # Yeni versiyon için
            text_config = selector.TextSelectorConfig(multiple=True)
        except:
            # Eski versiyon için
            text_config = selector.TextSelector()
        
        schema = vol.Schema({
            vol.Required(
                "state_names",
                default=self.state_names
            ): selector.TextSelector(text_config),
        })

        return self.async_show_form(
            step_id="state_names",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_type": self.config_data.get(CONF_DEVICE_TYPE, "").replace("_", " ").title()
            },
        )

    async def async_step_state_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Configure thresholds for each state."""
        errors = {}

        if user_input is not None:
            # Collect all states with thresholds
            states = []
            for i, state_name in enumerate(self.state_names):
                threshold_key = f"threshold_{i}"
                comparison_key = f"comparison_{i}"
                icon_key = f"icon_{i}"
                
                if threshold_key in user_input:
                    try:
                        threshold = float(user_input[threshold_key])
                        comparison = user_input.get(comparison_key, COMPARISON_GREATER)
                        icon = user_input.get(icon_key, "mdi:circle")
                        
                        states.append({
                            CONF_STATE_NAME: state_name,
                            CONF_THRESHOLD: threshold,
                            CONF_COMPARISON: comparison,
                            CONF_ICON: icon
                        })
                    except ValueError:
                        errors[threshold_key] = "invalid_number"
            
            if not states:
                errors["base"] = "no_states"
            elif not errors:
                self.config_data[CONF_STATES] = states
                return await self.async_step_timing()

        # Build schema with threshold fields for each state
        schema_dict = {}
        
        for i, state_name in enumerate(self.state_names):
            # State header
            schema_dict[vol.Optional(
                f"header_{i}",
                default=f"📊 {state_name}:"
            )] = str
            
            # Threshold field
            schema_dict[vol.Required(
                f"threshold_{i}",
                default=0.0
            )] = vol.Coerce(float)
            
            # Comparison selector
            schema_dict[vol.Required(
                f"comparison_{i}",
                default=COMPARISON_GREATER
            )] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": COMPARISON_GREATER, "label": "Büyüktür (>)"},
                        {"value": COMPARISON_LESS, "label": "Küçüktür (<)"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            
            # Icon field
            schema_dict[vol.Optional(
                f"icon_{i}",
                default="mdi:circle"
            )] = str
        
        schema = vol.Schema(schema_dict)
        
        return self.async_show_form(
            step_id="state_thresholds",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Configure timing settings."""
        errors = {}

        if user_input is not None:
            # Save all configuration
            self.config_data.update(user_input)
            
            return self.async_create_entry(
                title=self.config_data[CONF_NAME],
                data=self.config_data,
            )

        schema = vol.Schema({
            vol.Required(CONF_ACTIVE_DELAY, default=DEFAULT_ACTIVE_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
            vol.Required(CONF_FINISHED_DELAY, default=DEFAULT_FINISHED_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=60, max=1800)),
            vol.Required(CONF_IDLE_DELAY, default=DEFAULT_IDLE_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=300, max=7200)),
            vol.Optional("scan_interval", default=10): 
                vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
        })

        return self.async_show_form(
            step_id="timing",
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

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.config_data = dict(config_entry.data)
        self.state_names: List[str] = []
        self.states: List[Dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        # Load current states
        self.states = self.config_data.get(CONF_STATES, [])
        self.state_names = [state[CONF_STATE_NAME] for state in self.states]
        
        return await self.async_step_state_names()

    async def async_step_state_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit state names."""
        errors = {}

        if user_input is not None:
            if "state_names" in user_input:
                state_names = [name.strip() for name in user_input["state_names"] if name.strip()]
                if state_names:
                    # Update state names, keep existing thresholds if possible
                    new_states = []
                    for i, state_name in enumerate(state_names):
                        if i < len(self.states):
                            # Keep existing threshold/icon
                            new_states.append({
                                **self.states[i],
                                CONF_STATE_NAME: state_name
                            })
                        else:
                            # New state with defaults
                            new_states.append({
                                CONF_STATE_NAME: state_name,
                                CONF_THRESHOLD: 0.0,
                                CONF_COMPARISON: COMPARISON_GREATER,
                                CONF_ICON: "mdi:circle"
                            })
                    
                    self.states = new_states
                    self.state_names = state_names
                    return await self.async_step_state_thresholds()
                else:
                    errors["state_names"] = "no_states"

        # Try different approaches for TextSelector
        try:
            text_config = selector.TextSelectorConfig(multiple=True)
        except:
            text_config = selector.TextSelector()
        
        schema = vol.Schema({
            vol.Required(
                "state_names",
                default=self.state_names
            ): selector.TextSelector(text_config),
        })

        return self.async_show_form(
            step_id="state_names",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_state_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit state thresholds."""
        errors = {}

        if user_input is not None:
            # Update states with new thresholds
            for i, state_name in enumerate(self.state_names):
                threshold_key = f"threshold_{i}"
                comparison_key = f"comparison_{i}"
                icon_key = f"icon_{i}"
                
                if threshold_key in user_input:
                    try:
                        threshold = float(user_input[threshold_key])
                        comparison = user_input.get(comparison_key, COMPARISON_GREATER)
                        icon = user_input.get(icon_key, "mdi:circle")
                        
                        if i < len(self.states):
                            self.states[i].update({
                                CONF_THRESHOLD: threshold,
                                CONF_COMPARISON: comparison,
                                CONF_ICON: icon
                            })
                        else:
                            self.states.append({
                                CONF_STATE_NAME: state_name,
                                CONF_THRESHOLD: threshold,
                                CONF_COMPARISON: comparison,
                                CONF_ICON: icon
                            })
                    except ValueError:
                        errors[threshold_key] = "invalid_number"
            
            if not errors:
                return await self.async_step_timing()

        # Build schema with current values
        schema_dict = {}
        
        for i, state_name in enumerate(self.state_names):
            # Get current values
            if i < len(self.states):
                state = self.states[i]
                default_threshold = state.get(CONF_THRESHOLD, 0.0)
                default_comparison = state.get(CONF_COMPARISON, COMPARISON_GREATER)
                default_icon = state.get(CONF_ICON, "mdi:circle")
            else:
                default_threshold = 0.0
                default_comparison = COMPARISON_GREATER
                default_icon = "mdi:circle"
            
            # State header
            schema_dict[vol.Optional(
                f"header_{i}",
                default=f"📊 {state_name}:"
            )] = str
            
            # Threshold field
            schema_dict[vol.Required(
                f"threshold_{i}",
                default=default_threshold
            )] = vol.Coerce(float)
            
            # Comparison selector
            schema_dict[vol.Required(
                f"comparison_{i}",
                default=default_comparison
            )] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": COMPARISON_GREATER, "label": "Büyüktür (>)"},
                        {"value": COMPARISON_LESS, "label": "Küçüktür (<)"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            
            # Icon field
            schema_dict[vol.Optional(
                f"icon_{i}",
                default=default_icon
            )] = str
        
        schema = vol.Schema(schema_dict)
        
        return self.async_show_form(
            step_id="state_thresholds",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit timing settings."""
        errors = {}

        if user_input is not None:
            # Update configuration
            new_data = {
                **self.config_entry.data,
                CONF_STATES: self.states,
                CONF_ACTIVE_DELAY: user_input[CONF_ACTIVE_DELAY],
                CONF_FINISHED_DELAY: user_input[CONF_FINISHED_DELAY],
                CONF_IDLE_DELAY: user_input[CONF_IDLE_DELAY],
                "scan_interval": user_input.get("scan_interval", 10),
            }
            
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        data = dict(self.config_entry.data)
        
        schema = vol.Schema({
            vol.Required(CONF_ACTIVE_DELAY, default=data.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY)): 
                vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
            vol.Required(CONF_FINISHED_DELAY, default=data.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY)): 
                vol.All(vol.Coerce(int), vol.Range(min=60, max=1800)),
            vol.Required(CONF_IDLE_DELAY, default=data.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY)): 
                vol.All(vol.Coerce(int), vol.Range(min=300, max=7200)),
            vol.Optional("scan_interval", default=data.get("scan_interval", 10)): 
                vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
        })

        return self.async_show_form(
            step_id="timing",
            data_schema=schema,
            errors=errors,
        )
