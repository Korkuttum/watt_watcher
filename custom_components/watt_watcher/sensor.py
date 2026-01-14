# sensor.py (Değişiklikler: CycleDurationSensor için dakika birim, available'dan idle kontrolü kaldır, EnergySensor için available'dan idle kontrolü kaldır)
"""Sensor platform for Watt Watcher."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant, callback
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
    """Set up Watt Watcher sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Get configured states for options
    states_config = coordinator.data.get("states_config", [])
    state_options = [state["name"] for state in states_config]
    
    # Create sensor entities
    entities = [
        WattWatcherPowerSensor(coordinator, entry),
        WattWatcherStateSensor(coordinator, entry, state_options),
        WattWatcherCycleDurationSensor(coordinator, entry),
        WattWatcherEnergySensor(coordinator, entry),
    ]
    
    async_add_entities(entities)


class WattWatcherPowerSensor(WattWatcherEntity, SensorEntity):
    """Current power sensor."""
    
    _attr_icon = "mdi:flash"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_name = f"{coordinator.config.get('name')} Power"

    @property
    def native_value(self) -> float:
        """Return the current power consumption."""
        return round(self.coordinator.data.get("current_power", 0.0), 1)


class WattWatcherStateSensor(WattWatcherEntity, SensorEntity):
    """State sensor with dynamic icon."""
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry, state_options: list) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_state"
        self._attr_name = f"{coordinator.config.get('name')} Status"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = state_options

    @property
    def native_value(self) -> str:
        """Return the current state."""
        return self.coordinator.data.get("current_state", "idle")
    
    @property
    def icon(self) -> str:
        """Return dynamic icon based on current state."""
        return self.coordinator.data.get("current_icon", "mdi:circle")
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        timing = self.coordinator.data.get("timing_settings", {})
        states_config = self.coordinator.data.get("states_config", [])
        
        # Format states configuration for display - DÜZELTME BURADA
        formatted_states = []
        for state in states_config:
            formatted_states.append({
                "name": state.get("name", ""),
                "threshold": state.get("threshold", 0),  # min_watt yerine threshold
                "comparison": state.get("comparison", "greater"),  # karşılaştırma tipi
                "icon": state.get("icon", "mdi:circle")
            })
        
        return {
            "current_power": self.coordinator.data.get("current_power", 0.0),
            "state_duration": self.coordinator.data.get("state_duration", 0),
            "active_delay": timing.get("active_delay", 60),
            "finished_delay": timing.get("finished_delay", 300),
            "idle_delay": timing.get("idle_delay", 3600),
            "configured_states": formatted_states,  # Artık doğru alanları içeriyor
        }


class WattWatcherCycleDurationSensor(WattWatcherEntity, SensorEntity):
    """Cycle duration sensor."""
    
    _attr_icon = "mdi:progress-clock"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_cycle_duration"
        self._attr_name = f"{coordinator.config.get('name')} Cycle Duration"

    @property
    def native_value(self) -> int:
        """Return current cycle duration in minutes."""
        return self.coordinator.data.get("cycle_duration", 0) // 60
    
    @property
    def available(self) -> bool:
        """Only available when device is not idle. DEĞİŞİKLİK: Bu kontrolü kaldır, her zaman available olsun"""
        return super().available
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        duration_seconds = self.coordinator.data.get("cycle_duration", 0)
        duration_minutes = duration_seconds // 60
        remaining_seconds = duration_seconds % 60
        
        return {
            "minutes": duration_minutes,
            "seconds": remaining_seconds,
            "human_readable": f"{duration_minutes}m {remaining_seconds}s",
            "current_state": self.coordinator.data.get("current_state", "idle"),
        }


class WattWatcherEnergySensor(WattWatcherEntity, SensorEntity):
    """Energy consumption sensor."""
    
    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_energy"
        self._attr_name = f"{coordinator.config.get('name')} Energy"
        self._energy_this_cycle = 0.0
        self._last_update_time = datetime.now()
        self._last_power = 0.0
        
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._last_update_time = datetime.now()
        self._last_power = self.coordinator.data.get("current_power", 0.0)
        
        # Listen for coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        now = datetime.now()
        time_diff = (now - self._last_update_time).total_seconds()
        
        # Get current power and state
        current_power = self.coordinator.data.get("current_power", 0.0)
        current_state = self.coordinator.data.get("current_state", "idle")
        
        # Calculate average power
        avg_power = (self._last_power + current_power) / 2
        
        # Calculate energy (Wh = W * hours)
        energy_increment = avg_power * (time_diff / 3600)
        
        # Reset energy when returning to idle
        if current_state == "idle":
            self._energy_this_cycle = 0.0
        else:
            # Add energy when not idle
            self._energy_this_cycle += energy_increment
        
        # Update tracking variables
        self._last_update_time = now
        self._last_power = current_power
        
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return energy consumed in current cycle."""
        return round(self._energy_this_cycle, 3)
    
    @property
    def available(self) -> bool:
        """Only available when device is not idle. DEĞİŞİKLİK: Bu kontrolü kaldır, her zaman available olsun"""
        return super().available
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "kwh": round(self._energy_this_cycle / 1000, 4),
            "current_state": self.coordinator.data.get("current_state", "idle"),
        }
