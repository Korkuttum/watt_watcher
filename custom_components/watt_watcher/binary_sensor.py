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
        """Return true if device is active (not idle and within delay)."""
        return self.coordinator.data.get("is_active", False)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        timing = self.coordinator.data.get("timing_settings", {})
        return {
            "current_power": self.coordinator.data.get("current_power", 0.0),
            "current_state": self.coordinator.data.get("current_state", "idle"),
            "active_delay": timing.get("active_delay", 60),
        }
