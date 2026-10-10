"""The Aseko Local integration."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FORWARDER_ENABLED,
    CONF_FORWARDER_HOST,
    DEFAULT_FORWARDER_PORT_V7,
    DEFAULT_FORWARDER_PORT_V8,
    DOMAIN,
    MARK_DUMP_WAIT_TIMEOUT,
)
from .coordinator import (
    AsekoLocalDataUpdateCoordinator,
    BackwashHistoryLoadingError,
)
from .forwarder import AsekoCloudMirror
from .models import AsekoDevice
from .recording.views import async_setup_recording
from .runtime import loaded_entries
from .server import AsekoDeviceServer, ServerConnectionError
from .trackers.consumption import PUMP_KEYS

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATETIME,
    Platform.SENSOR,
]

SERVICE_RESET_CONSUMPTION = "reset_consumption"
SERVICE_SET_LAST_SCHEDULED_BACKWASH = "set_last_scheduled_backwash"
SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH = "clear_last_scheduled_backwash"
SERVICE_MARK_DUMP = "mark_dump"

RESET_CONSUMPTION_SCHEMA = vol.Schema(
    {
        vol.Optional("pump", default="all"): vol.In([*PUMP_KEYS, "all"]),
        vol.Optional("counter", default="canister"): vol.In(
            ["canister", "total", "all"]
        ),
        # without it every unit is reset, as before
        vol.Optional("serial_number"): cv.positive_int,
    }
)

SET_LAST_SCHEDULED_BACKWASH_SCHEMA = vol.Schema(
    {
        vol.Required("timestamp"): cv.datetime,
        vol.Optional("serial_number"): cv.positive_int,
    }
)

CLEAR_LAST_SCHEDULED_BACKWASH_SCHEMA = vol.Schema(
    {
        vol.Optional("serial_number"): cv.positive_int,
    }
)

# a platform set-up that keeps failing is logged at most this often (seconds)
SETUP_ERROR_LOG_INTERVAL = 60

MARK_DUMP_SCHEMA = vol.Schema(
    {
        vol.Optional("note"): vol.All(cv.string, vol.Length(max=200)),
        vol.Optional("wait_for_next_frame", default=True): cv.boolean,
        vol.Optional("serial_number"): cv.positive_int,
    }
)
# One notification, rewritten as a mark_dump call progresses, so the phone
# shows whether the marker is written yet before the setting is changed back.
MARK_DUMP_NOTIFICATION_ID = f"{DOMAIN}_mark_dump"

type AsekoLocalConfigEntry = ConfigEntry["AsekoLocalRuntimeData"]


@dataclass
class AsekoLocalRuntimeData:
    """What one config entry keeps while it runs: coordinator, server, mirrors."""

    coordinator: AsekoLocalDataUpdateCoordinator
    device_discovered: bool = False
    mirror: AsekoCloudMirror | None = None
    mirror_v8: AsekoCloudMirror | None = None
    server: AsekoDeviceServer | None = None


def _mark_dump_message(markers: list[dict], label: str, *, wait: bool) -> str:
    """Say which markers were written and how they relate to the frames."""
    lines = []
    for m in markers:
        when = dt_util.parse_datetime(m["time"])
        clock = when.strftime("%H:%M:%S") if when else m["time"]
        ages = ", ".join(f"{age} s" for age in m["seconds_since_last_frame"].values())
        if wait and m["waited_for_frame"]:
            lines.append(
                f"Marker **{m['marker']}**{label} written at {clock}, right after "
                f"a frame that arrived {m['seconds_after_tap']} s after the tap. "
                "You can change the unit again."
            )
        elif wait:
            lines.append(
                f"No frame within {MARK_DUMP_WAIT_TIMEOUT} s: marker "
                f"**{m['marker']}**{label} written at {clock} without one. Is "
                "the unit still sending?"
            )
        else:
            lines.append(
                f"Marker **{m['marker']}**{label} written at {clock}; last frame "
                f"{ages or 'never'} before."
            )
    return "\n\n".join(lines)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> bool:
    """Set up Aseko Local from a config entry."""

    def _snapshot_ready(dev: AsekoDevice) -> bool:
        # wait until the device has a serial number and a valid device type is available
        base_keys = ("serial_number", "device_type")
        return all(getattr(dev, k, None) is not None for k in base_keys)

    setup_error_logged = [float("-inf")]  # monotonic time of the last error logged

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

        rd.device_discovered = True  # set early to prevent concurrent calls
        try:
            await hass.config_entries.async_forward_entry_setups(
                config_entry, PLATFORMS
            )
        except Exception:
            # The coordinator asks again on the next frame; log at most once a
            # minute so a failure that persists does not flood the log.
            rd.device_discovered = False
            now = time.monotonic()
            if now - setup_error_logged[0] >= SETUP_ERROR_LOG_INTERVAL:
                setup_error_logged[0] = now
                _LOGGER.exception(
                    "Setting up the Aseko Local entities failed; retrying on the "
                    "next frame"
                )
            return
        rd.coordinator.platforms_ready = True
        # Load persisted backwash timestamps for known devices (e.g. after
        # an HA restart, so the sensor shows the last observed value
        # immediately on first frame).
        await rd.coordinator.async_setup_backwash_trackers()
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

    # The frame log survives restarts; load it before frames start arriving
    await coordinator.async_load_frame_log()
    # exact consumption counters, before the sensors restore rounded litres
    await coordinator.async_load_consumption()

    # Raw-Sink: caches the last frame per device for diagnostics
    raw_sink = coordinator.store_raw_frame

    # start Server
    host, port = config_entry.data[CONF_HOST], config_entry.data[CONF_PORT]
    try:
        server = await AsekoDeviceServer.create(
            host=host,
            port=port,
            on_data=coordinator.devices_update_callback,
            raw_sink=raw_sink,
            v8_raw_sink=coordinator.store_v8_frame,
            frame_warning_sink=coordinator.store_frame_warning,
            rejected_sink=coordinator.store_rejected_frame,
        )
    except ServerConnectionError as err:
        # The port may still be held (a restart before the old socket is
        # released, another program): Home Assistant retries the set-up later
        # instead of leaving the entry failed.  The server that did not start
        # is forgotten, so the retry does not inherit this set-up's callbacks.
        await AsekoDeviceServer.remove(host, port)
        msg = f"Cannot listen on {host}:{port}: {err}"
        raise ConfigEntryNotReady(msg) from err

    if not server.running:
        raise ConfigEntryNotReady

    coordinator.async_start_stale_check()

    # The test cases card and its photo / status / export endpoints, once per HA run
    integration = await async_get_integration(hass, DOMAIN)
    await async_setup_recording(hass, str(integration.version))

    # Add to runtime_data
    rd = config_entry.runtime_data
    rd.server = server
    # Optional: Cloud Mirror Forwarder to Aseko Cloud
    rd.mirror, rd.mirror_v8 = await _async_start_mirrors(config_entry, server)

    # domain services, once for all config entries
    _async_register_services(hass)

    return True


async def _async_start_mirrors(
    config_entry: AsekoLocalConfigEntry, server: AsekoDeviceServer
) -> tuple[AsekoCloudMirror | None, AsekoCloudMirror | None]:
    """Start forwarding to Aseko Cloud when the options ask for it (v7, v8)."""
    if not config_entry.options.get(CONF_FORWARDER_ENABLED):
        return None, None
    forwarder_host = config_entry.options.get(CONF_FORWARDER_HOST)
    if not forwarder_host:
        _LOGGER.warning("Forwarder enabled but host not set — skipping mirror.")
        return None, None

    mirror = AsekoCloudMirror(
        cloud_host=forwarder_host, cloud_port=DEFAULT_FORWARDER_PORT_V7
    )
    await mirror.start()
    server.set_forward_callback(mirror.enqueue)

    mirror_v8 = AsekoCloudMirror(
        cloud_host=forwarder_host, cloud_port=DEFAULT_FORWARDER_PORT_V8
    )
    await mirror_v8.start()
    server.set_forward_v8_callback(mirror_v8.enqueue)

    _LOGGER.info(
        "Cloud forwarding enabled to %s (v7:%d, v8:%d)",
        forwarder_host,
        DEFAULT_FORWARDER_PORT_V7,
        DEFAULT_FORWARDER_PORT_V8,
    )
    return mirror, mirror_v8


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain's services once; shared by every config entry."""
    _async_register_consumption_service(hass)
    _async_register_backwash_services(hass)
    _async_register_mark_dump_service(hass)


@callback
def _async_register_consumption_service(hass: HomeAssistant) -> None:
    """``reset_consumption``."""
    if not hass.services.has_service(DOMAIN, SERVICE_RESET_CONSUMPTION):

        async def handle_reset_consumption(call: ServiceCall) -> None:
            pump = call.data.get("pump", "all")
            counter = call.data.get("counter", "canister")
            serial_number = call.data.get("serial_number")
            for entry in loaded_entries(hass):
                entry.runtime_data.coordinator.reset_consumption(
                    pump, counter, serial_number
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_CONSUMPTION,
            handle_reset_consumption,
            schema=RESET_CONSUMPTION_SCHEMA,
        )
        _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_RESET_CONSUMPTION)


@callback
def _check_backwash_history_ready(hass: HomeAssistant, serial: int | None) -> None:
    """Raise unless every entry's matching unit has its stored history in.

    Asked once, before the first entry is written: each coordinator refuses
    its own half-done change, but a service walks every loaded entry, so
    without this a ready entry could be changed and a later one then refuse
    the whole call.
    """
    loading = [
        serial_number
        for entry in loaded_entries(hass)
        for serial_number in entry.runtime_data.coordinator.loading_backwash_serials(
            serial
        )
    ]
    if loading:
        raise BackwashHistoryLoadingError(loading)


@callback
def _async_register_backwash_services(hass: HomeAssistant) -> None:
    """``set_last_scheduled_backwash`` and ``clear_last_scheduled_backwash``."""
    if not hass.services.has_service(DOMAIN, SERVICE_SET_LAST_SCHEDULED_BACKWASH):

        async def handle_set_last_scheduled_backwash(call: ServiceCall) -> None:
            """Seed the last scheduled backwash so the projection can start.

            The device never transmits when it last ran a backwash, so without
            this the "next" projection has to wait out a whole interval for the
            first observed cycle.  The seeded value is marked as manual and is
            replaced as soon as a real scheduled cycle is detected.
            """
            timestamp = call.data["timestamp"]
            serial = call.data.get("serial_number")

            # A naive datetime from the service call is in the user's local
            # time; the tracker compares against timezone-aware timestamps.
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

            # judged on the clocks of the units it is written to, before any
            # of them is written
            unit_now = min(
                (
                    now
                    for entry in loaded_entries(hass)
                    if (now := entry.runtime_data.coordinator.unit_clock_now(serial))
                    is not None
                ),
                default=dt_util.now(),
            )
            if timestamp > unit_now:
                msg = (
                    f"{timestamp.isoformat()} is in the future; "
                    "the last scheduled backwash must already have happened"
                )
                raise ServiceValidationError(msg)

            _check_backwash_history_ready(hass, serial)

            matched = False
            for entry in loaded_entries(hass):
                coordinator = entry.runtime_data.coordinator
                if coordinator.set_last_scheduled_backwash(timestamp, serial):
                    matched = True

            if not matched:
                raise ServiceValidationError(
                    f"No Aseko device with a backwash valve has serial_number {serial}"
                    if serial is not None
                    else "No Aseko device with a backwash valve has been seen yet"
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_LAST_SCHEDULED_BACKWASH,
            handle_set_last_scheduled_backwash,
            schema=SET_LAST_SCHEDULED_BACKWASH_SCHEMA,
        )
        _LOGGER.debug(
            "Registered service %s.%s", DOMAIN, SERVICE_SET_LAST_SCHEDULED_BACKWASH
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH):

        async def handle_clear_last_scheduled_backwash(call: ServiceCall) -> None:
            """Return the last scheduled backwash to unknown.

            The undo for a mistyped date.  Also re-arms the classification of
            an older stored cycle, so if one is on record it is re-derived on
            the next frame.
            """
            serial = call.data.get("serial_number")

            _check_backwash_history_ready(hass, serial)

            matched = False
            for entry in loaded_entries(hass):
                if entry.runtime_data.coordinator.clear_last_scheduled_backwash(serial):
                    matched = True

            if not matched:
                raise ServiceValidationError(
                    f"No Aseko device with a backwash valve has serial_number {serial}"
                    if serial is not None
                    else "No Aseko device with a backwash valve has been seen yet"
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH,
            handle_clear_last_scheduled_backwash,
            schema=CLEAR_LAST_SCHEDULED_BACKWASH_SCHEMA,
        )
        _LOGGER.debug(
            "Registered service %s.%s", DOMAIN, SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH
        )


@callback
def _async_register_mark_dump_service(hass: HomeAssistant) -> None:
    """``mark_dump``: a marker in every recording frame log."""
    if not hass.services.has_service(DOMAIN, SERVICE_MARK_DUMP):

        async def handle_mark_dump(call: ServiceCall) -> ServiceResponse:
            """Write a numbered, timestamped marker into every frame log.

            Tap it, then photograph the unit's display: in the diagnostics
            download the marker sits between the frames received before and
            after, so frames and photos line up without comparing clocks.
            """
            note = call.data.get("note")
            wait = call.data.get("wait_for_next_frame", True)
            serial_number = call.data.get("serial_number")
            loaded = loaded_entries(hass)
            if not loaded:
                msg = "No Aseko Local entry is loaded"
                raise ServiceValidationError(msg)
            loaded = [e for e in loaded if e.runtime_data.coordinator.frame_log.enabled]
            if not loaded:
                msg = "Recording is off: turn it on in the Aseko test cases card first"
                raise ServiceValidationError(msg)
            if serial_number is not None:
                loaded = [
                    e
                    for e in loaded
                    if e.runtime_data.coordinator.knows_serial(serial_number)
                ]
                if not loaded:
                    msg = (
                        f"No recording entry has received a frame from {serial_number}"
                    )
                    raise ServiceValidationError(msg)

            tapped = dt_util.utcnow()
            label = f" ({note})" if note else ""
            if wait:
                persistent_notification.async_create(
                    hass,
                    f"Waiting for the next frame{label}, at most "
                    f"{MARK_DUMP_WAIT_TIMEOUT} s. The marker is **not written "
                    "yet** -- leave the unit as it is.",
                    title="Aseko mark: waiting for a frame",
                    notification_id=MARK_DUMP_NOTIFICATION_ID,
                )

            generations = {
                e.entry_id: e.runtime_data.coordinator.recording_generation
                for e in loaded
            }

            async def mark(entry: ConfigEntry) -> dict | None:
                marker = await entry.runtime_data.coordinator.async_mark_after_frame(
                    note,
                    {},
                    wait=wait,
                    serial_number=serial_number,
                    generation=generations[entry.entry_id],
                )
                if marker is None:
                    return None  # stopped or deleted while waiting
                return {
                    "entry": entry.title,
                    "marker": marker["marker"],
                    "time": dt_util.as_local(marker["time"]).isoformat(),
                    "seconds_since_last_frame": marker["seconds_since_last_frame"],
                    "waited_for_frame": marker["waited_for_frame"],
                    "seconds_after_tap": round(
                        (marker["time"] - tapped).total_seconds(), 1
                    ),
                }

            results = await asyncio.gather(*(mark(entry) for entry in loaded))
            markers = [m for m in results if m is not None]
            if not markers:
                persistent_notification.async_dismiss(hass, MARK_DUMP_NOTIFICATION_ID)
                msg = "Recording was stopped or deleted while waiting; no marker was written"
                raise ServiceValidationError(msg)
            persistent_notification.async_create(
                hass,
                _mark_dump_message(markers, label, wait=wait),
                title=(
                    "Aseko mark: no frame arrived"
                    if wait and not all(m["waited_for_frame"] for m in markers)
                    else "Aseko mark: written"
                ),
                notification_id=MARK_DUMP_NOTIFICATION_ID,
            )
            return {"markers": markers}

        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_DUMP,
            handle_mark_dump,
            schema=MARK_DUMP_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_MARK_DUMP)


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
            await entry.runtime_data.coordinator.async_save_frame_log()
            await entry.runtime_data.coordinator.async_save_consumption()
            if entry.runtime_data.server:
                # Remove, not just stop: a stopped server left in the registry
                # would be handed back to the next setup without listening.
                await AsekoDeviceServer.remove(
                    entry.runtime_data.server.host, entry.runtime_data.server.port
                )
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
        if not remaining:
            for service in (
                SERVICE_RESET_CONSUMPTION,
                SERVICE_SET_LAST_SCHEDULED_BACKWASH,
                SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH,
                SERVICE_MARK_DUMP,
            ):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
                    _LOGGER.debug("Unregistered service %s.%s", DOMAIN, service)

    return unload_ok
