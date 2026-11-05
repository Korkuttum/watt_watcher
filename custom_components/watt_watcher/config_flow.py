"""Config flow and options flow for Watt Watcher.

Both flows share the same wizard (``_WizardMixin``)::

    setup:    user  ->  state_names  ->  state (once per state)  ->  timing
    options:  menu  ->  timing                                      (quick edit)
                    ->  state_names -> state (per state) -> timing  (full edit)
"""
from __future__ import annotations

import copy
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    COMPARISON_GREATER,
    COMPARISON_LESS,
    CONF_ACTIVE_DELAY,
    CONF_COMPARISON,
    CONF_DEVICE_TYPE,
    CONF_FINISHED_DELAY,
    CONF_ICON,
    CONF_IDLE_DELAY,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_RESUME_WINDOW,
    CONF_SCAN_INTERVAL,
    CONF_STATE_NAME,
    CONF_STATES,
    CONF_THRESHOLD,
    DEFAULT_ACTIVE_DELAY,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_FINISHED_DELAY,
    DEFAULT_IDLE_DELAY,
    DEFAULT_NAME,
    DEFAULT_RESUME_WINDOW,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE_TIMINGS,
    DOMAIN,
    STATE_IDLE,
)

_LOGGER = logging.getLogger(__name__)

ADVANCED = "advanced"
DEVICE_TYPES = ["washing_machine", "dishwasher", "kettle", "coffee_maker", "custom"]

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

# Text injected into the "state" step description (Turkish / English only;
# every other language falls back to English).
_ROLE_TEXT = {
    "tr": {
        "start": "Başlangıç durumu: güç bu değerin ÜSTÜNDE kalınca döngü başlar.",
        "finish": "Bitiş durumu: güç bu değerin ALTINDA kalınca döngü biter.",
        "middle": "Ara durum: aşağıda seçtiğin karşılaştırmaya göre belirlenir.",
    },
    "en": {
        "start": "Start state: the cycle starts when power stays ABOVE this value.",
        "finish": "Finish state: the cycle ends when power stays BELOW this value.",
        "middle": "Intermediate state: matched using the comparison you pick below.",
    },
}

_ROLE_ICON = {"start": "mdi:play-circle", "finish": "mdi:check-circle", "middle": "mdi:progress-clock"}


def _lang(hass) -> str:
    """Turkish if Home Assistant is set to Turkish, English otherwise."""
    return "tr" if (hass.config.language or "").lower().startswith("tr") else "en"


def _default_state_names(device_type: str, language: str) -> list[str]:
    table = _DEFAULT_STATES.get(language, _DEFAULT_STATES["en"])
    return list(table.get(device_type, table["custom"]))


def _new_state(name: str, index: int, total: int) -> dict[str, Any]:
    """Sensible starting values for a state the user has not configured yet."""
    if index == 0:
        role, threshold, comparison = "start", 5.0, COMPARISON_GREATER
    elif index == total - 1:
        role, threshold, comparison = "finish", 5.0, COMPARISON_LESS
    else:
        role, threshold, comparison = "middle", 100.0 * index, COMPARISON_GREATER
    return {
        CONF_STATE_NAME: name,
        CONF_THRESHOLD: threshold,
        CONF_COMPARISON: comparison,
        CONF_ICON: _ROLE_ICON[role],
    }


def _seconds(minimum: int, maximum: int, step: int = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step,
            unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX,
        )
    )


class _WizardMixin:
    """State names, per-state thresholds and timings (shared by both flows)."""

    _state_names: list[str]
    _states: list[dict[str, Any]]
    _index: int

    # -- provided by the concrete flow ---------------------------------- #
    def _timing_defaults(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def _save(self, data: dict[str, Any]) -> config_entries.ConfigFlowResult:  # pragma: no cover
        raise NotImplementedError

    # -- step: state names ---------------------------------------------- #
    async def async_step_state_names(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            names = [n.strip() for n in user_input["state_names"] if n.strip()]
            lowered = [n.lower() for n in names]
            if len(names) < 2:
                errors["state_names"] = "min_two_states"
            elif len(set(lowered)) != len(lowered):
                errors["state_names"] = "duplicate_states"
            elif STATE_IDLE in lowered:
                errors["state_names"] = "reserved_name"
            else:
                self._state_names = names
                # Keep what the user already configured for states that stay.
                old_states = self._states
                by_name = {s[CONF_STATE_NAME]: s for s in old_states}
                merged = []
                for i, name in enumerate(names):
                    if name in by_name:
                        merged.append(by_name[name])
                    elif i < len(old_states) and old_states[i][CONF_STATE_NAME] not in names:
                        # Renamed in place: keep its thresholds and icon.
                        merged.append({**old_states[i], CONF_STATE_NAME: name})
                    else:
                        merged.append(_new_state(name, i, len(names)))
                self._states = merged
                self._index = 0
                return await self.async_step_state()

        schema = vol.Schema({
            vol.Required("state_names", default=self._state_names): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True)
            ),
        })
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="state_names", data_schema=schema, errors=errors
        )

    # -- step: one screen per state ------------------------------------- #
    async def async_step_state(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        total = len(self._states)
        index = self._index
        state = self._states[index]
        is_start = index == 0
        is_finish = index == total - 1
        role = "start" if is_start else "finish" if is_finish else "middle"

        if user_input is not None:
            state[CONF_THRESHOLD] = float(user_input[CONF_THRESHOLD])
            state[CONF_ICON] = user_input.get(CONF_ICON) or _ROLE_ICON[role]
            if role == "middle":
                state[CONF_COMPARISON] = user_input[CONF_COMPARISON]
            else:
                # The first state is always "above", the last always "below".
                state[CONF_COMPARISON] = COMPARISON_GREATER if is_start else COMPARISON_LESS
            self._index += 1
            if self._index < total:
                return await self.async_step_state()
            return await self.async_step_timing()

        fields: dict[Any, Any] = {
            vol.Required(CONF_THRESHOLD, default=state[CONF_THRESHOLD]): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=10000, step=0.5,
                    unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
        if role == "middle":
            fields[vol.Required(CONF_COMPARISON, default=state[CONF_COMPARISON])] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[COMPARISON_GREATER, COMPARISON_LESS],
                        translation_key="comparison",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        fields[vol.Optional(CONF_ICON, default=state[CONF_ICON])] = selector.IconSelector()

        lang = _lang(self.hass)  # type: ignore[attr-defined]
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="state",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "state": state[CONF_STATE_NAME],
                "position": f"{index + 1}/{total}",
                "role": _ROLE_TEXT[lang][role],
            },
        )

    # -- step: timings -------------------------------------------------- #
    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            advanced = user_input.get(ADVANCED, {})
            return self._save({
                CONF_STATES: self._states,
                CONF_ACTIVE_DELAY: int(user_input[CONF_ACTIVE_DELAY]),
                CONF_FINISHED_DELAY: int(user_input[CONF_FINISHED_DELAY]),
                CONF_IDLE_DELAY: int(user_input[CONF_IDLE_DELAY]),
                CONF_RESUME_WINDOW: int(advanced.get(CONF_RESUME_WINDOW, DEFAULT_RESUME_WINDOW)),
                CONF_SCAN_INTERVAL: int(advanced.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            })

        d = self._timing_defaults()
        schema = vol.Schema({
            vol.Required(CONF_ACTIVE_DELAY, default=d[CONF_ACTIVE_DELAY]): _seconds(10, 600, 5),
            vol.Required(CONF_FINISHED_DELAY, default=d[CONF_FINISHED_DELAY]): _seconds(30, 1800, 5),
            vol.Required(CONF_IDLE_DELAY, default=d[CONF_IDLE_DELAY]): _seconds(60, 7200, 30),
            vol.Required(ADVANCED): section(
                vol.Schema({
                    vol.Required(CONF_RESUME_WINDOW, default=d[CONF_RESUME_WINDOW]): _seconds(0, 7200, 30),
                    vol.Required(CONF_SCAN_INTERVAL, default=d[CONF_SCAN_INTERVAL]): _seconds(5, 60, 1),
                }),
                {"collapsed": True},
            ),
        })
        return self.async_show_form(step_id="timing", data_schema=schema, last_step=True)  # type: ignore[attr-defined]


class WattWatcherConfigFlow(_WizardMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a new appliance."""

    VERSION = 1

    def __init__(self) -> None:
        self._basics: dict[str, Any] = {}
        self._state_names = []
        self._states = []
        self._index = 0

    # -- wizard hooks --------------------------------------------------- #
    def _timing_defaults(self) -> dict[str, Any]:
        suggested = DEVICE_TYPE_TIMINGS.get(self._basics.get(CONF_DEVICE_TYPE, ""), {})
        return {
            CONF_ACTIVE_DELAY: DEFAULT_ACTIVE_DELAY,
            CONF_FINISHED_DELAY: suggested.get("finished_delay", DEFAULT_FINISHED_DELAY),
            CONF_IDLE_DELAY: DEFAULT_IDLE_DELAY,
            CONF_RESUME_WINDOW: DEFAULT_RESUME_WINDOW,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        }

    def _save(self, data: dict[str, Any]) -> config_entries.ConfigFlowResult:
        return self.async_create_entry(
            title=self._basics.get(CONF_NAME, DEFAULT_NAME),
            data={**self._basics, **data},
        )

    # -- step: user ----------------------------------------------------- #
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(f"{DOMAIN}_{user_input[CONF_POWER_SENSOR]}")
            self._abort_if_unique_id_configured()

            self._basics = dict(user_input)
            self._state_names = _default_state_names(user_input[CONF_DEVICE_TYPE], _lang(self.hass))
            return await self.async_step_state_names()

        schema = vol.Schema({
            vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
            vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_DEVICE_TYPE, default=DEFAULT_DEVICE_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DEVICE_TYPES,
                    translation_key="device_type",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    # -- step: reconfigure (change the power sensor / name) ------------- #
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry,
                title=user_input[CONF_NAME],
                data_updates={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_POWER_SENSOR: user_input[CONF_POWER_SENSOR],
                },
            )

        schema = vol.Schema({
            vol.Required(CONF_NAME, default=entry.data.get(CONF_NAME, DEFAULT_NAME)): selector.TextSelector(),
            vol.Required(
                CONF_POWER_SENSOR, default=entry.data.get(CONF_POWER_SENSOR)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return WattWatcherOptionsFlow()


class WattWatcherOptionsFlow(_WizardMixin, config_entries.OptionsFlow):
    """Edit timings, states and thresholds of an existing appliance.

    ``self.config_entry`` is provided by Home Assistant and is read-only.
    Everything is collected first and stored once as entry *options*, which the
    coordinator merges over the original entry data.
    """

    def __init__(self) -> None:
        self._state_names = []
        self._states = []
        self._index = 0

    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    # -- wizard hooks --------------------------------------------------- #
    def _timing_defaults(self) -> dict[str, Any]:
        cur = self._current()
        return {
            CONF_ACTIVE_DELAY: cur.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY),
            CONF_FINISHED_DELAY: cur.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY),
            CONF_IDLE_DELAY: cur.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY),
            CONF_RESUME_WINDOW: cur.get(CONF_RESUME_WINDOW, DEFAULT_RESUME_WINDOW),
            CONF_SCAN_INTERVAL: cur.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        }

    def _save(self, data: dict[str, Any]) -> config_entries.ConfigFlowResult:
        # Saving options runs the entry's update listener, which reloads it.
        return self.async_create_entry(title="", data=data)

    # -- step: menu ----------------------------------------------------- #
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._states = copy.deepcopy(self._current().get(CONF_STATES, []))
        self._state_names = [s[CONF_STATE_NAME] for s in self._states]
        return self.async_show_menu(step_id="init", menu_options=["timing", "state_names"])
