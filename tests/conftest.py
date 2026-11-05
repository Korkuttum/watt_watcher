"""Pytest setup for the Home Assistant based tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import custom_components.watt_watcher  # noqa: E402,F401  (importable for patching)

# The offline state-machine script stubs Home Assistant modules at import time,
# so it must never be collected next to the real-Home-Assistant tests.
collect_ignore = ["test_state_machine.py"]

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/watt_watcher."""
    yield
