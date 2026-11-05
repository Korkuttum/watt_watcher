"""Config flow for Watt Watcher."""
from __future__ import annotations

import copy

import voluptuous as vol
from typing import Any, Dict, List
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
    CONF_RESUME_WINDOW,
    DEFAULT_RESUME_WINDOW,
    DEVICE_TYPE_TIMINGS,
    DEFAULT_NAME,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_ACTIVE_DELAY,
    DEFAULT_FINISHED_DELAY,
    DEFAULT_IDLE_DELAY,
    COMPARISON_GREATER,
    COMPARISON_LESS,
)

_LOGGER = logging.getLogger(__name__)


_DEFAULT_STATES = {
    "tr": {
        "washing_machine": ["çalışıyor", "yıkıyor", "sıkıyor", "bitti"],
        "dishwasher": ["çalışıyor", "yıkıyor", "kuruluyor", "bitti"],
        "kettle": ["çalışıyor", "kaynıyor", "bitti"],
        "coffee_maker": ["çalışıyor", "ısınıyor", "demliyor", "bitti"],
        "custom": ["çalışıyor", "bitti"],
    },
    "en": {
        "washing_machine": ["running", "washing", "spinning", "finished"],
        "dishwasher": ["running", "washing", "drying", "finished"],
        "kettle": ["running", "boiling", "finished"],
        "coffee_maker": ["running", "heating", "brewing", "finished"],
        "custom": ["running", "finished"],
    },
}


def _lang(hass) -> str:
    """Language used for generated text: Turkish if HA is Turkish, else English."""
    return "tr" if (hass.config.language or "").lower().startswith("tr") else "en"


def _get_default_states(device_type: str, language: str = "en") -> List[str]:
    """Default state names for a device type; the last one is the "finished" state."""
    table = _DEFAULT_STATES.get(language, _DEFAULT_STATES["en"])
    return list(table.get(device_type, table["custom"]))


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
            self.state_names = _get_default_states(device_type, _lang(self.hass))
            
            return await self.async_step_state_names()

        schema = vol.Schema({
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=False)
            ),
            vol.Required(CONF_DEVICE_TYPE, default=DEFAULT_DEVICE_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["washing_machine", "dishwasher", "kettle", "coffee_maker", "custom"],
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
        )

    async def async_step_state_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Threshold, comparison (sadece ara durumlar için), icon."""
        errors = {}

        if user_input is not None:
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

        return self.async_show_form(
            step_id="state_thresholds",
            data_schema=_threshold_schema(self.states, _lang(self.hass)),
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
                CONF_RESUME_WINDOW: user_input[CONF_RESUME_WINDOW],
                "scan_interval": user_input.get("scan_interval", 10),
            })
            return self.async_create_entry(
                title=self.config_data.get(CONF_NAME, DEFAULT_NAME),
                data=self.config_data
            )

        suggested = DEVICE_TYPE_TIMINGS.get(
            self.config_data.get(CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE), {}
        )
        schema = vol.Schema({
            vol.Required(CONF_ACTIVE_DELAY, default=DEFAULT_ACTIVE_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
            vol.Required(
                CONF_FINISHED_DELAY,
                default=suggested.get("finished_delay", DEFAULT_FINISHED_DELAY),
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=1800)),
            vol.Required(CONF_IDLE_DELAY, default=DEFAULT_IDLE_DELAY): 
                vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
            vol.Required(CONF_RESUME_WINDOW, default=DEFAULT_RESUME_WINDOW): 
                vol.All(vol.Coerce(int), vol.Range(min=0, max=7200)),
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
        return WattWatcherOptionsFlowHandler()


def _threshold_schema(states: List[Dict[str, Any]], language: str = "en") -> vol.Schema:
    """Build the per-state threshold form (shared by setup and options)."""
    schema_dict: Dict[Any, Any] = {}
    for i, state in enumerate(states):
        name = state[CONF_STATE_NAME]
        is_start = i == 0
        is_finish = i == len(states) - 1
        if language == "tr":
            label = " (başlangıç, otomatik >)" if is_start else " (bitiş, otomatik <)" if is_finish else ""
        else:
            label = " (start, automatically >)" if is_start else " (finish, automatically <)" if is_finish else ""

        schema_dict[vol.Optional(f"header_{i}", default=f"📊 {name}{label}:")] = str
        schema_dict[vol.Required(
            f"threshold_{i}", default=state.get(CONF_THRESHOLD, 0.0)
        )] = vol.Coerce(float)

        if not is_start and not is_finish:
            schema_dict[vol.Required(
                f"comparison_{i}", default=state.get(CONF_COMPARISON, COMPARISON_GREATER)
            )] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[COMPARISON_GREATER, COMPARISON_LESS],
                    translation_key="comparison",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema_dict[vol.Optional(
            f"icon_{i}", default=state.get(CONF_ICON, "mdi:circle")
        )] = str
    return vol.Schema(schema_dict)


class WattWatcherOptionsFlowHandler(config_entries.OptionsFlow):
    """Edit states, thresholds and timings.

    ``self.config_entry`` is provided by Home Assistant (it is read-only, so it
    must not be assigned in ``__init__``).  Everything is collected first and
    saved once, as entry *options*, which the coordinator merges over the
    original entry data.
    """

    def __init__(self) -> None:
        self.state_names: List[str] = []
        self.states: List[Dict[str, Any]] = []

    def _current(self) -> Dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Menu: edit timings directly, or edit the states and thresholds."""
        self.states = copy.deepcopy(self._current().get(CONF_STATES, []))
        self.state_names = [s[CONF_STATE_NAME] for s in self.states]
        return self.async_show_menu(step_id="init", menu_options=["timing", "state_names"])

    async def async_step_state_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            state_names = [n.strip() for n in user_input.get("state_names", []) if n.strip()]
            if len(state_names) < 2:
                errors["state_names"] = "en_az_iki_durum_gerekli"
            else:
                self.state_names = state_names
                new_states = []
                for i, name in enumerate(state_names):
                    if i < len(self.states):
                        new_states.append({**self.states[i], CONF_STATE_NAME: name})
                    else:
                        new_states.append({
                            CONF_STATE_NAME: name,
                            CONF_THRESHOLD: 0.0,
                            CONF_COMPARISON: COMPARISON_GREATER,
                            CONF_ICON: "mdi:circle",
                        })
                self.states = new_states
                return await self.async_step_state_thresholds()

        schema = vol.Schema({
            vol.Required("state_names", default=self.state_names): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True)
            ),
        })
        return self.async_show_form(step_id="state_names", data_schema=schema, errors=errors)

    async def async_step_state_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            for i, state in enumerate(self.states):
                if f"threshold_{i}" in user_input:
                    state[CONF_THRESHOLD] = float(user_input[f"threshold_{i}"])
                if user_input.get(f"icon_{i}"):
                    state[CONF_ICON] = user_input[f"icon_{i}"]
                if 0 < i < len(self.states) - 1 and f"comparison_{i}" in user_input:
                    state[CONF_COMPARISON] = user_input[f"comparison_{i}"]

            # First state is always "> start", last is always "< finish"
            self.states[0][CONF_COMPARISON] = COMPARISON_GREATER
            self.states[-1][CONF_COMPARISON] = COMPARISON_LESS
            return await self.async_step_timing()

        return self.async_show_form(
            step_id="state_thresholds", data_schema=_threshold_schema(self.states, _lang(self.hass)),
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            options = {
                CONF_STATES: self.states,
                CONF_ACTIVE_DELAY: user_input[CONF_ACTIVE_DELAY],
                CONF_FINISHED_DELAY: user_input[CONF_FINISHED_DELAY],
                CONF_IDLE_DELAY: user_input[CONF_IDLE_DELAY],
                CONF_RESUME_WINDOW: user_input[CONF_RESUME_WINDOW],
                "scan_interval": user_input.get("scan_interval", 10),
            }
            # Saving options triggers the entry's update listener, which reloads it.
            return self.async_create_entry(title="", data=options)

        data = self._current()
        schema = vol.Schema({
            vol.Required(CONF_ACTIVE_DELAY, default=data.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY)):
                vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
            vol.Required(CONF_FINISHED_DELAY, default=data.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY)):
                vol.All(vol.Coerce(int), vol.Range(min=30, max=1800)),
            vol.Required(CONF_IDLE_DELAY, default=data.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY)):
                vol.All(vol.Coerce(int), vol.Range(min=60, max=7200)),
            vol.Required(CONF_RESUME_WINDOW, default=data.get(CONF_RESUME_WINDOW, DEFAULT_RESUME_WINDOW)):
                vol.All(vol.Coerce(int), vol.Range(min=0, max=7200)),
            vol.Optional("scan_interval", default=data.get("scan_interval", 10)):
                vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
        })
        return self.async_show_form(step_id="timing", data_schema=schema)
