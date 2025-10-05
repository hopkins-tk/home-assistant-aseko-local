"""Interfaces with the Aseko Local binary sensors."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

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
    enabled: bool = True


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
        translation_key="filtration_pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.filtration_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="cl_pump_running",
        translation_key="cl_pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.cl_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="ph_minus_pump_running",
        translation_key="ph_minus_pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.ph_minus_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="ph_plus_pump_running",
        translation_key="ph_plus_pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.ph_plus_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="algicide_pump_running",
        translation_key="algicide_pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.algicide_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="floc_pump_running",
        translation_key="floc_pump_running",
        icon="mdi:pump",
        value_fn=lambda device: device.floc_pump_running,
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
    _LOGGER.debug(
        ">>> [sensor] Found %s devices: %s",
        len(devices),
        [d.serial_number for d in devices],
    )

    entities: list[BinarySensorEntity] = []

    for device in devices:
        _LOGGER.debug(
            ">>> [sensor] Setting up binary sensors for device (serial=%s)",
            device.serial_number,
        )

        for description in filter(lambda d: d.enabled, BINARY_SENSORS):
            key = description.key
            val = description.value_fn(device)

            _LOGGER.debug(
                "Processing binary sensor: %s (value=%s)",
                key,
                val,
            )

            if val is None:
                _LOGGER.debug(
                    "   - Skipped non-available binary sensor: %s (value=None)",
                    key,
                )
                continue
            entity = AsekoLocalBinarySensorEntity(device, coordinator, description)
            entities.append(entity)
            _LOGGER.debug(
                "   - Regular binary sensor: %s (unique_id=%s)",
                key,
                entity.unique_id,
            )

    _LOGGER.debug(">>> [sensor] Adding %s binary sensors", len(entities))
    async_add_entities(entities)


class AsekoLocalBinarySensorEntity(AsekoLocalEntity, BinarySensorEntity):
    """Representation of an Aseko device binary sensor entity."""

    entity_description: AsekoLocalBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state of the sensor."""
        val = self.entity_description.value_fn(self.device)
        _LOGGER.debug(
            ">>> [sensor] native_value for %s (%s): %s",
            self.entity_description.key,
            self.unique_id,
            val,
        )
        return val
