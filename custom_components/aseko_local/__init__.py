"""The Aseko Local integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry

from .aseko_data import AsekoDevice
from .aseko_server import AsekoDeviceServer
from .coordinator import AsekoLocalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type AsekoLocalConfigEntry = ConfigEntry[AsekoLocalRuntimeData]


@dataclass
class AsekoLocalRuntimeData:
    """Class to hold your data."""

    coordinator: AsekoLocalDataUpdateCoordinator
    device_discovered: bool = False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
) -> bool:
    """Set up Aseko Local from a config entry."""

    async def new_device_callback(device: AsekoDevice) -> None:
        """Register new unit."""
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

        config_entry.runtime_data.device_discovered = True

        _LOGGER.info("New Aseko device registered: %s", device.serial_number)

    # Initialise the coordinator that manages data updates from your api.
    # This is defined in coordinator.py
    coordinator = AsekoLocalDataUpdateCoordinator(
        hass, config_entry, new_device_callback
    )

    api = await AsekoDeviceServer.create(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
        on_data=coordinator.devices_update_callback,
    )

    if not api.running:
        raise ConfigEntryNotReady

    config_entry.runtime_data = AsekoLocalRuntimeData(coordinator)

    # Return true to denote a successful setup.
    # async_forward_entry_setups will be called once first data are received to add sensors for the discovered devices.
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Delete device if selected from UI."""

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> bool:
    """Unload a config entry."""
    # This is called when you remove your integration or shutdown HA.
    # If you have created any custom services, they need to be removed here too.

    # Stop & remove the server
    await AsekoDeviceServer.remove(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
    )

    # Unload platforms and return result
    if config_entry.runtime_data.device_discovered:
        return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    return True
