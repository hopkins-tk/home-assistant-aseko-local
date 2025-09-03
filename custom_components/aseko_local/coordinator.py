# custom_components/aseko_local/coordinator.py

import logging
from collections.abc import Callable
from types import CoroutineType
from typing import Any
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util  # ← for timestamps

from .aseko_data import AsekoData, AsekoDevice

_LOGGER = logging.getLogger(__name__)


class AsekoLocalDataUpdateCoordinator(DataUpdateCoordinator[AsekoData]):
    """Aseko Local coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        cb_new_device: Callable[[AsekoDevice], CoroutineType[Any, Any, None]] | None = None,
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

    def devices_update_callback(self, device: AsekoDevice) -> None:
        """Receive callback with device update."""

        _LOGGER.debug("📡 devices_update_callback CALLED with device=%s (serial=%s)",
                      device, getattr(device, "serial_number", None))

        new_data: AsekoData = AsekoData() if self.data is None else self.data

        existing_serials = [d.serial_number for d in (new_data.get_all() or [])]
        _LOGGER.debug("🔎 Before update: known serials=%s", existing_serials)

        is_new_device = False

        if device.serial_number is not None:
            is_new_device = new_data.get(device.serial_number) is None
            _LOGGER.debug("➡️ Device %s is_new_device=%s", device.serial_number, is_new_device)

            new_data.set(device.serial_number, device)

            _LOGGER.debug("✅ Stored device %s → known serials now: %s",
                          device.serial_number, list(new_data.devices.keys()))
        else:
            _LOGGER.warning("❌ Received device without serial_number, not stored!")
            return  # abort, nothing to propagate

        # Use device timestamp if available (converted to UTC), else fallback to utcnow
        now = dt_util.as_utc(device.timestamp) if getattr(device, "timestamp", None) else dt_util.utcnow()

        devices = new_data.get_all() or []
        _LOGGER.debug("📊 Currently %s devices in new_data", len(devices))

        _LOGGER.debug("⚠️ Calling async_set_updated_data() with %s devices", len(devices))
        self.async_set_updated_data(new_data)

        if is_new_device:
            _LOGGER.debug("🆕 NEW DEVICE DISCOVERED: %s", device.serial_number)
            if self.cb_new_device is not None:
                self.hass.loop.create_task(self.cb_new_device(device))

    def get_device(self, serial_number: int) -> AsekoDevice | None:
        _LOGGER.debug("get_device(%s) called", serial_number)
        return self.data.get(serial_number) if self.data is not None else None

    def get_devices(self) -> list[AsekoDevice]:
        devices = self.data.get_all() or [] if self.data is not None else []
        _LOGGER.debug("get_devices() → %s devices: %s",
                      len(devices), [d.serial_number for d in devices])
        return devices
