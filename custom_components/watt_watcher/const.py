"""Constants for Watt Watcher."""

from homeassistant.const import Platform

DOMAIN = "watt_watcher"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Configuration keys
CONF_POWER_SENSOR = "power_sensor"
CONF_NAME = "name"
CONF_DEVICE_TYPE = "device_type"
CONF_STATES = "states"
CONF_STATE_NAME = "name"
CONF_THRESHOLD = "threshold"
CONF_COMPARISON = "comparison"
CONF_ICON = "icon"
CONF_ACTIVE_DELAY = "active_delay"
CONF_FINISHED_DELAY = "finished_delay"
CONF_IDLE_DELAY = "idle_delay"

# Default values
DEFAULT_NAME = "Appliance"
DEFAULT_SCAN_INTERVAL = 10  # seconds
DEFAULT_DEVICE_TYPE = "custom"
DEFAULT_ACTIVE_DELAY = 60    # 1 minute
DEFAULT_FINISHED_DELAY = 300  # 5 minutes
DEFAULT_IDLE_DELAY = 3600    # 1 hour

# Comparison types
COMPARISON_GREATER = "greater"
COMPARISON_LESS = "less"

# Storage
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
