"""The Aseko Local integration."""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry as AsekoLocalConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry

from .aseko_data import AsekoDevice
from .aseko_server import AsekoDeviceServer
from .coordinator import AsekoLocalDataUpdateCoordinator
from pathlib import Path
from dataclasses import dataclass

from .mirror_forwarder import AsekoCloudMirror


from .const import (
    DOMAIN,
    CONF_FORWARDER_HOST,
    CONF_FORWARDER_PORT,
    CONF_FORWARDER_ENABLED,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

_MIRRORS: dict[str, AsekoCloudMirror] = {}
_SERVERS: dict[str, AsekoDeviceServer] = {}

type AsekoLocalConfigEntry = ConfigEntry["AsekoLocalRuntimeData"]


@dataclass
class AsekoLocalRuntimeData:
    coordinator: AsekoLocalDataUpdateCoordinator
    device_discovered: bool = False
    mirror: AsekoCloudMirror | None = None
    server: AsekoDeviceServer | None = None


async def async_setup_entry(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> bool:
    """Set up Aseko Local from a config entry."""

    def _snapshot_ready(dev: AsekoDevice) -> bool:
        # wait until the device has a serial number and a valid device type is available
        base_keys = ("serial_number", "device_type")
        return all(getattr(dev, k, None) is not None for k in base_keys)

    async def new_device_callback(device: AsekoDevice) -> None:
        # Protected against early calls before runtime_data is set
        rd = getattr(config_entry, "runtime_data", None)
        if not rd:
            _LOGGER.debug("Callback before runtime_data is ready – skipping.")
            return

        if rd.device_discovered:
            return

        if not _snapshot_ready(device):
            _LOGGER.debug("Deferring platform setup; first snapshot not ready yet.")
            return

        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
        rd.device_discovered = True
        _LOGGER.info("New Aseko device registered: %s", device.serial_number)

    coordinator = AsekoLocalDataUpdateCoordinator(
        hass, config_entry, new_device_callback
    )

    config_entry.runtime_data = AsekoLocalRuntimeData(
        coordinator=coordinator,
        device_discovered=False,
        mirror=None,
        server=None,
    )

    # Optional: Raw-Sink (single line log for appending the log file)
    raw_sink = None

    # start Server
    server = await AsekoDeviceServer.create(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
        on_data=coordinator.devices_update_callback,
        raw_sink=raw_sink,
    )

    if not server.running:
        raise ConfigEntryNotReady

    # Optional: Cloud Mirror Forwarder to Aseko Cloud
    mirror_instance = None
    if config_entry.options.get(CONF_FORWARDER_ENABLED):
        forwarder_host = config_entry.options.get(CONF_FORWARDER_HOST)
        forwarder_port = config_entry.options.get(CONF_FORWARDER_PORT)
        if forwarder_host and forwarder_port:
            mirror_instance = AsekoCloudMirror(
                cloud_host=forwarder_host, cloud_port=int(forwarder_port)
            )
            await mirror_instance.start()
            server.set_forward_callback(mirror_instance.enqueue)
            _LOGGER.info(
                "Cloud forwarding enabled to %s:%s", forwarder_host, forwarder_port
            )
        else:
            _LOGGER.warning(
                "Forwarder enabled but host/port not set — skipping mirror."
            )

    # Add to runtime_data
    rd = config_entry.runtime_data
    rd.server = server
    rd.mirror = mirror_instance

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Aseko Local config entry."""
    _LOGGER.info("Unloading Aseko Local entry %s", entry.entry_id)

    unload_ok = True

    # Unload platforms only if they were actually loaded
    if getattr(entry, "runtime_data", None) and entry.runtime_data.device_discovered:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Stop server and mirror if they exist
        if getattr(entry, "runtime_data", None):
            if entry.runtime_data.server:
                await entry.runtime_data.server.stop()
            if entry.runtime_data.mirror:
                await entry.runtime_data.mirror.stop()

        # Remove runtime_data to avoid stale references
        domain_data = hass.data.get(DOMAIN)
        if domain_data is not None:
            domain_data.pop(entry.entry_id, None)
            if not domain_data:
                hass.data.pop(DOMAIN, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle reload of the entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
