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
    api: AsekoDeviceServer


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
) -> bool:
    """Set up Aseko Local from a config entry."""

    def new_device_callback(device: AsekoDevice) -> None:
        """Register new unit."""

        hass.loop.create_task(
            hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
        )

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

    # Initialise a listener for config flow options changes.
    # This will be removed automatically if the integraiton is unloaded.
    # See config_flow for defining an options setting that shows up as configure
    # on the integration.
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    config_entry.runtime_data = AsekoLocalRuntimeData(coordinator, api)

    # Return true to denote a successful setup.
    # async_forward_entry_setups will be called once first data are received to add sensors for the discovered devices.
    return True


async def async_reload_entry(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> None:
    """Handle config options update."""

    # Reload the integration when the options change.
    await hass.config_entries.async_reload(config_entry.entry_id)


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

    # Unload platforms and return result
    await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    # Stop & remove the server
    await AsekoDeviceServer.remove(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
    )

    return True
