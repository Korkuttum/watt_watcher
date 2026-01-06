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
        self._attr_name = f"{coordinator.config.get('name')} Active"

    @property
    def is_on(self) -> bool:
        """Return true if device is active."""
        # Sadece coordinator'ın is_active değerini döndür
        # "bitti" durumu da aktif DEĞİL
        return self.coordinator.data.get("is_active", False)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        timing = self.coordinator.data.get("timing_settings", {})
        timers = self.coordinator.data.get("timers", {})
        
        # Kalan süreleri hesapla
        current_state = self.coordinator.data.get("current_state", "idle")
        bitti_duration = self.coordinator.data.get("bitti_duration", 0)
        idle_remaining = self.coordinator.data.get("idle_remaining", 0)
        
        active_timer = timers.get("active_timer", 0)
        finished_timer = timers.get("finished_timer", 0)
        
        active_delay = timing.get("active_delay", 60)
        finished_delay = timing.get("finished_delay", 300)
        idle_delay = timing.get("idle_delay", 3600)
        
        # Kalan süreler
        active_remaining = max(0, active_delay - active_timer) if active_timer < active_delay else 0
        finished_remaining = max(0, finished_delay - finished_timer) if finished_timer < finished_delay else 0
        
        # Durum mesajı
        status_message = "Hazır"
        if current_state == "bitti":
            status_message = f"Bekliyor ({idle_remaining}s)"
        elif not self.is_on and current_state != "idle":
            status_message = f"Aktif oluyor ({active_remaining}s)"
        
        return {
            "current_power": self.coordinator.data.get("current_power", 0.0),
            "current_state": current_state,
            "status_message": status_message,
            "active_delay": active_delay,
            "finished_delay": finished_delay,
            "idle_delay": idle_delay,
            "active_timer": active_timer,
            "finished_timer": finished_timer,
            "bitti_duration": bitti_duration,
            "active_in": active_remaining,      # Aktif olmaya kalan süre
            "finished_in": finished_remaining,  # Bitti olmaya kalan süre
            "idle_in": idle_remaining,          # Idle olmaya kalan süre
        }
