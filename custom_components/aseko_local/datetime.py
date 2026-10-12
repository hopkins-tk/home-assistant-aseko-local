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
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AsekoLocalConfigEntry
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import AsekoLocalEntity, async_setup_platform_entities
from .models import AsekoDevice

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
    async_setup_platform_entities(
        hass, config_entry, async_add_entities, Platform.DATETIME, _build_entities
    )


def _build_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
    features: frozenset[str] | None = None,
) -> list[DateTimeEntity]:
    """Create one entity per device that has a backwash valve.

    The decoder lists ``backwash_running`` in ``device.features`` only for
    units with that output (NET has none).  See Issue #129.  With
    ``features`` given, only when the valve is among what the device has
    just started showing.
    """
    if features is not None and "backwash_running" not in features:
        return []
    return [
        AsekoLastScheduledBackwashEntity(device, coordinator, LAST_SCHEDULED_BACKWASH)
        for device in devices
        if "backwash_running" in device.possible_features
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
        unit_now = self.coordinator.unit_clock_now(self.device.serial_number)
        if unit_now is not None and value > unit_now:
            msg = (
                f"{value.isoformat()} is in the future; "
                "the last scheduled backwash must already have happened"
            )
            raise ServiceValidationError(msg)
        self.coordinator.set_last_scheduled_backwash(value, self.device.serial_number)
