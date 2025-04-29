"""Interfaces with the Aseko Local sensors."""

from collections.abc import Callable
from dataclasses import dataclass

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


@dataclass(frozen=True, kw_only=True)
class AsekoSensorEntityDescription(SensorEntityDescription):
    """Describes an Aseko device sensor entity."""

    value_fn: Callable[[AsekoDevice], StateType]


SENSORS: list[AsekoSensorEntityDescription] = [
    AsekoSensorEntityDescription(
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
        options=[direction.name for direction in AsekoElectrolyzerDirection],
        icon="mdi:arrow-left-right-bold",
        value_fn=lambda device: device.electrolyzer_direction.value
        if device.electrolyzer_direction is not None
        else None,
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
        key="ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.ph,
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
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Aseko device sensors."""

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices()
    async_add_entities(
        AsekoLocalSensorEntity(device, coordinator, description)
        for description in SENSORS
        for device in devices
        if description.value_fn(device) is not None
    )


class AsekoLocalSensorEntity(AsekoLocalEntity, SensorEntity):
    """Representation of an Aseko device sensor entity."""

    entity_description: AsekoSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.device)
