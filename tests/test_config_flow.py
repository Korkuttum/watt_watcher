"""Config flow and options flow tests (run against a real Home Assistant)."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "watt_watcher"

STATES = [
    {"name": "running", "threshold": 5.0, "comparison": "greater", "icon": "mdi:play-circle"},
    {"name": "finished", "threshold": 5.0, "comparison": "less", "icon": "mdi:check-circle"},
]
DATA = {
    "name": "Dishwasher", "power_sensor": "sensor.plug_power", "device_type": "dishwasher",
    "states": STATES, "active_delay": 60, "finished_delay": 60, "idle_delay": 60, "scan_interval": 10,
}


def _no_setup():
    return patch("custom_components.watt_watcher.async_setup_entry", return_value=True)


async def test_setup_flow_creates_entry(hass):
    with _no_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Dishwasher", "power_sensor": "sensor.plug_power", "device_type": "dishwasher"},
        )
        assert result["step_id"] == "state_names"
        # English Home Assistant -> English default names, last one is the finish state
        assert result["data_schema"]({}) == {"state_names": ["running", "washing", "drying", "finished"]}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"state_names": ["running", "washing", "finished"]}
        )
        # one screen per state
        for expected_position in ("1/3", "2/3", "3/3"):
            assert result["step_id"] == "state"
            assert result["description_placeholders"]["position"] == expected_position
            payload = {"threshold": 5.0, "icon": "mdi:circle"}
            if expected_position == "2/3":
                payload.update(threshold=1000.0, comparison="greater")
            result = await hass.config_entries.flow.async_configure(result["flow_id"], payload)

        assert result["step_id"] == "timing"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"active_delay": 60, "finished_delay": 600, "idle_delay": 3600,
             "advanced": {"resume_window": 1800, "scan_interval": 10}},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["finished_delay"] == 600 and data["resume_window"] == 1800
    assert [s["name"] for s in data["states"]] == ["running", "washing", "finished"]
    assert data["states"][0]["comparison"] == "greater"
    assert data["states"][1]["threshold"] == 1000.0
    assert data["states"][-1]["comparison"] == "less"


async def test_state_name_validation(hass):
    with _no_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "X", "power_sensor": "sensor.p", "device_type": "custom"},
        )
        for names, error in [(["only"], "min_two_states"),
                             (["a", "A"], "duplicate_states"),
                             (["a", "idle"], "reserved_name")]:
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"state_names": names}
            )
            assert result["step_id"] == "state_names"
            assert result["errors"] == {"state_names": error}


async def test_same_sensor_cannot_be_added_twice(hass):
    MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=f"{DOMAIN}_sensor.plug_power").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Again", "power_sensor": "sensor.plug_power", "device_type": "custom"},
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_options_menu_timing_shortcut(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    with _no_setup():
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.MENU
        assert set(result["menu_options"]) == {"timing", "state_names"}

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "timing"}
        )
        assert result["step_id"] == "timing"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"active_delay": 60, "finished_delay": 600, "idle_delay": 3600,
             "advanced": {"resume_window": 1800, "scan_interval": 10}},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["finished_delay"] == 600
    assert entry.options["states"] == STATES  # untouched by the shortcut


async def test_options_edit_states_keeps_thresholds_of_renamed_state(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    with _no_setup():
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "state_names"}
        )
        assert result["data_schema"]({}) == {"state_names": ["running", "finished"]}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"state_names": ["working", "done"]}
        )
        for _ in range(2):
            assert result["step_id"] == "state"
            # defaults of the form are the renamed state's old values
            defaults = result["data_schema"]({})
            assert defaults["threshold"] == 5.0
            result = await hass.config_entries.options.async_configure(result["flow_id"], defaults)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"active_delay": 60, "finished_delay": 60, "idle_delay": 60,
             "advanced": {"resume_window": 0, "scan_interval": 10}},
        )
    assert [s["name"] for s in entry.options["states"]] == ["working", "done"]


async def test_every_form_can_be_serialized_for_the_frontend(hass):
    """The UI turns each schema into JSON; a selector it cannot serialize breaks the screen."""
    from homeassistant.helpers import config_validation as cv

    try:  # Home Assistant 2026.x
        import probatio

        def render(result):
            return probatio.to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    except ImportError:  # older Home Assistant
        import voluptuous_serialize

        def render(result):
            return voluptuous_serialize.convert(result["data_schema"], custom_serializer=cv.custom_serializer)

    with _no_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert render(result)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "X", "power_sensor": "sensor.p", "device_type": "washing_machine"},
        )
        assert render(result)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"state_names": ["a", "b", "c", "d"]}
        )
        for _ in range(4):
            schema = render(result)  # start/finish have no comparison, middle states do
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], result["data_schema"]({})
            )
        timing = render(result)
        assert any(f["name"] == "advanced" and f["type"] == "expandable" for f in timing)


async def test_reconfigure_changes_name_and_sensor(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=f"{DOMAIN}_sensor.plug_power")
    entry.add_to_hass(hass)
    with _no_setup():
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Dishwasher 2", "power_sensor": "sensor.other_plug"}
        )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert entry.data["power_sensor"] == "sensor.other_plug" and entry.title == "Dishwasher 2"
    assert entry.data["states"] == STATES  # states and timings untouched
