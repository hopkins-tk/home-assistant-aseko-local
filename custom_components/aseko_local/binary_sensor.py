"""Interfaces with the Aseko Local binary sensors."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AsekoLocalConfigEntry
from .aseko_data import AsekoDevice
from .entity import AsekoLocalEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AsekoLocalBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Aseko device binary sensor entity."""

    value_fn: Callable[[AsekoDevice], bool | None]


BINARY_SENSORS: tuple[AsekoLocalBinarySensorEntityDescription, ...] = (
    AsekoLocalBinarySensorEntityDescription(
        key="water_flow_to_probes",
        translation_key="water_flow_to_probes",
        icon="mdi:waves-arrow-right",
        value_fn=lambda device: device.water_flow_to_probes,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="electrolyzer_active",
        translation_key="electrolyzer_active",
        icon="mdi:lightning-bolt",
        value_fn=lambda device: device.electrolyzer_active,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="pump_running",
        translation_key="pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.pump_running,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aseko device binary sensors."""

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices()
    async_add_entities(
        AsekoLocalBinarySensorEntity(device, coordinator, description)
        for description in BINARY_SENSORS
        for device in devices
        if description.value_fn(device) is not None
    )


class AsekoLocalBinarySensorEntity(AsekoLocalEntity, BinarySensorEntity):
    """Representation of an Aseko device binary sensor entity."""

    entity_description: AsekoLocalBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.device)
