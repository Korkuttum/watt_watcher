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
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, STATE_OFF, STATE_RUNNING, STATE_FINISHED
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
    
    # Create sensor entities
    entities = [
        WattWatcherStatusSensor(coordinator, entry),
        WattWatcherPowerSensor(coordinator, entry),
        WattWatcherStateDurationSensor(coordinator, entry),
        WattWatcherCycleDurationSensor(coordinator, entry),
        WattWatcherEnergySensor(coordinator, entry),
    ]
    
    async_add_entities(entities)


class WattWatcherStatusSensor(WattWatcherEntity, SensorEntity):
    """Status sensor for Watt Watcher."""
    
    _attr_icon = "mdi:state-machine"
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_name = f"{coordinator.config.get('name')} Status"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [
            "off", 
            "standby", 
            "running", 
            "finished", 
            "error", 
            "unknown"
        ]

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self.coordinator.data.get("state", "unknown")


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
        return round(self.coordinator.data.get("power", 0.0), 1)
    
    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested number of decimal places."""
        return 1


class WattWatcherStateDurationSensor(WattWatcherEntity, SensorEntity):
    """Current state duration sensor."""
    
    _attr_icon = "mdi:timer"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_state_duration"
        self._attr_name = f"{coordinator.config.get('name')} State Duration"

    @property
    def native_value(self) -> int:
        """Return the duration in current state."""
        return self.coordinator.data.get("state_duration", 0)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        duration = self.coordinator.data.get("state_duration", 0)
        return {
            "hours": duration // 3600,
            "minutes": (duration % 3600) // 60,
            "seconds": duration % 60,
            "human_readable": self._format_duration(duration)
        }
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration as human readable string."""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}分{seconds % 60}秒"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}時間{minutes}分"


class WattWatcherCycleDurationSensor(WattWatcherEntity, SensorEntity, RestoreEntity):
    """Cycle duration sensor with persistence."""
    
    _attr_icon = "mdi:progress-clock"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_cycle_duration"
        self._attr_name = f"{coordinator.config.get('name')} Cycle Duration"
        self._cycle_start_time = None
        self._last_cycle_duration = 0
        self._total_cycles = 0
        
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) is not None:
            if "total_cycles" in last_state.attributes:
                self._total_cycles = int(last_state.attributes["total_cycles"])
            if "last_cycle_duration" in last_state.attributes:
                self._last_cycle_duration = int(last_state.attributes["last_cycle_duration"])
        
        # Listen for state changes to track cycles
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        current_state = data.get("state", "unknown")
        
        # Track cycle start/end
        if current_state == STATE_RUNNING:
            if self._cycle_start_time is None:
                # New cycle started
                self._cycle_start_time = datetime.now()
        elif self._cycle_start_time is not None:
            if current_state in [STATE_FINISHED, STATE_OFF]:
                # Cycle ended
                cycle_duration = int((datetime.now() - self._cycle_start_time).total_seconds())
                self._last_cycle_duration = cycle_duration
                self._total_cycles += 1
                self._cycle_start_time = None
        
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return current cycle duration."""
        if self._cycle_start_time:
            return int((datetime.now() - self._cycle_start_time).total_seconds())
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "last_cycle_duration": self._last_cycle_duration,
            "total_cycles": self._total_cycles,
            "cycle_start_time": self._cycle_start_time.isoformat() if self._cycle_start_time else None,
            "current_cycle_human_readable": self._format_duration(self.native_value),
            "last_cycle_human_readable": self._format_duration(self._last_cycle_duration)
        }
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration as human readable string."""
        if seconds == 0:
            return "0秒"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}時間{minutes}分{secs}秒"
        elif minutes > 0:
            return f"{minutes}分{secs}秒"
        else:
            return f"{secs}秒"


class WattWatcherEnergySensor(WattWatcherEntity, SensorEntity):
    """Energy consumption sensor for current cycle."""
    
    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_suggested_display_precision = 3
    
    def __init__(self, coordinator: WattWatcherCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_energy"
        self._attr_name = f"{coordinator.config.get('name')} Energy"
        self._energy_this_cycle = 0.0
        self._last_update_time = datetime.now()
        
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._last_update_time = datetime.now()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        now = datetime.now()
        time_diff = (now - self._last_update_time).total_seconds()
        
        # Calculate energy (Wh = W * hours)
        avg_power = self.coordinator.data.get("avg_power", 0.0)
        energy_increment = avg_power * (time_diff / 3600)  # Convert seconds to hours
        
        # Only add energy if device is running
        if self.coordinator.data.get("state") == STATE_RUNNING:
            self._energy_this_cycle += energy_increment
        
        # Reset energy when cycle ends
        current_state = self.coordinator.data.get("state", "unknown")
        if current_state not in [STATE_RUNNING, "unknown"]:
            self._energy_this_cycle = 0.0
        
        self._last_update_time = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return energy consumed in current cycle."""
        return round(self._energy_this_cycle, 3)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "kwh": round(self._energy_this_cycle / 1000, 4),
            "avg_power_w": self.coordinator.data.get("avg_power", 0.0)
        }
