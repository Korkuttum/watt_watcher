"""Coordinator for Watt Watcher."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_NAME,
    CONF_DEVICE_TYPE,
    DEVICE_PROFILES,
    DEFAULT_SCAN_INTERVAL,
    STATE_OFF,
    STATE_RUNNING,
    STATE_FINISHED,
)

_LOGGER = logging.getLogger(__name__)


class WattWatcherCoordinator(DataUpdateCoordinator):
    """Coordinator for Watt Watcher."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.config = dict(entry.data)
        self.options = dict(entry.options)
        
        # Device state
        self.current_state = STATE_OFF
        self.current_power = 0.0
        self.state_start_time = datetime.now()
        self.cycle_start_time = None
        self.power_history: List[float] = []
        
        # Timers for debounce
        self.low_power_timer = 0
        self.pause_timer = 0
        
        # Configuration
        self.scan_interval = self.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from power sensor and update state."""
        try:
            # Get power sensor value
            power_entity = self.config[CONF_POWER_SENSOR]
            self.current_power = float(self.hass.states.get(power_entity).state)
            
            # Update state based on power
            new_state = self._determine_state(self.current_power)
            
            if new_state != self.current_state:
                self._on_state_change(new_state)
                
            # Update power history (last 10 readings)
            self.power_history.append(self.current_power)
            if len(self.power_history) > 10:
                self.power_history.pop(0)
            
            return {
                "state": self.current_state,
                "power": self.current_power,
                "state_duration": self._get_state_duration(),
                "cycle_duration": self._get_cycle_duration(),
                "avg_power": self._get_average_power(),
            }
            
        except (ValueError, AttributeError, TypeError) as err:
            _LOGGER.error("Error updating power data: %s", err)
            return {
                "state": STATE_ERROR,
                "power": 0.0,
                "state_duration": 0,
                "cycle_duration": 0,
                "avg_power": 0.0,
            }

    def _determine_state(self, power: float) -> str:
        """Determine appliance state based on power consumption."""
        
        # Simple state determination logic
        if power < 1:
            # Very low power - check if it's been long enough for OFF
            self.low_power_timer += self.scan_interval
            if self.low_power_timer > 300:  # 5 minutes
                return STATE_OFF
            else:
                return self.current_state  # Keep current state
        else:
            # Reset low power timer
            self.low_power_timer = 0
            
        if power > 40:
            # High power = running
            if self.current_state != STATE_RUNNING:
                # Starting new cycle
                self.cycle_start_time = datetime.now()
            return STATE_RUNNING
            
        elif 5 < power < 40:
            # Medium power = standby
            return "standby"
            
        elif 1 < power < 5:
            # Finished state (low but not zero)
            if self.current_state == STATE_RUNNING:
                self.pause_timer += self.scan_interval
                if self.pause_timer > 300:  # 5 minutes in low power after running
                    return STATE_FINISHED
                else:
                    return STATE_RUNNING  # Still in pause
            else:
                return "standby"
                
        return self.current_state  # Default: keep current state

    def _on_state_change(self, new_state: str) -> None:
        """Handle state change."""
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = datetime.now()
        
        # Reset timers
        if new_state == STATE_RUNNING:
            self.pause_timer = 0
            self.low_power_timer = 0
            
        _LOGGER.debug(
            "State changed: %s -> %s (power: %.1fW)",
            old_state, new_state, self.current_power
        )

    def _get_state_duration(self) -> int:
        """Get duration in current state in seconds."""
        return int((datetime.now() - self.state_start_time).total_seconds())

    def _get_cycle_duration(self) -> int:
        """Get current cycle duration in seconds."""
        if self.cycle_start_time:
            return int((datetime.now() - self.cycle_start_time).total_seconds())
        return 0

    def _get_average_power(self) -> float:
        """Get average power from history."""
        if not self.power_history:
            return 0.0
        return sum(self.power_history) / len(self.power_history)
