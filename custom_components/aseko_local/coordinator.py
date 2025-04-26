"""Example integration using DataUpdateCoordinator."""

from collections.abc import Callable
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .aseko_data import AsekoData, AsekoUnitData

_LOGGER = logging.getLogger(__name__)


class AsekoLocalDataUpdateCoordinator(DataUpdateCoordinator):
    """Aseko Local coordinator."""

    data: AsekoData | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        cb_new_unit: Callable[[AsekoData], None] | None = None,
    ) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.host = config_entry.data[CONF_HOST]
        self.port = config_entry.data[CONF_PORT]
        self.cb_new_unit = cb_new_unit

        # Initialise DataUpdateCoordinator
        super().__init__(
            hass,
            _LOGGER,
            # update_method=async_update_data,
            name=f"{HOMEASSISTANT_DOMAIN} ({config_entry.unique_id})",
        )

    def devices_update_callback(self, unit_data: AsekoUnitData):
        """Receive callback from api with device update."""

        new_data: AsekoData = AsekoData() if self.data is None else self.data
        new_unit = new_data.get(unit_data.serial_number) is None
        new_data.set(unit_data.serial_number, unit_data)

        self.async_set_updated_data(new_data)

        if new_unit:
            _LOGGER.info("New Aseko unit discovered: %s", unit_data.serial_number)
            if self.cb_new_unit is not None:
                # Call the callback function with the new unit data
                self.cb_new_unit(unit_data)

    # self.async_refresh()


#    def get_unit(self, serial_number: int) -> AsekoUnitData | None:
#        """Return unit by serial number."""
#
#        return self.data.get(serial_number) if self.data is not None else None
#
#    def get_units(self) -> list[AsekoUnitData]:
#        """Return units."""
#
#        return self.data.get_all() if self.data is not None else []
