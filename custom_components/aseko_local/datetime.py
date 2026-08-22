"""Aseko Local writable datetime entities.

Holds the one backwash value the device cannot tell us: when its last
*scheduled* cycle ran.  Until that is known the "next scheduled backwash"
projection has nothing to count from, and waiting for the integration to
observe a cycle can take a whole interval.

Making it a ``datetime`` entity rather than a read-only sensor means the value
is set the obvious way — click it, pick a date in the dialog, done — with no
helper or script in between.  ``aseko_local.set_last_scheduled_backwash``
remains available for automations.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity, DateTimeEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import AsekoLocalConfigEntry
from .aseko_data import AsekoDevice
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import AsekoLocalEntity

_LOGGER = logging.getLogger(__name__)

LAST_SCHEDULED_BACKWASH = DateTimeEntityDescription(
    key="last_scheduled_backwash",
    translation_key="last_scheduled_backwash",
    icon="mdi:calendar-check",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the writable backwash datetime entities."""

    coordinator = config_entry.runtime_data.coordinator
    async_add_entities(_build_entities(coordinator.get_devices(), coordinator))

    @callback
    def _async_add_new_device(device: AsekoDevice) -> None:
        new_entities = _build_entities([device], coordinator)
        if new_entities:
            async_add_entities(new_entities)

    config_entry.async_on_unload(
        coordinator.async_add_new_device_listener(_async_add_new_device)
    )


def _build_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
) -> list[DateTimeEntity]:
    """Create one entity per device that has a backwash valve.

    ``backwash_active`` is the decoder's presence marker for that output: it is
    left as None on device types without one (NET).  See Issue #129.
    """
    return [
        AsekoLastScheduledBackwashEntity(device, coordinator, LAST_SCHEDULED_BACKWASH)
        for device in devices
        if device.backwash_active is not None
    ]


class AsekoLastScheduledBackwashEntity(AsekoLocalEntity, DateTimeEntity):
    """When the unit last ran its scheduled backwash — observed or entered."""

    entity_description: DateTimeEntityDescription

    @property
    def native_value(self) -> datetime | None:
        """Return the stored timestamp, or None while nothing is known."""
        return self.device.last_scheduled_backwash

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Publish whether this was observed or entered by hand.

        Omitted while the value is unknown — an attribute describing where a
        non-existent value came from is just noise.
        """
        source = self.device.last_scheduled_backwash_source
        if source is None:
            return None
        return {"source": source.value}

    async def async_set_value(self, value: datetime) -> None:
        """Record a user-supplied timestamp and re-project the next cycle."""
        if value > dt_util.now():
            raise ServiceValidationError(
                f"{value.isoformat()} is in the future; "
                "the last scheduled backwash must already have happened"
            )
        self.coordinator.set_last_scheduled_backwash(value, self.device.serial_number)
