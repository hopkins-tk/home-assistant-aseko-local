"""The Websocket Callback Example integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .aseko_data import AsekoUnitData
from .aseko_server import AsekoUnitServer
from .coordinator import AsekoLocalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type AsekoLocalConfigEntry = ConfigEntry[AsekoLocalRuntimeData]


@dataclass
class AsekoLocalRuntimeData:
    """Class to hold your data."""

    coordinator: AsekoLocalDataUpdateCoordinator
    api: AsekoUnitServer
    cancel_update_listener: Callable


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
) -> bool:
    """Set up Aseko Local from a config entry."""

    def new_unit(unit_data: AsekoUnitData):
        """Register new unit."""

        hass.loop.create_task(
            hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
        )

        _LOGGER.info("New Aseko unit registered: %s", unit_data.serial_number)

    # Initialise the coordinator that manages data updates from your api.
    # This is defined in coordinator.py
    coordinator = AsekoLocalDataUpdateCoordinator(hass, config_entry, new_unit)

    api = await AsekoUnitServer.create(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
        on_data=coordinator.devices_update_callback,
    )

    #    units = coordinator.get_units()
    #   units = config_entry.runtime_data.api.data.get_all()
    #    if units:
    #        await register_sensors(config_entry, async_add_entities, units)

    # Perform an initial data load from api.
    # async_config_entry_first_refresh() is special in that it does not log errors if it fails
    #    await coordinator.async_config_entry_first_refresh()

    # Test to see if api initialised correctly, else raise ConfigNotReady to make HA retry setup
    #    if not coordinator.api.running:
    #        raise ConfigEntryNotReady

    # Initialise a listener for config flow options changes.
    # This will be removed automatically if the integraiton is unloaded.
    # See config_flow for defining an options setting that shows up as configure
    # on the integration.
    # If you do not want any config flow options, no need to have listener.
    cancel_update_listener = config_entry.async_on_unload(
        config_entry.add_update_listener(_async_update_listener)
    )

    # Add the coordinator and update listener to config runtime data to make
    # accessible throughout your integration
    config_entry.runtime_data = AsekoLocalRuntimeData(
        coordinator, api, cancel_update_listener
    )

    # Setup platforms (based on the list of entity types in PLATFORMS defined above)
    # This calls the async_setup method in each of your entity type files.
    #    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Return true to denote a successful setup.
    return True


async def _async_update_listener(hass: HomeAssistant, config_entry):
    """Handle config options update."""
    # Reload the integration when the options change.
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
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
    #    if unloaded:
    #        hass.data[DOMAIN]["entities"].pop(config_entry.entry_id, None)
    #        hass.data[DOMAIN]["devices"].pop(config_entry.entry_id, None)

    await AsekoUnitServer.remove(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
    )

    return True
