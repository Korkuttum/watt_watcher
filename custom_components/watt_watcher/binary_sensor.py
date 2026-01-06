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

from .const import DOMAIN, STATE_RUNNING
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
        WattWatcherRunningSensor(coordinator, entry),
    ]
    
    async_add_entities(entities)


class WattWatcherRunningSensor(WattWatcherEntity, BinarySensorEntity):
    """Binary sensor indicating if appliance is running."""
    
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_running"
        self._attr_name = f"{coordinator.config.get('name')} Running"
        self._attr_icon = "mdi:power"

    @property
    def is_on(self) -> bool:
        """Return true if appliance is running."""
        return self.coordinator.data.get("state") == STATE_RUNNING
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "current_power": self.coordinator.data.get("power", 0.0),
            "state_duration": self.coordinator.data.get("state_duration", 0),
            "cycle_duration": self.coordinator.data.get("cycle_duration", 0)
        }
