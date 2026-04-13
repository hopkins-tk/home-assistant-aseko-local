"""Interfaces with the Aseko Local sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable

from homeassistant.components.sensor import (
    RestoreSensor,
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
from .aseko_data import AsekoDevice, AsekoElectrolyzerDirection, ACTUATOR_MASKS
from .coordinator import AsekoLocalDataUpdateCoordinator
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

    pump_key: str = ""  # one of PUMP_KEYS in consumption_tracker
    counter: str = ""  # "total" or "canister"


# ---------- Consumption sensors ----------

# Maps pump_key to the corresponding field name in AsekoActuatorMasks.
# None means the pump is not yet mapped (e.g. pH+) and sensors are skipped.
PUMP_MASK_FIELD: dict[str, str | None] = {
    "cl": "cl",
    "ph_minus": "ph_minus",
    "ph_plus": None,  # byte position unknown — disabled until confirmed
    "algicide": "algicide",
    "floc": "flocculant",
    "oxy": "oxy",  # byte position unconfirmed — enabled once mask is set in ACTUATOR_MASKS
}

# Maps pump_key to the corresponding *_pump_running attribute on AsekoDevice.
# Used as secondary filter: if the decoder left the attribute as None, the pump
# is not present on this specific device (e.g. algicide vs flocculant share bit 0x20).
PUMP_RUNNING_ATTR: dict[str, str] = {
    "cl": "cl_pump_running",
    "ph_minus": "ph_minus_pump_running",
    "ph_plus": "ph_plus_pump_running",
    "algicide": "algicide_pump_running",
    "floc": "floc_pump_running",
    "oxy": "oxy_pump_running",
}

CONSUMPTION_SENSORS: list[AsekoConsumptionSensorEntityDescription] = [
    AsekoConsumptionSensorEntityDescription(
        key="chlor_consumed",
        translation_key="chlor_consumed",
        pump_key="cl",
        counter="canister",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="chlor_total_consumed",
        translation_key="chlor_total_consumed",
        pump_key="cl",
        counter="total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="ph_minus_consumed",
        translation_key="ph_minus_consumed",
        pump_key="ph_minus",
        counter="canister",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="ph_minus_total_consumed",
        translation_key="ph_minus_total_consumed",
        pump_key="ph_minus",
        counter="total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="ph_plus_consumed",
        translation_key="ph_plus_consumed",
        pump_key="ph_plus",
        counter="canister",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="ph_plus_total_consumed",
        translation_key="ph_plus_total_consumed",
        pump_key="ph_plus",
        counter="total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="algicide_consumed",
        translation_key="algicide_consumed",
        pump_key="algicide",
        counter="canister",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="algicide_total_consumed",
        translation_key="algicide_total_consumed",
        pump_key="algicide",
        counter="total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="floc_consumed",
        translation_key="floc_consumed",
        pump_key="floc",
        counter="canister",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="floc_total_consumed",
        translation_key="floc_total_consumed",
        pump_key="floc",
        counter="total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="oxy_consumed",
        translation_key="oxy_consumed",
        pump_key="oxy",
        counter="canister",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cup-water",
    ),
    AsekoConsumptionSensorEntityDescription(
        key="oxy_total_consumed",
        translation_key="oxy_total_consumed",
        pump_key="oxy",
        counter="total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cup-water",
    ),
]

# ---------- Fixed (system-level) sensors ----------

SENSORS: list[AsekoSensorEntityDescription] = [
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
        key="required_oxy_dose",
        translation_key="required_oxy_dose",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_oxy_dose,
    ),
    AsekoSensorEntityDescription(
        key="required_cl_dose",
        translation_key="required_cl_dose",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_cl_dose,
    ),
    AsekoSensorEntityDescription(
        key="required_floc",
        translation_key="required_floc",
        native_unit_of_measurement="mL/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.required_floc,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_chlor",
        translation_key="flowrate_chlor",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flowrate_chlor
            if device.cl_pump_running
            else 0
            if device.flowrate_chlor is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_minus",
        translation_key="flowrate_ph_minus",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flowrate_ph_minus
            if device.ph_minus_pump_running
            else 0
            if device.flowrate_ph_minus is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_plus",
        translation_key="flowrate_ph_plus",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flowrate_ph_plus
            if device.ph_plus_pump_running
            else 0
            if device.flowrate_ph_plus is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_algicide",
        translation_key="flowrate_algicide",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flowrate_algicide
            if device.algicide_pump_running
            else 0
            if device.flowrate_algicide is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_floc",
        translation_key="flowrate_floc",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flowrate_floc
            if device.floc_pump_running
            else 0
            if device.flowrate_floc is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_oxy",
        translation_key="flowrate_oxy",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flowrate_oxy
            if device.oxy_pump_running
            else 0
            if device.flowrate_oxy is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
]

# ---------- Connection status sensor ----------

CONNECTION_STATUS_SENSOR = AsekoSensorEntityDescription(
    key="connection_status",
    translation_key="connection_status",
    device_class=SensorDeviceClass.ENUM,
    options=["online", "offline"],
    icon="mdi:lan-connect",
    value_fn=lambda device: "online" if device.online() else "offline",
)

LAST_SEEN_SENSOR = AsekoSensorEntityDescription(
    key="last_seen",
    translation_key="last_seen",
    device_class=SensorDeviceClass.TIMESTAMP,
    icon="mdi:clock-outline",
    value_fn=lambda device: device.last_seen,
)

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

        device_masks = (
            ACTUATOR_MASKS.get(device.device_type) if device.device_type else None
        )
        for description in CONSUMPTION_SENSORS:
            mask_field = PUMP_MASK_FIELD[description.pump_key]
            if mask_field is None:
                continue  # pump not yet mapped (e.g. ph_plus)
            if device_masks is None or getattr(device_masks, mask_field, 0) == 0:
                continue  # pump not present on this device type
            running_attr = PUMP_RUNNING_ATTR.get(description.pump_key)
            if running_attr and getattr(device, running_attr, None) is None:
                continue  # decoder determined pump absent (e.g. algicide vs floc share bit 0x20)
            entity = AsekoConsumptionSensorEntity(device, coordinator, description)
            entities.append(entity)
            _LOGGER.debug(
                "   - Consumption sensor: %s (unique_id=%s)",
                description.key,
                entity.unique_id,
            )

        # Connection status sensor – always added, overrides available to show offline state
        entities.append(
            AsekoConnectionStatusSensorEntity(
                device, coordinator, CONNECTION_STATUS_SENSOR
            )
        )

    _LOGGER.debug(">>> [sensor] Adding %s sensors", len(entities))
    async_add_entities(entities)


class AsekoConsumptionSensorEntity(AsekoLocalEntity, RestoreSensor):
    """Sensor that reads L consumed from AsekoConsumptionTracker and restores across restarts."""

    entity_description: AsekoConsumptionSensorEntityDescription

    def __init__(
        self,
        unit: AsekoDevice,
        coordinator: AsekoLocalDataUpdateCoordinator,
        description: AsekoConsumptionSensorEntityDescription,
    ) -> None:
        AsekoLocalEntity.__init__(self, unit, coordinator, description)

    @property
    def native_value(self) -> float | None:
        """Return current consumption in litres (3 dp) from the tracker, or None if not ready."""
        if self.device.serial_number is None:
            return None
        tracker = self.coordinator.get_tracker(self.device.serial_number)
        if tracker is None:
            return None
        return round(
            tracker.get(
                self.entity_description.pump_key, self.entity_description.counter
            )
            / 1000,
            3,
        )

    async def async_added_to_hass(self) -> None:
        """Restore persisted state and seed the tracker on integration startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_sensor_data()
        if last_state and last_state.native_value is not None:
            try:
                value = float(str(last_state.native_value))
            except (TypeError, ValueError):
                return
            if self.device.serial_number is None:
                return
            tracker = self.coordinator.get_tracker(self.device.serial_number)
            if tracker is not None:
                # Persisted value is in L; tracker works internally in mL
                tracker.seed_counter(
                    self.entity_description.pump_key,
                    self.entity_description.counter,
                    value * 1000,
                )


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


class AsekoConnectionStatusSensorEntity(AsekoLocalSensorEntity):
    """Connection status sensor: always available, shows 'online' or 'offline'.

    Overrides the base available property so the sensor remains visible even
    when the device is offline – instead of going unavailable it shows 'offline'.
    """

    @property
    def available(self) -> bool:
        """Always available: reports 'offline' rather than becoming unavailable."""
        return True
