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
    CONF_PROXY_HOST,
    CONF_PROXY_PORT,
    CONF_PROXY_ENABLED,
    CONF_ENABLE_RAW_LOGGING,
    DEFAULT_LOG_DIR,
)
from .logging_helper import LoggingHelper

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

# Hier speichern wir unsere Helper-Instanz, um sie bei unload zu schließen
_LOG_HELPERS: dict[str, LoggingHelper] = {}  # was ist mit diesen?
_MIRRORS: dict[str, AsekoCloudMirror] = {}
_SERVERS: dict[str, AsekoDeviceServer] = {}

# Typisiertes runtime_data, damit sensor.py darauf zugreifen kann
type AsekoLocalConfigEntry = ConfigEntry["AsekoLocalRuntimeData"]

@dataclass
class AsekoLocalRuntimeData:
    coordinator: AsekoLocalDataUpdateCoordinator
    device_discovered: bool = False
    mirror: AsekoCloudMirror | None = None
    server: AsekoDeviceServer | None = None

async def async_setup_entry(hass: HomeAssistant, config_entry: AsekoLocalConfigEntry) -> bool:
    """Set up Aseko Local from a config entry."""
    
    def _snapshot_ready(dev: AsekoDevice) -> bool:
        # wait until the device has a serial number and a valid device type available
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
        

    coordinator = AsekoLocalDataUpdateCoordinator(hass, config_entry, new_device_callback)

    config_entry.runtime_data = AsekoLocalRuntimeData(
        coordinator=coordinator,
        device_discovered=False,
        mirror=None,
        server=None,
    )   
    log_dir_path = Path(hass.config.path(DEFAULT_LOG_DIR))
    log_helper = LoggingHelper(log_dir=str(log_dir_path), raw_log_enabled=config_entry.options.get(CONF_ENABLE_RAW_LOGGING, False))

    # Optional: Raw-Sink (einzeiliges Append ins File, analog früher)
    raw_sink = None
    if config_entry.options.get(CONF_ENABLE_RAW_LOGGING, False):

        async def _raw_logger(frame_bytes: bytes) -> None:
            try:
                log_helper.log_raw_packet("__init__", frame_bytes)
            except Exception as e:
                _LOGGER.warning("Failed to write raw frame: %s", e)

        raw_sink = _raw_logger
        _LOGGER.info("Raw frame logging enabled; writing to %s", log_dir_path)

    # start Server
    server = await AsekoDeviceServer.create(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
        on_data=coordinator.devices_update_callback,
        raw_sink=raw_sink,
        log_helper=log_helper,  # <-- Integration in AsekoDeviceServer (falls unterstützt)
    )

    if not server.running:
        raise ConfigEntryNotReady

    # Optional: Cloud Mirror Forwarder (Proxy/Aseko Cloud)
    mirror_instance = None
    if config_entry.options.get(CONF_PROXY_ENABLED):
        proxy_host = config_entry.options.get(CONF_PROXY_HOST)
        proxy_port = config_entry.options.get(CONF_PROXY_PORT)
        if proxy_host and proxy_port:
            mirror_instance = AsekoCloudMirror(
                cloud_host=proxy_host,
                cloud_port=int(proxy_port),
                log_helper=log_helper,
                logger=_LOGGER,
            )
            await mirror_instance.start()
            server.set_forward_callback(mirror_instance.enqueue)
            _LOGGER.info("Cloud proxy forwarding enabled to %s:%s", proxy_host, proxy_port)
        else:
            _LOGGER.warning("Proxy enabled but host/port not set — skipping mirror.")

    # Add to runtime_data
    rd = config_entry.runtime_data
    rd.server = server
    rd.mirror = mirror_instance
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Aseko Local config entry."""
    _LOGGER.info("Unloading Aseko Local entry %s", entry.entry_id)

    unload_ok = True

    # Plattformen nur entladen, wenn sie überhaupt geladen wurden
    if getattr(entry, "runtime_data", None) and entry.runtime_data.device_discovered:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Server stoppen
        if getattr(entry, "runtime_data", None):
            if entry.runtime_data.server:
                await entry.runtime_data.server.stop()
            if entry.runtime_data.mirror:
                await entry.runtime_data.mirror.stop()

        # LoggingHelper schließen
        log_helper = _LOG_HELPERS.pop(entry.entry_id, None)
        if log_helper:
            log_helper.close()

        # Domain-Daten aufräumen
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
