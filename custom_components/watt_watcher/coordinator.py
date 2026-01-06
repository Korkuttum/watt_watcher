"""Coordinator for Watt Watcher."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_STATES,
    CONF_STATE_NAME,
    CONF_THRESHOLD,
    CONF_COMPARISON,
    CONF_ICON,
    CONF_ACTIVE_DELAY,
    CONF_FINISHED_DELAY,
    CONF_IDLE_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ACTIVE_DELAY,
    DEFAULT_FINISHED_DELAY,
    DEFAULT_IDLE_DELAY,
    COMPARISON_GREATER,
    COMPARISON_LESS,
)

_LOGGER = logging.getLogger(__name__)


class WattWatcherCoordinator(DataUpdateCoordinator):
    """Coordinator for Watt Watcher."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.config = dict(entry.data)
        
        # State tracking
        self.current_power = 0.0
        self.current_state = "unknown"
        self.state_start_time = datetime.now()
        self.cycle_start_time = None
        
        # Configuration
        self.scan_interval = self.config.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        self.active_delay = self.config.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY)
        self.finished_delay = self.config.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY)
        self.idle_delay = self.config.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY)
        
        # States configuration
        self.states_config = self.config.get(CONF_STATES, [])
        self.state_icons = {}
        
        for state in self.states_config:
            state_name = state[CONF_STATE_NAME]
            self.state_icons[state_name] = state.get(CONF_ICON, "mdi:circle")
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from power sensor and update states."""
        try:
            # Get power sensor value
            power_entity = self.config[CONF_POWER_SENSOR]
            state = self.hass.states.get(power_entity)
            
            if state is None or state.state in ["unknown", "unavailable"]:
                _LOGGER.warning("Power sensor unavailable: %s", power_entity)
                return self._create_error_data()
            
            self.current_power = float(state.state)
            
            # Determine state based on thresholds
            new_state = self._determine_state(self.current_power)
            
            if new_state != self.current_state:
                self._on_state_change(new_state)
            
            # Get current state icon
            current_icon = self.state_icons.get(self.current_state, "mdi:circle")
            
            return {
                "current_power": self.current_power,
                "current_state": self.current_state,
                "current_icon": current_icon,
                "state_duration": self._get_state_duration(),
                "cycle_duration": self._get_cycle_duration(),
                "is_active": self.current_state not in ["unknown", "idle", "bitti"],
                "timing_settings": {
                    "active_delay": self.active_delay,
                    "finished_delay": self.finished_delay,
                    "idle_delay": self.idle_delay,
                },
                "states_config": self.states_config,
            }
            
        except (ValueError, AttributeError, TypeError) as err:
            _LOGGER.error("Error updating power data: %s", err)
            return self._create_error_data()

    def _determine_state(self, power: float) -> str:
        """Determine state based on threshold comparisons."""
        # Check each state in order (first match wins)
        for state in self.states_config:
            state_name = state[CONF_STATE_NAME]
            threshold = state[CONF_THRESHOLD]
            comparison = state[CONF_COMPARISON]
            
            if comparison == COMPARISON_GREATER:
                if power > threshold:
                    return state_name
            elif comparison == COMPARISON_LESS:
                if power < threshold:
                    return state_name
        
        # If no state matches, return unknown
        return "unknown"

    def _on_state_change(self, new_state: str) -> None:
        """Handle state change."""
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = datetime.now()
        
        # Start cycle timer when entering first active state
        if old_state in ["unknown", "idle", "bitti"] and new_state not in ["unknown", "idle", "bitti"]:
            self.cycle_start_time = datetime.now()
            _LOGGER.info("Cycle started: %s", new_state)
        
        # End cycle when returning to idle/finished
        elif old_state not in ["unknown", "idle", "bitti"] and new_state in ["unknown", "idle", "bitti"]:
            if self.cycle_start_time:
                cycle_duration = (datetime.now() - self.cycle_start_time).total_seconds()
                _LOGGER.info("Cycle ended. Duration: %d seconds", cycle_duration)
            self.cycle_start_time = None
        
        _LOGGER.debug(
            "State changed: %s -> %s (power: %.1fW)",
            old_state, new_state, self.current_power
        )

    def _get_state_duration(self) -> int:
        """Get duration in current state in seconds."""
        return int((datetime.now() - self.state_start_time).total_seconds())

    def _get_cycle_duration(self) -> int:
        """Get current cycle duration in seconds."""
        if self.cycle_start_time and self.current_state not in ["unknown", "idle", "bitti"]:
            return int((datetime.now() - self.cycle_start_time).total_seconds())
        return 0

    def _create_error_data(self) -> Dict[str, Any]:
        """Create error data structure."""
        return {
            "current_power": 0.0,
            "current_state": "error",
            "current_icon": "mdi:alert-circle",
            "state_duration": 0,
            "cycle_duration": 0,
            "is_active": False,
            "timing_settings": {
                "active_delay": self.active_delay,
                "finished_delay": self.finished_delay,
                "idle_delay": self.idle_delay,
            },
            "states_config": self.states_config,
        }
