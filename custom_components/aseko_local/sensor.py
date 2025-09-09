"""Interfaces with the Aseko Local sensors."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import AsekoLocalConfigEntry
from .aseko_data import AsekoDevice, AsekoElectrolyzerDirection, AsekoPumpType
from .entity import AsekoLocalEntity
# from .consumption import _pump_key  # only for building translation_key
from .optional_entities import get_optional_inactive_entities

_LOGGER = logging.getLogger(__name__)

# ---------- Base descriptions ----------

@dataclass(frozen=True, kw_only=True)
class AsekoSensorEntityDescription(SensorEntityDescription):
    """Describes a regular Aseko device sensor entity."""
    value_fn: Callable[[AsekoDevice], StateType]


@dataclass(frozen=True, kw_only=True)
class AsekoConsumptionSensorEntityDescription(SensorEntityDescription):
    """Describes a chemical consumption sensor entity (value from Tracker)."""
    resettable: bool = False


# ---------- Fixed (system-level) sensors ----------

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
        key="cl_free_mv",
        translation_key="free_chlorine_mv",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.cl_free_mv,
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
        key="active_pump",
        translation_key="active_pump",
        device_class=SensorDeviceClass.ENUM,
        options=[c.name.lower() for c in AsekoPumpType],
        icon="mdi:pump",
        value_fn=lambda device: (
            device.active_pump.name.lower() if device.active_pump else "off"
        ),
    ),
    AsekoSensorEntityDescription(
        key="flowrate_chlor",
        translation_key="flowrate_chlor",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_chlor,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_minus",
        translation_key="flowrate_ph_minus",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_ph_minus,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_plus",
        translation_key="flowrate_ph_plus",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_ph_plus,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_floc",
        translation_key="flowrate_floc",
        native_unit_of_measurement="ml/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: device.flowrate_floc,
    ),
]

# ---------- Chemical consumption sensors (per pump) ----------

CHEMICAL_CONSUMPTION_SENSORS: list[AsekoConsumptionSensorEntityDescription] = [
    AsekoConsumptionSensorEntityDescription( 
        key="consumed", 
        translation_key="consumed", 
        native_unit_of_measurement=UnitOfVolume.LITERS, 
        state_class=SensorStateClass.MEASUREMENT, 
        icon="mdi:chart-bar", 
        resettable=True, 
        ), 
    AsekoConsumptionSensorEntityDescription( 
        key="total_consumed", 
        translation_key="total_consumed", 
        native_unit_of_measurement=UnitOfVolume.LITERS, 
        state_class=SensorStateClass.TOTAL_INCREASING, 
        icon="mdi:chart-bar-stacked", 
        ), 
    AsekoConsumptionSensorEntityDescription( 
        key="remaining", 
        translation_key="remaining", 
        native_unit_of_measurement=UnitOfVolume.LITERS, 
        state_class=SensorStateClass.MEASUREMENT, 
        icon="mdi:beaker-outline", 
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
        len(devices), [d.serial_number for d in devices]
    )

    entities: list[SensorEntity] = []

    for device in devices:
        _LOGGER.debug(
            ">>> [sensor] Setting up sensors for device (serial=%s)",
            device.serial_number,
        )
        optional_inactive, always_inactive = get_optional_inactive_entities(device)

        # --- Regular sensors ---
        for description in SENSORS:
            tr_key = description.key
            val = description.value_fn(device)

            _LOGGER.debug(
                "Processing sensor: %s (value=%s)",
                tr_key, val,
            )

            if tr_key in optional_inactive or tr_key in always_inactive:
                ent = AsekoLocalSensorEntity(device, coordinator, description)

                reasonInactive = "none"              
                if tr_key in always_inactive:
                    reasonInactive = "always"
                    ent._attr_entity_registry_enabled_default = False
                    _LOGGER.debug(
                        "   - Always inactive sensor: %s (unique_id=%s, value=%s)",
                        tr_key, ent.unique_id, val,
                    )

                if val is None:
                    reasonInactive = "optional"
                    ent._attr_entity_registry_enabled_default = False
                    _LOGGER.debug(
                        "   - Optional inactive sensor because of value none: %s (unique_id=%s, active=%s)",
                        tr_key, ent.unique_id, val is not None,
                    )

                entities.append(ent)
                _LOGGER.debug(
                    "       → Created as %s inactive because %s",
                    "always" if tr_key in always_inactive else "optionally",
                    reasonInactive,
                )
            else:
                if val is None:
                    # not optional and no value -> skip
                    _LOGGER.debug(
                        "   - Skipped non-optional sensor: %s (value=None)",
                        tr_key,
                    )
                    continue
                ent = AsekoLocalSensorEntity(device, coordinator, description)
                entities.append(ent)
                _LOGGER.debug(
                    "   - Regular sensor: %s (unique_id=%s)",
                    tr_key, ent.unique_id,
                )

        # --- Chemical consumption sensors (per pump) ---
        # for description in CHEMICAL_CONSUMPTION_SENSORS:
        #     for pump_type in AsekoPumpType:
        #         if pump_type == AsekoPumpType.OFF:
        #             continue

        #         flow_attr = f"flowrate_{pump_type.name.lower()}"
        #         flowrate_value = getattr(device, flow_attr, None)

        #         if flow_attr in optional_inactive:
        #             ent = AsekoConsumptionSensorEntity(
        #                 device, coordinator, description, pump_type
        #             )
        #             if flowrate_value is None:
        #                 ent._attr_entity_registry_enabled_default = False
        #             entities.append(ent)
        #             _LOGGER.debug(
        #                 "   - Optional consumption sensor: %s (pump=%s, active=%s)",
        #                 description.key, pump_type.name, flowrate_value is not None,
        #             )
        #         else:
        #             if flowrate_value is None:
        #                 # Not optional and no value -> skip
        #                 _LOGGER.debug(
        #                     "   - Skipped non-optional consumption sensor: %s (pump=%s, value=None)",
        #                     description.key, pump_type.name,
        #                 )
        #                 continue
        #             ent = AsekoConsumptionSensorEntity(
        #                 device, coordinator, description, pump_type
        #             )
        #             entities.append(ent)
        #             _LOGGER.debug(
        #                 "   - Consumption sensor: %s (unique_id=%s, pump=%s)",
        #                 description.key, ent.unique_id, pump_type.name,
        #             )

    _LOGGER.debug(">>> [sensor] Adding %s sensors", len(entities))
    async_add_entities(entities)


# ---------- Entities ----------

class AsekoLocalSensorEntity(AsekoLocalEntity, SensorEntity):
    """Representation of a regular Aseko device sensor entity."""

    entity_description: AsekoSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        val = self.entity_description.value_fn(self.device)
        _LOGGER.debug(">>> [sensor] native_value for %s (%s): %s", self.entity_description.key, self.unique_id, val)
        return val


# class AsekoConsumptionSensorEntity(AsekoLocalEntity, SensorEntity):
#     """Representation of a chemical consumption sensor (backed by the tracker)."""

#     entity_description: AsekoConsumptionSensorEntityDescription

#     def __init__(self, device, coordinator, description, pump_type: AsekoPumpType):
#         super().__init__(device, coordinator, description)
#         self._pump_type = pump_type

#         pump_key = _pump_key(pump_type)
#         if not pump_key:
#             raise ValueError(f"Invalid pump_type={pump_type} for consumption sensor")

#         self._attr_unique_id = f"{device.serial_number}_{pump_key}_{description.key}"
#         self._attr_translation_key = f"{pump_key}_{description.translation_key}"

#     @property
#     def native_value(self) -> StateType:
#         tracker = self.coordinator.consumption_tracker
#         serial = self.device.serial_number
#         key = self.entity_description.key

#         if key == "consumed":
#             val = round(tracker.get_consumed_l(serial, self._pump_type), 2)
#         elif key == "total_consumed":
#             val = round(tracker.get_total_consumed_l(serial, self._pump_type), 2)
#         elif key == "remaining":
#             last = tracker.get_last_fill_l(serial, self._pump_type) or 0.0
#             used = tracker.get_consumed_l(serial, self._pump_type) or 0.0
#             val = max(0.0, round(last - used, 2))
#         else:
#             val = None

#         _LOGGER.debug(">>> [sensor] native_value for consumption sensor %s (%s): %s",
#                       self.entity_description.key, self.unique_id, val)
#         return val