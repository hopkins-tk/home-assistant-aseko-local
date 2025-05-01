"""Example integration using DataUpdateCoordinator."""

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .aseko_data import AsekoData, AsekoDevice

_LOGGER = logging.getLogger(__name__)


class AsekoLocalDataUpdateCoordinator(DataUpdateCoordinator[AsekoData]):
    """Aseko Local coordinator."""

    data: AsekoData | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        cb_new_device: Callable[[AsekoDevice], None] | None = None,
    ) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.host = config_entry.data[CONF_HOST]
        self.port = config_entry.data[CONF_PORT]
        self.cb_new_device = cb_new_device

        # Initialise DataUpdateCoordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{HOMEASSISTANT_DOMAIN} ({config_entry.unique_id})",
        )

    def devices_update_callback(self, device: AsekoDevice) -> None:
        """Receive callback from api with device update."""

        new_data: AsekoData = AsekoData() if self.data is None else self.data
        if device.serial_number is not None:
            is_new_device = new_data.get(device.serial_number) is None
            new_data.set(device.serial_number, device)

        self.async_set_updated_data(new_data)

        if is_new_device:
            _LOGGER.info("New Aseko unit discovered: %s", device.serial_number)
            if self.cb_new_device is not None:
                # Call the callback function with the new unit data
                self.cb_new_device(device)

    def get_device(self, serial_number: int) -> AsekoDevice | None:
        """Return unit by serial number."""

        return self.data.get(serial_number) if self.data is not None else None

    def get_devices(self) -> list[AsekoDevice]:
        """Return units."""

        return self.data.get_all() or [] if self.data is not None else []
