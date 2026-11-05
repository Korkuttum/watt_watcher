"""Binary sensor platform for Watt Watcher."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WattWatcherCoordinator
from .entity import WattWatcherEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watt Watcher binary sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Create binary sensor entity
    entities = [
        WattWatcherActiveSensor(coordinator, entry),
    ]
    
    async_add_entities(entities)


class WattWatcherActiveSensor(WattWatcherEntity, BinarySensorEntity):
    """Active binary sensor."""
    
    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_icon = "mdi:power"
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_active"
        self._attr_translation_key = "active"

    @property
    def is_on(self) -> bool:
        """Return true if device is active."""
        # On only while a cycle is running; "finished" and "idle" are off.
        return self.coordinator.data.get("is_active", False)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        timing = self.coordinator.data.get("timing_settings", {})
        timers = self.coordinator.data.get("timers", {})
        
        # Remaining times
        current_state = self.coordinator.data.get("current_state", "idle")
        finished_duration = self.coordinator.data.get("finished_duration", 0)
        idle_remaining = self.coordinator.data.get("idle_remaining", 0)
        
        active_timer = timers.get("active_timer", 0)
        finished_timer = timers.get("finished_timer", 0)
        
        active_delay = timing.get("active_delay", 60)
        finished_delay = timing.get("finished_delay", 300)
        idle_delay = timing.get("idle_delay", 3600)
        
        # Time left until each transition
        active_remaining = max(0, active_delay - active_timer) if active_timer < active_delay else 0
        finished_remaining = max(0, finished_delay - finished_timer) if finished_timer < finished_delay else 0
        
        # Machine-readable status: ready / waiting / starting
        status_message = "ready"
        if current_state == self.coordinator.finish_state_name:
            status_message = "waiting"
        elif not self.is_on and current_state != "idle":
            status_message = "starting"
        
        return {
            "current_power": self.coordinator.data.get("current_power", 0.0),
            "current_state": current_state,
            "status_message": status_message,
            "active_delay": active_delay,
            "finished_delay": finished_delay,
            "idle_delay": idle_delay,
            "active_timer": active_timer,
            "finished_timer": finished_timer,
            "finished_duration": finished_duration,
            "bitti_duration": finished_duration,  # deprecated alias
            "active_in": active_remaining,      # seconds until active
            "finished_in": finished_remaining,  # seconds until finished
            "idle_in": idle_remaining,          # seconds until idle
            "resume_count": self.coordinator.data.get("resume_count", 0),
        }
