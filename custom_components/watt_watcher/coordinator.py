"""Coordinator for Watt Watcher.

State machine
-------------
::

    idle ──(power "on" for active_delay)──────────────▶ active states
    active states ──(power "off" for finished_delay)──▶ finish state
    finish ──(power "on" for active_delay,
              within resume_window)───────────────────▶ active states   (RESUME)
    finish ──(max(idle_delay, resume_window))─────────▶ idle

A *resume* keeps the same cycle (same start time, same energy counter) and
fires ``watt_watcher_resumed`` instead of ``watt_watcher_started``.  This is
what stops dishwashers, which pause for minutes between phases, from
announcing a new start every time the heater switches on again.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    COMPARISON_GREATER,
    COMPARISON_LESS,
    CONF_ACTIVE_DELAY,
    CONF_COMPARISON,
    CONF_FINISHED_DELAY,
    CONF_ICON,
    CONF_IDLE_DELAY,
    CONF_POWER_SENSOR,
    CONF_RESUME_WINDOW,
    CONF_SCAN_INTERVAL,
    CONF_STATE_NAME,
    CONF_STATES,
    CONF_THRESHOLD,
    DEFAULT_ACTIVE_DELAY,
    DEFAULT_FINISHED_DELAY,
    DEFAULT_IDLE_DELAY,
    DEFAULT_RESUME_WINDOW,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_FINISHED,
    EVENT_IDLE,
    EVENT_RESUMED,
    EVENT_STARTED,
    EVENT_STATE_CHANGED,
    STATE_IDLE,
    STATE_UNKNOWN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _seconds(since: datetime | None, now: datetime) -> int:
    """Whole seconds between ``since`` and ``now`` (0 when ``since`` is None)."""
    if since is None:
        return 0
    return max(0, int((now - since).total_seconds()))


class WattWatcherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Track an appliance's cycle by watching a power sensor."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.config: dict[str, Any] = {**entry.data, **entry.options}

        # Timing configuration
        self.scan_interval = self.config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.active_delay = self.config.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY)
        self.finished_delay = self.config.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY)
        self.idle_delay = self.config.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY)
        self.resume_window = self.config.get(CONF_RESUME_WINDOW, DEFAULT_RESUME_WINDOW)
        # "finished" is kept at least as long as a resume is still possible,
        # otherwise a resume would show up as a brand new start.
        self.idle_timeout = max(self.idle_delay, self.resume_window)

        # States: the first one is "start", the last one is "finish".
        self.states_config: list[dict[str, Any]] = self.config.get(CONF_STATES, [])
        self.state_icons = {
            s[CONF_STATE_NAME]: s.get(CONF_ICON, "mdi:circle") for s in self.states_config
        }
        if self.states_config:
            self.start_state_name = self.states_config[0][CONF_STATE_NAME]
            self.finish_state_name = self.states_config[-1][CONF_STATE_NAME]
        else:
            self.start_state_name = "çalışıyor"
            self.finish_state_name = "bitti"

        # Runtime state
        self.current_power = 0.0
        self.current_state = STATE_IDLE
        self.state_start_time: datetime = dt_util.utcnow()
        self.cycle_start_time: datetime | None = None
        self.finish_start_time: datetime | None = None
        self.resume_count = 0
        self.power_available = True

        # Debounce timers
        self.active_timer_start: datetime | None = None
        self.finished_timer_start: datetime | None = None

        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=self.scan_interval),
        )

    # ------------------------------------------------------------------ #
    # Persistence (so a Home Assistant restart in the middle of a wash
    # does not turn into a fake "started" notification)
    # ------------------------------------------------------------------ #
    async def async_load_state(self) -> None:
        """Restore the state saved before the last shutdown."""
        stored = await self._store.async_load()
        if not stored:
            return

        state = stored.get("state", STATE_IDLE)
        valid = {s[CONF_STATE_NAME] for s in self.states_config} | {STATE_IDLE}
        if state not in valid:
            return

        self.current_state = state
        self.cycle_start_time = dt_util.parse_datetime(stored.get("cycle_start") or "")
        self.finish_start_time = dt_util.parse_datetime(stored.get("finish_start") or "")
        self.resume_count = int(stored.get("resume_count", 0))
        _LOGGER.debug("Restored state %s", state)

    def _save_state(self) -> None:
        self._store.async_delay_save(
            lambda: {
                "state": self.current_state,
                "cycle_start": self.cycle_start_time.isoformat() if self.cycle_start_time else None,
                "finish_start": self.finish_start_time.isoformat() if self.finish_start_time else None,
                "resume_count": self.resume_count,
            },
            1,
        )

    # ------------------------------------------------------------------ #
    # Update loop
    # ------------------------------------------------------------------ #
    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        power = self._read_power()

        if power is None:
            # Sensor is unavailable (Wi-Fi blip, restart ...).  Do NOT touch
            # the state machine: dropping to idle here is what used to make
            # the next reading look like a fresh start.
            return self._build_data(now)

        self.current_power = power
        raw = self._raw_state(power)
        new_state = self._advance(raw, now)
        if new_state != self.current_state:
            self._transition(new_state, now)

        _LOGGER.debug(
            "power=%.1fW raw=%s state=%s resumes=%d",
            power, raw, self.current_state, self.resume_count,
        )
        return self._build_data(now)

    def _read_power(self) -> float | None:
        entity_id = self.config[CONF_POWER_SENSOR]
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", ""):
            if self.power_available:
                _LOGGER.warning("Power sensor %s is unavailable, holding state", entity_id)
            self.power_available = False
            return None
        try:
            power = float(state.state)
        except ValueError:
            _LOGGER.warning("Power sensor %s has a non-numeric state: %s", entity_id, state.state)
            self.power_available = False
            return None
        self.power_available = True
        return power

    def _raw_state(self, power: float) -> str:
        """Map a power reading to a configured state name (no delays)."""
        greater = sorted(
            (s for s in self.states_config if s[CONF_COMPARISON] == COMPARISON_GREATER),
            key=lambda s: s[CONF_THRESHOLD],
            reverse=True,
        )
        less = sorted(
            (s for s in self.states_config if s[CONF_COMPARISON] == COMPARISON_LESS),
            key=lambda s: s[CONF_THRESHOLD],
        )
        for s in greater:
            if power > s[CONF_THRESHOLD]:
                return s[CONF_STATE_NAME]
        for s in less:
            if power < s[CONF_THRESHOLD]:
                return s[CONF_STATE_NAME]
        return STATE_UNKNOWN

    # ------------------------------------------------------------------ #
    # State machine
    # ------------------------------------------------------------------ #
    def _advance(self, raw: str, now: datetime) -> str:
        """Return the state we should be in, after applying the delays."""
        current = self.current_state
        finish = self.finish_state_name
        is_activity = raw not in (finish, STATE_UNKNOWN)

        if current == STATE_IDLE:
            return self._debounce_activity(raw, is_activity, now, STATE_IDLE)

        if current == finish:
            if _seconds(self.finish_start_time, now) >= self.idle_timeout:
                return STATE_IDLE
            # Power came back: wake up again (resume) instead of staying
            # "finished" or restarting from idle.
            if self.resume_window > 0:
                return self._debounce_activity(raw, is_activity, now, finish)
            return finish

        # An active state (anything but idle / finish)
        if raw == finish:
            if self.finished_timer_start is None:
                self.finished_timer_start = now
            if _seconds(self.finished_timer_start, now) >= self.finished_delay:
                self.finished_timer_start = None
                return finish
            return current  # looks off, but not for long enough yet

        self.finished_timer_start = None
        return current if raw == STATE_UNKNOWN else raw

    def _debounce_activity(self, raw: str, is_activity: bool, now: datetime, stay: str) -> str:
        """Require activity for ``active_delay`` seconds before leaving ``stay``."""
        if not is_activity:
            self.active_timer_start = None
            return stay
        if self.active_timer_start is None:
            self.active_timer_start = now
        if _seconds(self.active_timer_start, now) >= self.active_delay:
            self.active_timer_start = None
            return raw
        return stay

    def _transition(self, new_state: str, now: datetime) -> None:
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = now
        self.active_timer_start = None
        self.finished_timer_start = None

        _LOGGER.info("%s: %s -> %s (%.1fW)", self.config.get("name"), old_state, new_state, self.current_power)

        if old_state == STATE_IDLE:
            self.cycle_start_time = now
            self.finish_start_time = None
            self.resume_count = 0
            self._fire(EVENT_STARTED, old_state, new_state, now)
        elif new_state == STATE_IDLE:
            self._fire(EVENT_IDLE, old_state, new_state, now)
            self.cycle_start_time = None
            self.finish_start_time = None
        elif new_state == self.finish_state_name:
            self.finish_start_time = now
            self._fire(EVENT_FINISHED, old_state, new_state, now)
        elif old_state == self.finish_state_name:
            self.finish_start_time = None
            self.resume_count += 1
            self._fire(EVENT_RESUMED, old_state, new_state, now)

        self.hass.bus.async_fire(
            EVENT_STATE_CHANGED, self._event_data(old_state, new_state, now)
        )
        self._save_state()

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #
    def _event_data(self, old_state: str, new_state: str, now: datetime) -> dict[str, Any]:
        return {
            "entry_id": self.entry.entry_id,
            "name": self.config.get("name"),
            "from": old_state,
            "to": new_state,
            "power": self.current_power,
            "cycle_duration": self._cycle_duration(now),
            "resume_count": self.resume_count,
        }

    def _fire(self, event: str, old_state: str, new_state: str, now: datetime) -> None:
        self.hass.bus.async_fire(event, self._event_data(old_state, new_state, now))

    def _cycle_duration(self, now: datetime) -> int:
        """Seconds the cycle has been running (frozen once it has finished)."""
        if self.cycle_start_time is None or self.current_state == STATE_IDLE:
            return 0
        end = self.finish_start_time if self.current_state == self.finish_state_name else now
        return _seconds(self.cycle_start_time, end or now)

    def _build_data(self, now: datetime) -> dict[str, Any]:
        state = self.current_state
        finished = state == self.finish_state_name
        finish_duration = _seconds(self.finish_start_time, now) if finished else 0

        if state == STATE_IDLE:
            icon = "mdi:power-off"
        else:
            icon = self.state_icons.get(state, "mdi:circle")

        return {
            "current_power": self.current_power,
            "current_state": state,
            "current_icon": icon,
            "state_duration": _seconds(self.state_start_time, now),
            "cycle_duration": self._cycle_duration(now),
            "is_active": state not in (STATE_IDLE, self.finish_state_name),
            "power_available": self.power_available,
            "resume_count": self.resume_count,
            "bitti_duration": finish_duration,
            "idle_remaining": max(0, self.idle_timeout - finish_duration) if finished else 0,
            "timing_settings": {
                "active_delay": self.active_delay,
                "finished_delay": self.finished_delay,
                "idle_delay": self.idle_delay,
                "resume_window": self.resume_window,
            },
            "states_config": self.states_config,
            "timers": {
                "active_timer": _seconds(self.active_timer_start, now),
                "finished_timer": _seconds(self.finished_timer_start, now),
            },
        }
