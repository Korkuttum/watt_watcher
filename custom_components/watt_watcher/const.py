"""Constants for Watt Watcher."""

from homeassistant.const import Platform

DOMAIN = "watt_watcher"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Configuration keys
CONF_POWER_SENSOR = "power_sensor"
CONF_NAME = "name"
CONF_DEVICE_TYPE = "device_type"
CONF_STATES = "states"
CONF_ADVANCED = "advanced"
CONF_DEBOUNCE = "debounce"

# Default values
DEFAULT_NAME = "Appliance"
DEFAULT_SCAN_INTERVAL = 10  # seconds
DEFAULT_DEVICE_TYPE = "custom"

# State keys
STATE_OFF = "off"
STATE_STANDBY = "standby"
STATE_RUNNING = "running"
STATE_FINISHED = "finished"
STATE_ERROR = "error"
STATE_UNKNOWN = "unknown"

# Device type profiles
DEVICE_PROFILES = {
    "washing_machine": {
        "name": "Washing Machine",
        "icon": "mdi:washing-machine",
        "default_states": {
            "off": {"max": 1, "icon": "mdi:power-off"},
            "standby": {"min": 1, "max": 5, "icon": "mdi:sleep"},
            "preparing": {"min": 5, "max": 30, "icon": "mdi:water-alert"},
            "washing": {"min": 40, "max": 300, "icon": "mdi:water"},
            "rinsing": {"min": 100, "max": 200, "icon": "mdi:water-opacity"},
            "spinning": {"min": 300, "max": 800, "icon": "mdi:rotate-right"},
            "finished": {"min": 5, "max": 20, "icon": "mdi:check-circle"}
        }
    },
    "dishwasher": {
        "name": "Dishwasher",
        "icon": "mdi:dishwasher",
        "default_states": {
            "off": {"max": 1},
            "washing": {"min": 100, "max": 400},
            "drying": {"min": 800, "max": 1500},
            "finished": {"min": 5, "max": 20}
        }
    },
    "kettle": {
        "name": "Electric Kettle",
        "icon": "mdi:kettle",
        "default_states": {
            "off": {"max": 1},
            "boiling": {"min": 2000, "max": 3000},
            "keeping_warm": {"min": 50, "max": 200}
        }
    },
    "coffee_maker": {
        "name": "Coffee Maker",
        "icon": "mdi:coffee-maker",
        "default_states": {
            "off": {"max": 1},
            "heating": {"min": 800, "max": 1500},
            "brewing": {"min": 100, "max": 300}
        }
    },
    "custom": {
        "name": "Custom Appliance",
        "icon": "mdi:power-plug",
        "default_states": {
            "off": {"max": 1},
            "standby": {"min": 1, "max": 10},
            "running": {"min": 50, "max": 1000}
        }
    }
}

# Storage
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
