"""End-to-end test: set the integration up in a real Home Assistant and drive a cycle."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

DOMAIN = "watt_watcher"
DATA = {
    "name": "Dishwasher", "power_sensor": "sensor.plug_power", "device_type": "dishwasher",
    "states": [
        {"name": "running", "threshold": 5.0, "comparison": "greater", "icon": "mdi:play-circle"},
        {"name": "finished", "threshold": 5.0, "comparison": "less", "icon": "mdi:check-circle"},
    ],
    "active_delay": 60, "finished_delay": 120, "idle_delay": 600,
    "resume_window": 1800, "scan_interval": 10,
}


async def _advance(hass, freezer, seconds):
    for _ in range(seconds // 10):
        freezer.tick(timedelta(seconds=10))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()


async def test_entities_are_named_from_translations_and_cycle_resumes(hass, freezer):
    hass.states.async_set("sensor.plug_power", "0")
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=f"{DOMAIN}_sensor.plug_power")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity_id in (
        "sensor.dishwasher_power", "sensor.dishwasher_status",
        "sensor.dishwasher_cycle_duration", "sensor.dishwasher_cycle_energy",
        "binary_sensor.dishwasher_active",
    ):
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get("sensor.dishwasher_status").state == "idle"

    started = async_capture_events(hass, "watt_watcher_started")
    finished = async_capture_events(hass, "watt_watcher_finished")
    resumed = async_capture_events(hass, "watt_watcher_resumed")

    # heating -> started once
    hass.states.async_set("sensor.plug_power", "1500")
    await _advance(hass, freezer, 80)
    assert hass.states.get("sensor.dishwasher_status").state == "running"
    assert hass.states.get("binary_sensor.dishwasher_active").state == "on"
    assert len(started) == 1

    # pause longer than finish_delay -> finished
    hass.states.async_set("sensor.plug_power", "0")
    await _advance(hass, freezer, 140)
    assert hass.states.get("sensor.dishwasher_status").state == "finished"
    assert len(finished) == 1

    # heater comes back -> RESUMED, not a second "started"
    hass.states.async_set("sensor.plug_power", "1500")
    await _advance(hass, freezer, 80)
    assert hass.states.get("sensor.dishwasher_status").state == "running"
    assert len(started) == 1
    assert len(resumed) == 1

    # plug drops off for a while: state must be held, not reset
    hass.states.async_set("sensor.plug_power", "unavailable")
    await _advance(hass, freezer, 120)
    assert hass.states.get("sensor.dishwasher_status").state == "running"
    assert len(started) == 1


async def test_options_override_entry_data(hass):
    hass.states.async_set("sensor.plug_power", "0")
    entry = MockConfigEntry(
        domain=DOMAIN, data=DATA, options={"finished_delay": 777},
        unique_id=f"{DOMAIN}_sensor.plug_power",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].finished_delay == 777
