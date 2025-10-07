"""Interfaces with the Aseko Local sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import AsekoLocalConfigEntry
from .aseko_data import AsekoDevice, AsekoElectrolyzerDirection
from .entity import AsekoLocalEntity

_LOGGER = logging.getLogger(__name__)

# ---------- Base descriptions ----------


@dataclass(frozen=True, kw_only=True)
class AsekoSensorEntityDescription(SensorEntityDescription):
    """Describes a regular Aseko device sensor entity."""

    value_fn: Callable[[AsekoDevice], StateType]
    enabled: bool = True


@dataclass(frozen=True, kw_only=True)
class AsekoConsumptionSensorEntityDescription(SensorEntityDescription):
    """Describes a chemical consumption sensor entity (value from Tracker)."""

    resettable: bool = False


# ---------- Fixed (system-level) sensors ----------

SENSORS: list[SensorEntityDescription] = [
    AsekoSensorEntityDescription(
        # Air temperature is missing in decoder, no idea which byte is
        key="airTemp",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.air_temperature,
    ),
    AsekoSensorEntityDescription(
        key="electrolyzer",
        translation_key="electrolyzer_power",
        native_unit_of_measurement="g/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        value_fn=lambda device: device.electrolyzer_power,
    ),
    AsekoSensorEntityDescription(
        key="electrolyzer_direction",
        translation_key="electrolyzer_direction",
        device_class=SensorDeviceClass.ENUM,
        options=[direction.value for direction in AsekoElectrolyzerDirection],
        icon="mdi:arrow-left-right-bold",
        value_fn=lambda device: (
            device.electrolyzer_direction.value
            if device.electrolyzer_direction is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="free_chlorine",
        translation_key="free_chlorine",
        native_unit_of_measurement="mg/l",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.cl_free,
    ),
    AsekoSensorEntityDescription(
        key="required_free_chlorine",
        translation_key="required_free_chlorine",
        native_unit_of_measurement="mg/l",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_cl_free,
    ),
    AsekoSensorEntityDescription(
        key="free_chlorine_mv",
        translation_key="free_chlorine_mv",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.cl_free_mv,
        entity_registry_enabled_default=False,
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="ph",
        translation_key="ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.ph,
    ),
    AsekoSensorEntityDescription(
        key="required_ph",
        translation_key="required_ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_ph,
    ),
    AsekoSensorEntityDescription(
        key="rx",
        translation_key="redox",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.redox,
    ),
    AsekoSensorEntityDescription(
        key="required_rx",
        translation_key="required_redox",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_redox,
    ),
    AsekoSensorEntityDescription(
        key="salinity",
        translation_key="salinity",
        native_unit_of_measurement="kg/m³",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker-outline",
        value_fn=lambda device: device.salinity,
    ),
    AsekoSensorEntityDescription(
        key="waterTemp",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool-thermometer",
        value_fn=lambda device: device.water_temperature,
    ),
    AsekoSensorEntityDescription(
        key="required_waterTemp",
        translation_key="required_water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool-thermometer",
        value_fn=lambda device: device.required_water_temperature,
    ),
    AsekoSensorEntityDescription(
        key="required_algicide",
        translation_key="required_algicide",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_algicide,
    ),
    AsekoSensorEntityDescription(
        key="required_floc",
        translation_key="required_floc",
        native_unit_of_measurement="ml/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_floc,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_chlor",
        translation_key="flowrate_chlor",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_chlor
        if device.cl_pump_running
        else 0
        if device.flowrate_chlor is not None
        else None,
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_minus",
        translation_key="flowrate_ph_minus",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_ph_minus
        if device.ph_minus_pump_running
        else 0
        if device.flowrate_ph_minus is not None
        else None,
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_plus",
        translation_key="flowrate_ph_plus",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_ph_plus
        if device.ph_plus_pump_running
        else 0
        if device.flowrate_ph_plus is not None
        else None,
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_algicide",
        translation_key="flowrate_algicide",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_algicide
        if device.algicide_pump_running
        else 0
        if device.flowrate_algicide is not None
        else None,
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_floc",
        translation_key="flowrate_floc",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_floc
        if device.floc_pump_running
        else 0
        if device.flowrate_floc is not None
        else None,
        entity_registry_visible_default=False,
    ),
]

# ---------- Setup ----------


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Aseko device sensors."""

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices() or []
    _LOGGER.debug(
        ">>> [sensor] Found %s devices: %s",
        len(devices),
        [d.serial_number for d in devices],
    )

    entities: list[SensorEntity] = []

    for device in devices:
        _LOGGER.debug(
            ">>> [sensor] Setting up sensors for device (serial=%s)",
            device.serial_number,
        )

        for description in filter(lambda d: d.enabled, SENSORS):
            key = description.key
            val = description.value_fn(device)

            _LOGGER.debug(
                "Processing sensor: %s (value=%s)",
                key,
                val,
            )

            if val is None:
                _LOGGER.debug(
                    "   - Skipped non-available sensor: %s (value=None)",
                    key,
                )
                continue
            entity = AsekoLocalSensorEntity(device, coordinator, description)
            entities.append(entity)
            _LOGGER.debug(
                "   - Regular sensor: %s (unique_id=%s)",
                key,
                entity.unique_id,
            )

    _LOGGER.debug(">>> [sensor] Adding %s sensors", len(entities))
    async_add_entities(entities)


class AsekoLocalSensorEntity(AsekoLocalEntity, SensorEntity):
    """Representation of an Aseko device sensor entity."""

    entity_description: AsekoSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        val = self.entity_description.value_fn(self.device)
        _LOGGER.debug(
            ">>> [sensor] native_value for %s (%s): %s",
            self.entity_description.key,
            self.unique_id,
            val,
        )
        return val
