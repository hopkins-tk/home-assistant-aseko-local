"""Test Aseko Local setup process."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aseko_local import (
    AsekoLocalDataUpdateCoordinator,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.aseko_local.aseko_data import AsekoDevice, AsekoDeviceType
from custom_components.aseko_local.const import (
    DOMAIN,
)

from .const import MOCK_CONFIG


# We can pass fixtures as defined in conftest.py to tell pytest to use the fixture
# for a given test. We can also leverage fixtures and mocks that are available in
# Home Assistant using the pytest_homeassistant_custom_component plugin.
# Assertions allow you to verify that the return value of whatever is on the left
# side of the assertion matches with the right side.
async def test_setup_unload_entry(hass, bypass_get_data, api_server_running) -> None:
    """Test entry setup and unload."""

    # Create a mock entry so we don't have to go through config flow
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="test", state=ConfigEntryState.LOADED
    )
    test_device = AsekoDevice(type=AsekoDeviceType.SALT, serial_number=1234567890)

    # Set up the entry and assert that the values set during setup are where we expect
    # them to be. Because we have patched the AsekoLocalDataUpdateCoordinator.async_get_data
    # call, no code from custom_components/aseko_local/aseko_server.py actually runs.
    assert await async_setup_entry(hass, config_entry)
    assert isinstance(
        config_entry.runtime_data.coordinator, AsekoLocalDataUpdateCoordinator
    )
    if config_entry.runtime_data.coordinator and config_entry.runtime_data.coordinator.cb_new_device:
        await config_entry.runtime_data.coordinator.cb_new_device(test_device)
    else:
        pytest.fail("Coordinator or cb_new_device is not initialized")
    assert config_entry.runtime_data.device_discovered
    assert f"{DOMAIN}.sensor" in hass.config.components
    assert f"{DOMAIN}.binary_sensor" in hass.config.components

    # Unload the entry and verify that the data has been removed
    assert await async_unload_entry(hass, config_entry)


async def test_setup_entry_exception(
    hass, bypass_get_data, api_server_not_running
) -> None:
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")

    # In this case we are testing the condition where async_setup_entry raises
    # ConfigEntryNotReady using the `error_on_get_data` fixture which simulates
    # an error.
    with pytest.raises(ConfigEntryNotReady):
        assert await async_setup_entry(hass, config_entry)
