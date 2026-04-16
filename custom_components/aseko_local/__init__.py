"""The Aseko Local integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady

from .aseko_data import AsekoDevice
from .aseko_server import AsekoDeviceServer
from .consumption_tracker import PUMP_KEYS
from .coordinator import AsekoLocalDataUpdateCoordinator
from dataclasses import dataclass

from .mirror_forwarder import AsekoCloudMirror


from .const import (
    DOMAIN,
    CONF_FORWARDER_HOST,
    CONF_FORWARDER_ENABLED,
    DEFAULT_FORWARDER_PORT_V7,
    DEFAULT_FORWARDER_PORT_V8,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

_MIRRORS: dict[str, AsekoCloudMirror] = {}
_SERVERS: dict[str, AsekoDeviceServer] = {}

SERVICE_RESET_CONSUMPTION = "reset_consumption"

RESET_CONSUMPTION_SCHEMA = vol.Schema(
    {
        vol.Optional("pump", default="all"): vol.In(list(PUMP_KEYS) + ["all"]),
        vol.Optional("counter", default="canister"): vol.In(
            ["canister", "total", "all"]
        ),
    }
)

type AsekoLocalConfigEntry = ConfigEntry["AsekoLocalRuntimeData"]


@dataclass
class AsekoLocalRuntimeData:
    coordinator: AsekoLocalDataUpdateCoordinator
    device_discovered: bool = False
    mirror: AsekoCloudMirror | None = None
    mirror_v8: AsekoCloudMirror | None = None
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
        mirror_v8=None,
        server=None,
    )

    # Raw-Sink: caches the last frame per device for diagnostics
    raw_sink = coordinator.store_raw_frame

    # start Server
    server = await AsekoDeviceServer.create(
        host=config_entry.data[CONF_HOST],
        port=config_entry.data[CONF_PORT],
        on_data=coordinator.devices_update_callback,
        raw_sink=raw_sink,
        v8_raw_sink=coordinator.store_v8_frame,
    )

    if not server.running:
        raise ConfigEntryNotReady

    coordinator.async_start_stale_check()

    # Optional: Cloud Mirror Forwarder to Aseko Cloud
    mirror_instance = None
    mirror_v8_instance = None
    if config_entry.options.get(CONF_FORWARDER_ENABLED):
        forwarder_host = config_entry.options.get(CONF_FORWARDER_HOST)
        if forwarder_host:
            mirror_instance = AsekoCloudMirror(
                cloud_host=forwarder_host, cloud_port=DEFAULT_FORWARDER_PORT_V7
            )
            await mirror_instance.start()
            server.set_forward_callback(mirror_instance.enqueue)

            mirror_v8_instance = AsekoCloudMirror(
                cloud_host=forwarder_host, cloud_port=DEFAULT_FORWARDER_PORT_V8
            )
            await mirror_v8_instance.start()
            server.set_forward_v8_callback(mirror_v8_instance.enqueue)

            _LOGGER.info(
                "Cloud forwarding enabled to %s (v7:%d, v8:%d)",
                forwarder_host,
                DEFAULT_FORWARDER_PORT_V7,
                DEFAULT_FORWARDER_PORT_V8,
            )
        else:
            _LOGGER.warning("Forwarder enabled but host not set — skipping mirror.")

    # Add to runtime_data
    rd = config_entry.runtime_data
    rd.server = server
    rd.mirror = mirror_instance
    rd.mirror_v8 = mirror_v8_instance

    # Register domain service once (shared across all config entries)
    if not hass.services.has_service(DOMAIN, SERVICE_RESET_CONSUMPTION):

        async def handle_reset_consumption(call: ServiceCall) -> None:
            pump = call.data.get("pump", "all")
            counter = call.data.get("counter", "canister")
            for entry in hass.config_entries.async_entries(DOMAIN):
                rd = getattr(entry, "runtime_data", None)
                if rd:
                    rd.coordinator.reset_consumption(pump, counter)

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_CONSUMPTION,
            handle_reset_consumption,
            schema=RESET_CONSUMPTION_SCHEMA,
        )
        _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_RESET_CONSUMPTION)

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
            entry.runtime_data.coordinator.async_stop_stale_check()
            if entry.runtime_data.server:
                await entry.runtime_data.server.stop()
            if entry.runtime_data.mirror:
                await entry.runtime_data.mirror.stop()
            if entry.runtime_data.mirror_v8:
                await entry.runtime_data.mirror_v8.stop()

        # Remove domain service when the last entry is unloaded
        remaining = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]
        if not remaining and hass.services.has_service(
            DOMAIN, SERVICE_RESET_CONSUMPTION
        ):
            hass.services.async_remove(DOMAIN, SERVICE_RESET_CONSUMPTION)
            _LOGGER.debug(
                "Unregistered service %s.%s", DOMAIN, SERVICE_RESET_CONSUMPTION
            )

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
