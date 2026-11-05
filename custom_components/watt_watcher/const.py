"""Constants for Watt Watcher."""

from homeassistant.const import Platform

DOMAIN = "watt_watcher"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
VERSION = "0.2.1"

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
CONF_RESUME_WINDOW = "resume_window"
CONF_SCAN_INTERVAL = "scan_interval"

# Default values
DEFAULT_NAME = "Appliance"
DEFAULT_SCAN_INTERVAL = 10  # seconds
DEFAULT_DEVICE_TYPE = "custom"
DEFAULT_ACTIVE_DELAY = 60     # power must stay "on" this long to start a cycle
DEFAULT_FINISHED_DELAY = 300  # power must stay "off" this long to finish a cycle
DEFAULT_IDLE_DELAY = 3600     # how long "finished" is shown before going idle
DEFAULT_RESUME_WINDOW = 1800  # a cycle that wakes up again within this time is
                              # the SAME cycle, not a new start (0 = disabled)

# Per device type suggestions used by the setup form
DEVICE_TYPE_TIMINGS = {
    "washing_machine": {"finished_delay": 300},
    "dishwasher": {"finished_delay": 600},
    "kettle": {"finished_delay": 60},
    "coffee_maker": {"finished_delay": 120},
}

# Internal states
STATE_IDLE = "idle"
STATE_UNKNOWN = "unknown"

# Comparison types
COMPARISON_GREATER = "greater"
COMPARISON_LESS = "less"

# Events fired on the Home Assistant bus
EVENT_STARTED = f"{DOMAIN}_started"      # a brand new cycle began (idle -> active)
EVENT_FINISHED = f"{DOMAIN}_finished"    # the cycle finished
EVENT_RESUMED = f"{DOMAIN}_resumed"      # finished-looking cycle woke up again
EVENT_IDLE = f"{DOMAIN}_idle"            # back to idle, cycle closed
EVENT_STATE_CHANGED = f"{DOMAIN}_state_changed"

# Storage
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
