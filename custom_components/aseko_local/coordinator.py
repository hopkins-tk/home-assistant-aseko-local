# custom_components/aseko_local/coordinator.py

import logging
from collections.abc import Callable
from datetime import timedelta
from types import CoroutineType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .aseko_data import AsekoData, AsekoDevice
from .consumption_tracker import AsekoConsumptionTracker

_LOGGER = logging.getLogger(__name__)


class AsekoLocalDataUpdateCoordinator(DataUpdateCoordinator[AsekoData]):
    """Aseko Local coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        cb_new_device: Callable[[AsekoDevice], CoroutineType[Any, Any, None]]
        | None = None,
    ) -> None:
        """Initialize coordinator."""
        self.host = config_entry.data[CONF_HOST]
        self.port = config_entry.data[CONF_PORT]
        self.cb_new_device = cb_new_device
        self.hass = hass

        super().__init__(
            hass,
            _LOGGER,
            name=f"{HOMEASSISTANT_DOMAIN} ({config_entry.unique_id})",
        )
        # One tracker per device serial number
        self._trackers: dict[int, AsekoConsumptionTracker] = {}
        # Last raw frame per device serial number (for diagnostics)
        self._last_raw_frames: dict[int, bytes] = {}
        # Last partial (incomplete) raw frame per serial number
        self._last_partial_frames: dict[int, bytes] = {}
        # Last raw v8 text frame per device serial number (for diagnostics)
        self._last_v8_frames: dict[int, bytes] = {}
        # Unsubscribe handle for the periodic stale-check
        self._stale_check_unsub: Callable[[], None] | None = None
        # Per-platform listeners called whenever a brand-new device is discovered
        self._new_device_listeners: list[Callable[[AsekoDevice], None]] = []

    def devices_update_callback(self, device: AsekoDevice) -> None:
        """Receive callback with device update."""

        # Check if device_type is valid
        if getattr(device, "device_type", None) is None:
            _LOGGER.warning(
                "❌ Received device with unknown type, not stored! serial=%s",
                getattr(device, "serial_number", None),
            )
            return

        _LOGGER.debug(
            "📡 devices_update_callback CALLED with device=%s (serial=%s)",
            device,
            getattr(device, "serial_number", None),
        )

        new_data: AsekoData = AsekoData() if self.data is None else self.data

        existing_serials = [d.serial_number for d in (new_data.get_all() or [])]
        _LOGGER.debug("🔎 Before update: known serials=%s", existing_serials)

        is_new_device = False

        if device.serial_number is not None:
            is_new_device = new_data.get(device.serial_number) is None
            _LOGGER.debug(
                "➡️ Device %s is_new_device=%s", device.serial_number, is_new_device
            )

            new_data.set(device.serial_number, device)

            # Stamp server-side receive time (independent of device clock)
            stored = new_data.get(device.serial_number)
            if stored is not None:
                stored.last_seen = dt_util.now()

            # Update consumption tracker for this device
            if device.serial_number not in self._trackers:
                self._trackers[device.serial_number] = AsekoConsumptionTracker()
            self._trackers[device.serial_number].update(device, dt_util.now())

            _LOGGER.debug(
                "✅ Stored device %s → known serials now: %s",
                device.serial_number,
                list(new_data.devices.keys()),
            )
        else:
            _LOGGER.error("❌ Received device without serial_number, not stored!")
            return  # abort, nothing to propagate

        devices = new_data.get_all() or []
        _LOGGER.debug("📊 Currently %s devices in new_data", len(devices))

        _LOGGER.debug(
            "⚠️ Calling async_set_updated_data() with %s devices", len(devices)
        )
        self.async_set_updated_data(new_data)

        if is_new_device:
            _LOGGER.debug("🆕 NEW DEVICE DISCOVERED: %s", device.serial_number)
            if self.cb_new_device is not None:
                self.hass.loop.create_task(self.cb_new_device(device))
            for listener in list(self._new_device_listeners):
                try:
                    listener(device)
                except Exception:
                    _LOGGER.exception(
                        "❌ New-device listener %r failed for device serial=%s",
                        listener,
                        device.serial_number,
                    )

    def async_add_new_device_listener(
        self, listener: Callable[[AsekoDevice], None]
    ) -> Callable[[], None]:
        """Register a callback invoked whenever a brand-new device is discovered.

        Returns an unsubscribe callable that removes the listener.
        Platforms call this in async_setup_entry and pass the result to
        config_entry.async_on_unload() so the listener is removed on unload.
        """
        self._new_device_listeners.append(listener)

        def _unsub() -> None:
            self._new_device_listeners.remove(listener)

        return _unsub

    def store_raw_frame(self, raw_frame: bytes) -> None:
        """Cache the last raw frame, keyed by serial number (bytes 0-3).

        Frames shorter than MESSAGE_SIZE are stored as partial frames so users
        with unknown device variants can share the raw data via the Diagnostics
        download without needing to enable debug logging.
        """
        if len(raw_frame) < 4:
            return
        serial = int.from_bytes(raw_frame[0:4], "big")
        from .const import MESSAGE_SIZE  # noqa: PLC0415

        if len(raw_frame) < MESSAGE_SIZE:
            self._last_partial_frames[serial] = bytes(raw_frame)
        else:
            self._last_raw_frames[serial] = bytes(raw_frame)

    def get_raw_frame(self, serial_number: int) -> bytes | None:
        """Return the last full raw frame for a given device serial number."""
        return self._last_raw_frames.get(serial_number)

    def get_partial_frame(self, serial_number: int) -> bytes | None:
        """Return the last partial (incomplete) raw frame, if any."""
        return self._last_partial_frames.get(serial_number)

    def store_v8_frame(self, raw_frame: bytes) -> None:
        """Cache the last v8 text frame, keyed by the serial number in the frame text."""
        try:
            text = raw_frame.decode("ascii", errors="replace").strip()
            # Frame starts with "{v1 <serial> ..."
            serial = int(text.lstrip("{").split()[1])
            self._last_v8_frames[serial] = bytes(raw_frame)
        except (ValueError, IndexError):
            pass

    def get_v8_frame(self, serial_number: int) -> bytes | None:
        """Return the last raw v8 text frame for a given device serial number."""
        return self._last_v8_frames.get(serial_number)

    def get_tracker(self, serial_number: int) -> AsekoConsumptionTracker | None:
        """Return the consumption tracker for a given device serial number."""
        return self._trackers.get(serial_number)

    def reset_consumption(self, pump_key: str, counter: str) -> None:
        """Reset consumption counters for all tracked devices and notify listeners."""
        for tracker in self._trackers.values():
            tracker.reset(pump_key=pump_key, counter=counter)
        self.async_update_listeners()

    def get_device(self, serial_number: int) -> AsekoDevice | None:
        _LOGGER.debug("get_device(%s) called", serial_number)
        return self.data.get(serial_number) if self.data is not None else None

    def get_devices(self) -> list[AsekoDevice]:
        devices = self.data.get_all() or [] if self.data is not None else []
        _LOGGER.debug(
            "get_devices() → %s devices: %s",
            len(devices),
            [d.serial_number for d in devices],
        )
        return devices

    def async_start_stale_check(self) -> None:
        """Start a periodic task that pushes updates so entities detect offline state."""
        self._stale_check_unsub = async_track_time_interval(
            self.hass,
            self._async_check_stale,
            timedelta(seconds=30),
        )

    @callback
    def _async_check_stale(self, _now: object) -> None:
        """Re-push current data so entities re-evaluate device.online()."""
        if self.data is not None:
            self.async_set_updated_data(self.data)

    def async_stop_stale_check(self) -> None:
        """Stop the periodic stale check."""
        if self._stale_check_unsub is not None:
            self._stale_check_unsub()
            self._stale_check_unsub = None
