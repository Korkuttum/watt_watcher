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
        self.states: List[Dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Basic setup."""
        errors = {}

        if user_input is not None:
            self.config_data.update(user_input)
            
            await self.async_set_unique_id(
                f"{DOMAIN}_{user_input[CONF_POWER_SENSOR]}"
            )
            self._abort_if_unique_id_configured()
            
            device_type = user_input[CONF_DEVICE_TYPE]
            self.state_names = _get_default_states(device_type)
            
            return await self.async_step_state_names()

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
        """Step 2: Enter / edit state names (multiple text field - orijinal güzel ekran)."""
        errors = {}

        if user_input is not None:
            if "state_names" in user_input:
                state_names = [name.strip() for name in user_input["state_names"] if name.strip()]
                if len(state_names) < 2:
                    errors["state_names"] = "en_az_iki_durum_gerekli"
                else:
                    self.state_names = state_names
                    # İlk durum başlangıç, son durum bitiş olacak
                    self.states = []
                    for i, name in enumerate(state_names):
                        comparison = COMPARISON_GREATER if i == 0 else COMPARISON_LESS if i == len(state_names)-1 else COMPARISON_GREATER
                        self.states.append({
                            CONF_STATE_NAME: name,
                            CONF_THRESHOLD: 0.0,
                            CONF_COMPARISON: comparison,
                            CONF_ICON: "mdi:circle"
                        })
                    return await self.async_step_state_thresholds()

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
            description_placeholders={
                "note": "Durum isimlerini virgülle veya her satıra bir tane yazın. İlk durum başlangıç (otomatik >), son durum bitiş (otomatik <) olacak."
            }
        )

    async def async_step_state_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Threshold, comparison (sadece ara durumlar için), icon."""
        errors = {}

        if user_input is not None:
            updated = True
            for i, state in enumerate(self.states):
                th_key = f"threshold_{i}"
                cmp_key = f"comparison_{i}"
                icon_key = f"icon_{i}"

                if th_key in user_input:
                    try:
                        state[CONF_THRESHOLD] = float(user_input[th_key])
                    except ValueError:
                        errors[th_key] = "gecersiz_sayi"

                if icon_key in user_input and user_input[icon_key]:
                    state[CONF_ICON] = user_input[icon_key]

                # Sadece ara durumlar için comparison değiştirilebilir
                if 0 < i < len(self.states) - 1:
                    if cmp_key in user_input:
                        state[CONF_COMPARISON] = user_input[cmp_key]

            # Başlangıç ve bitiş karşılaştırmalarını zorla sabitle
            self.states[0][CONF_COMPARISON] = COMPARISON_GREATER
            self.states[-1][CONF_COMPARISON] = COMPARISON_LESS

            if not errors:
                self.config_data[CONF_STATES] = self.states
                return await self.async_step_timing()

        schema_dict = {}

        for i, state in enumerate(self.states):
            name = state[CONF_STATE_NAME]
            is_start = i == 0
            is_finish = i == len(self.states) - 1

            schema_dict[vol.Optional(
                f"header_{i}",
                default=f"📊 {name} {'(Başlangıç - otomatik >)' if is_start else '(Bitiş - otomatik <)' if is_finish else ''}:"
            )] = str

            schema_dict[vol.Required(
                f"threshold_{i}",
                default=state.get(CONF_THRESHOLD, 0.0)
            )] = vol.Coerce(float)

            if not is_start and not is_finish:
                schema_dict[vol.Required(
                    f"comparison_{i}",
                    default=state.get(CONF_COMPARISON, COMPARISON_GREATER)
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": COMPARISON_GREATER, "label": "Büyüktür (>)"},
                            {"value": COMPARISON_LESS, "label": "Küçüktür (<)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                )

            schema_dict[vol.Optional(
                f"icon_{i}",
                default=state.get(CONF_ICON, "mdi:circle")
            )] = str

        return self.async_show_form(
            step_id="state_thresholds",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Timing settings."""
        errors = {}

        if user_input is not None:
            self.config_data.update({
                CONF_ACTIVE_DELAY: user_input[CONF_ACTIVE_DELAY],
                CONF_FINISHED_DELAY: user_input[CONF_FINISHED_DELAY],
                CONF_IDLE_DELAY: user_input[CONF_IDLE_DELAY],
                "scan_interval": user_input.get("scan_interval", 10),
            })
            return self.async_create_entry(
                title=self.config_data.get(CONF_NAME, DEFAULT_NAME),
                data=self.config_data
            )

        schema = vol.Schema({
            vol.Required(CONF_ACTIVE_DELAY, default=DEFAULT_ACTIVE_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
            vol.Required(CONF_FINISHED_DELAY, default=DEFAULT_FINISHED_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=60, max=1800)),
            vol.Required(CONF_IDLE_DELAY, default=DEFAULT_IDLE_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
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
        """Options flow for editing."""
        return WattWatcherOptionsFlowHandler(config_entry)


class WattWatcherOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self.state_names = []
        self.states = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        states = self.config_entry.data.get(CONF_STATES, [])
        self.states = states.copy()
        self.state_names = [s[CONF_STATE_NAME] for s in states]
        return await self.async_step_state_names()

    async def async_step_state_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            if "state_names" in user_input:
                state_names = [n.strip() for n in user_input["state_names"] if n.strip()]
                if len(state_names) < 2:
                    errors["state_names"] = "en_az_iki_durum_gerekli"
                else:
                    self.state_names = state_names
                    new_states = []
                    for i, name in enumerate(state_names):
                        # Mevcut threshold/icon varsa koru
                        if i < len(self.states):
                            new_states.append({
                                **self.states[i],
                                CONF_STATE_NAME: name
                            })
                        else:
                            comparison = COMPARISON_GREATER if i == 0 else COMPARISON_LESS if i == len(state_names)-1 else COMPARISON_GREATER
                            new_states.append({
                                CONF_STATE_NAME: name,
                                CONF_THRESHOLD: 0.0,
                                CONF_COMPARISON: comparison,
                                CONF_ICON: "mdi:circle"
                            })
                    self.states = new_states
                    return await self.async_step_state_thresholds()

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
        errors = {}

        if user_input is not None:
            for i, state in enumerate(self.states):
                th_key = f"threshold_{i}"
                icon_key = f"icon_{i}"
                cmp_key = f"comparison_{i}"

                if th_key in user_input:
                    try:
                        state[CONF_THRESHOLD] = float(user_input[th_key])
                    except ValueError:
                        errors[th_key] = "gecersiz_sayi"

                if icon_key in user_input:
                    state[CONF_ICON] = user_input[icon_key]

                if 0 < i < len(self.states) - 1 and cmp_key in user_input:
                    state[CONF_COMPARISON] = user_input[cmp_key]

            # Sabitle
            self.states[0][CONF_COMPARISON] = COMPARISON_GREATER
            self.states[-1][CONF_COMPARISON] = COMPARISON_LESS

            if not errors:
                new_data = {
                    **self.config_entry.data,
                    CONF_STATES: self.states,
                }
                self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                return await self.async_step_timing()

        schema_dict = {}

        for i, state in enumerate(self.states):
            name = state[CONF_STATE_NAME]
            is_start = i == 0
            is_finish = i == len(self.states) - 1
            cmp_label = " (otomatik >)" if is_start else " (otomatik <)" if is_finish else ""

            schema_dict[vol.Optional(
                f"header_{i}",
                default=f"📊 {name}{cmp_label}:"
            )] = str

            schema_dict[vol.Required(
                f"threshold_{i}",
                default=state.get(CONF_THRESHOLD, 0.0)
            )] = vol.Coerce(float)

            if not is_start and not is_finish:
                schema_dict[vol.Required(
                    f"comparison_{i}",
                    default=state.get(CONF_COMPARISON, COMPARISON_GREATER)
                )] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": COMPARISON_GREATER, "label": "Büyüktür (>)"},
                            {"value": COMPARISON_LESS, "label": "Küçüktür (<)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                )

            schema_dict[vol.Optional(
                f"icon_{i}",
                default=state.get(CONF_ICON, "mdi:circle")
            )] = str

        return self.async_show_form(
            step_id="state_thresholds",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            new_data = {
                **self.config_entry.data,
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
                vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
            vol.Optional("scan_interval", default=data.get("scan_interval", 10)): 
                vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
        })

        return self.async_show_form(
            step_id="timing",
            data_schema=schema,
            errors=errors,
        )
