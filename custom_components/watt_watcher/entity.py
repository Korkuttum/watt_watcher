"""Base entity for Watt Watcher."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import WattWatcherCoordinator


class WattWatcherEntity(CoordinatorEntity[WattWatcherCoordinator], Entity):
    """Base entity for Watt Watcher."""
    
    _attr_has_entity_name = True
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.config.get("name", "Appliance"),
            manufacturer="Watt Watcher",
            model="Power Monitor",
            sw_version=VERSION,
        )
    
    @property
    def available(self) -> bool:
        """Entities stay available while the coordinator has data."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
