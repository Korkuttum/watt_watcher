"""Offline test of the Watt Watcher state machine (no Home Assistant needed).

Home Assistant modules are stubbed, then the coordinator is driven with a
synthetic power trace that looks like a dishwasher: heating, pauses of several
minutes, and a long silence at the end.

Run:  python3 tests/test_state_machine.py
"""
import importlib
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class _DUC:  # DataUpdateCoordinator stand-in
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, name=None, update_interval=None):
        self.hass = hass


for pkg in ("homeassistant", "homeassistant.helpers", "homeassistant.util"):
    _stub(pkg)
_stub("homeassistant.const", Platform=types.SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor"))
_stub("homeassistant.config_entries", ConfigEntry=object)
_stub("homeassistant.core", HomeAssistant=object)


class _Store:
    def __init__(self, *a, **k):
        pass

    def async_delay_save(self, *a, **k):
        pass


_stub("homeassistant.helpers.storage", Store=_Store)
_stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=_DUC)

CLOCK = {"now": datetime(2026, 1, 1, tzinfo=timezone.utc)}
_stub("homeassistant.util.dt", utcnow=lambda: CLOCK["now"], parse_datetime=lambda s: None)
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]

root = Path(__file__).resolve().parents[1] / "custom_components"
# Register the package without running its __init__ (which needs real HA)
_pkg = types.ModuleType("watt_watcher")
_pkg.__path__ = [str(root / "watt_watcher")]
sys.modules["watt_watcher"] = _pkg
coord_mod = importlib.import_module("watt_watcher.coordinator")


def make(**cfg):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    entry.data = {
        "name": "Dishwasher", "power_sensor": "sensor.p",
        "active_delay": 60, "finished_delay": 600, "idle_delay": 600,
        "resume_window": 1800, "scan_interval": 10,
        "states": [
            {"name": "yıkıyor", "threshold": 5.0, "comparison": "greater", "icon": "mdi:a"},
            {"name": "bitti", "threshold": 5.0, "comparison": "less", "icon": "mdi:b"},
        ],
        **cfg,
    }
    hass = MagicMock()
    events = []
    hass.bus.async_fire = lambda ev, data=None: events.append(ev.split("watt_watcher_")[1])
    c = coord_mod.WattWatcherCoordinator(hass, entry)
    return c, hass, events


def drive(c, hass, trace):
    """trace: list of (watts or None, minutes)."""
    import asyncio
    for watts, minutes in trace:
        for _ in range(int(minutes * 6)):  # 10 s steps
            CLOCK["now"] += timedelta(seconds=10)
            hass.states.get.return_value = (
                types.SimpleNamespace(state="unavailable") if watts is None
                else types.SimpleNamespace(state=str(watts))
            )
            c.data = asyncio.run(c._async_update_data())


def seq(events):
    return [e for e in events if e != "state_changed"]


# 1) Yesterday's real trace: 8 pauses of 2.5-10 min inside one wash
c, hass, ev = make(finished_delay=600)
drive(c, hass, [(0, 5), (1500, 100), (0, 4), (1500, 8), (0, 4), (1500, 10),
                (0, 9), (1500, 6), (0, 10), (1500, 5), (0, 40)])
print("finished_delay=600 :", seq(ev))
assert seq(ev).count("started") == 1, "should start exactly once"
assert seq(ev).count("finished") == 1, "pauses under 10 min must not finish"
assert seq(ev)[-2:] == ["finished", "idle"] or seq(ev)[-1] == "finished"

# 2) Short finished_delay: pauses DO finish, but the wake-up is a resume, never a new start
c, hass, ev = make(finished_delay=120)
drive(c, hass, [(1500, 30), (0, 5), (1500, 10), (0, 5), (1500, 10), (0, 40)])
print("finished_delay=120 :", seq(ev))
assert seq(ev).count("started") == 1, "pause wake-ups must be resumes, not starts"
assert seq(ev).count("resumed") == 2

# 3) Sensor unavailable in the middle of a wash must not look like a new start
c, hass, ev = make()
drive(c, hass, [(1500, 30), (None, 5), (1500, 30)])
print("unavailable blip   :", seq(ev))
assert seq(ev) == ["started"]

# 4) Wake-up after the resume window is a genuinely new cycle
c, hass, ev = make(finished_delay=120, idle_delay=300, resume_window=600)
drive(c, hass, [(1500, 30), (0, 30), (1500, 10)])
print("new cycle later    :", seq(ev))
assert seq(ev) == ["started", "finished", "idle", "started"]

# 5) resume_window = 0 restores the old behaviour (finished -> idle -> started)
c, hass, ev = make(finished_delay=120, idle_delay=300, resume_window=0)
drive(c, hass, [(1500, 30), (0, 10), (1500, 10)])
print("resume disabled    :", seq(ev))
assert seq(ev).count("resumed") == 0

# 6) A start state that is not the lowest threshold still starts a cycle
c, hass, ev = make(states=[
    {"name": "çalışıyor", "threshold": 5.0, "comparison": "greater", "icon": "x"},
    {"name": "ısıtıyor", "threshold": 1000.0, "comparison": "greater", "icon": "y"},
    {"name": "bitti", "threshold": 5.0, "comparison": "less", "icon": "z"},
])
drive(c, hass, [(2000, 5)])
print("jump to high power :", seq(ev), c.current_state)
assert seq(ev) == ["started"] and c.current_state == "ısıtıyor"

print("\nALL OK")
