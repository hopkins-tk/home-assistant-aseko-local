"""Interfaces with the Aseko Local sensors."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    Platform,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import AsekoLocalConfigEntry
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import (
    AsekoLocalEntity,
    async_remove_retired_platform_entities,
    async_setup_platform_entities,
)
from .models import (
    AsekoConnectionState,
    AsekoDevice,
    AsekoElectrodePolarity,
    AsekoHeatingCondition,
    AsekoProfileFlag,
    AsekoVariableSpeedPumpType,
)

_LOGGER = logging.getLogger(__name__)

# ---------- Base descriptions ----------


@dataclass(frozen=True, kw_only=True)
class AsekoSensorEntityDescription(SensorEntityDescription):
    """Describes a regular Aseko device sensor entity."""

    value_fn: Callable[[AsekoDevice], StateType]
    enabled: bool = True
    # The AsekoDevice field this sensor stands for.  The entity is created
    # when that field is in ``device.features``, i.e. when the decoder says
    # this unit has the quantity — whether or not its value is known yet.  A
    # None value then shows as "unknown" rather than as a missing entity.
    # Leave unset for sensors every device has (connection status, last seen).
    feature: str | None = None
    # The unit when it depends on the device (v8 sends the delays in minutes).
    # None: ``native_unit_of_measurement`` as given.
    unit_fn: Callable[[AsekoDevice], str] | None = None


def _delay_unit(device: AsekoDevice) -> str:
    """Minutes where the profile says so (v8), seconds otherwise (v7)."""
    if AsekoProfileFlag.DELAYS_IN_MINUTES in device.flags:
        return UnitOfTime.MINUTES
    return UnitOfTime.SECONDS


@dataclass(frozen=True, kw_only=True)
class AsekoConsumptionSensorEntityDescription(SensorEntityDescription):
    """Describes a chemical consumption sensor entity (value from Tracker)."""

    pump_key: str = ""  # one of PUMP_KEYS in trackers.consumption
    counter: str = ""  # "total" or "canister"


# ---------- Consumption sensors ----------

# Maps pump_key to the corresponding *_pump_running field on AsekoDevice.
PUMP_RUNNING_ATTR: dict[str, str] = {
    "cl": "chlorine_pump_running",
    "ph_minus": "ph_minus_pump_running",
    "ph_plus": "ph_plus_pump_running",
    "algicide": "algaecide_pump_running",
    "floc": "flocculant_pump_running",
    "oxy": "oxygen_pump_running",
}


def device_has_pump(device: AsekoDevice, pump_key: str) -> bool:
    """Return True if this unit has the given chemical pump.

    Answered by the decoder rather than by byte masks: the pump's
    running-state field is in ``device.features`` when the model reads it
    and this unit has the pump.  SALT's shared third port is algicide *or*
    flocculant, so only the chemical the port is configured for is present;
    a pump nobody has mapped yet (pH+) is in no profile's list at all.
    """
    return PUMP_RUNNING_ATTR[pump_key] in device.features


def model_has_pump(device: AsekoDevice, pump_key: str) -> bool:
    """Return True if this unit's model can have the given chemical pump.

    The entities for a pump are built when the model has it; they start
    disabled until this unit shows the pump (``device_has_pump``).
    """
    return PUMP_RUNNING_ATTR[pump_key] in device.possible_features


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
        key="airTemp",
        feature="air_temperature",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sun-thermometer",
        value_fn=lambda device: device.air_temperature,
    ),
    AsekoSensorEntityDescription(
        key="electrolyzer",
        feature="chlorine_production",
        translation_key="chlorine_production",
        native_unit_of_measurement="g/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        value_fn=lambda device: device.chlorine_production,
    ),
    AsekoSensorEntityDescription(
        key="chlorine_production_measured",
        feature="chlorine_production_measured",
        translation_key="chlorine_production_measured",
        native_unit_of_measurement="g/h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:lightning-bolt-outline",
        value_fn=lambda device: device.chlorine_production_measured,
    ),
    AsekoSensorEntityDescription(
        key="electrolyzer_direction",
        feature="electrode_polarity",
        translation_key="electrode_polarity",
        device_class=SensorDeviceClass.ENUM,
        options=[direction.value for direction in AsekoElectrodePolarity],
        icon="mdi:arrow-left-right-bold",
        value_fn=lambda device: (
            device.electrode_polarity.value
            if device.electrode_polarity is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="free_chlorine",
        feature="free_chlorine",
        translation_key="free_chlorine",
        native_unit_of_measurement="mg/l",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.free_chlorine,
    ),
    AsekoSensorEntityDescription(
        key="required_free_chlorine",
        feature="free_chlorine_target",
        translation_key="free_chlorine_target",
        native_unit_of_measurement="mg/l",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.free_chlorine_target,
    ),
    AsekoSensorEntityDescription(
        key="free_chlorine_mv",
        feature="free_chlorine_mv",
        translation_key="free_chlorine_mv",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.free_chlorine_mv,
    ),
    AsekoSensorEntityDescription(
        key="ph",
        feature="ph",
        translation_key="ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.ph,
    ),
    AsekoSensorEntityDescription(
        key="required_ph",
        feature="ph_target",
        translation_key="ph_target",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.ph_target,
    ),
    AsekoSensorEntityDescription(
        key="ph_minus_concentration",
        feature="ph_minus_concentration",
        translation_key="ph_minus_concentration",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.ph_minus_concentration,
    ),
    AsekoSensorEntityDescription(
        key="rx",
        feature="redox",
        translation_key="redox",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.redox,
    ),
    AsekoSensorEntityDescription(
        key="required_rx",
        feature="redox_target",
        translation_key="redox_target",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.redox_target,
    ),
    AsekoSensorEntityDescription(
        key="salinity",
        feature="salinity",
        translation_key="salinity",
        native_unit_of_measurement="kg/m³",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker-outline",
        value_fn=lambda device: device.salinity,
    ),
    AsekoSensorEntityDescription(
        key="waterTemp",
        feature="water_temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool-thermometer",
        value_fn=lambda device: device.water_temperature,
    ),
    AsekoSensorEntityDescription(
        key="required_waterTemp",
        feature="water_temperature_target",
        translation_key="water_temperature_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool-thermometer",
        value_fn=lambda device: device.water_temperature_target,
    ),
    AsekoSensorEntityDescription(
        key="water_level",
        feature="water_level",
        translation_key="water_level",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves",
        value_fn=lambda device: device.water_level,
    ),
    AsekoSensorEntityDescription(
        key="water_level_low_alarm",
        feature="water_level_low_alarm",
        translation_key="water_level_low_alarm",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-down",
        value_fn=lambda device: device.water_level_low_alarm,
    ),
    AsekoSensorEntityDescription(
        key="water_level_filling_on",
        feature="water_level_refill_start",
        translation_key="water_level_refill_start",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-up",
        value_fn=lambda device: device.water_level_refill_start,
    ),
    AsekoSensorEntityDescription(
        key="water_level_filling_off",
        feature="water_level_refill_stop",
        translation_key="water_level_refill_stop",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-up",
        value_fn=lambda device: device.water_level_refill_stop,
    ),
    AsekoSensorEntityDescription(
        key="water_level_high_alarm",
        feature="water_level_high_alarm",
        translation_key="water_level_high_alarm",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-up",
        value_fn=lambda device: device.water_level_high_alarm,
    ),
    AsekoSensorEntityDescription(
        key="max_filling_time",
        feature="max_refill_time",
        translation_key="max_refill_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer",
        value_fn=lambda device: device.max_refill_time,
    ),
    AsekoSensorEntityDescription(
        key="max_ph_doses",
        feature="max_ph_doses",
        translation_key="max_ph_doses",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        value_fn=lambda device: device.max_ph_doses,
    ),
    AsekoSensorEntityDescription(
        key="required_algicide",
        feature="algaecide_dose_target",
        translation_key="algaecide_dose_target",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.algaecide_dose_target,
    ),
    AsekoSensorEntityDescription(
        key="required_oxy_dose",
        feature="oxygen_dose_target",
        translation_key="oxygen_dose_target",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.oxygen_dose_target,
    ),
    AsekoSensorEntityDescription(
        key="required_cl_dose",
        feature="chlorine_dose_target",
        translation_key="chlorine_dose_target",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.chlorine_dose_target,
    ),
    AsekoSensorEntityDescription(
        key="required_floc",
        feature="flocculant_dose_target",
        translation_key="flocculant_dose_target",
        native_unit_of_measurement="mL/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.flocculant_dose_target,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_chlor",
        feature="chlorine_flow_rate",
        translation_key="chlorine_flow_rate",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.chlorine_flow_rate
            if device.chlorine_pump_running
            else 0
            if device.chlorine_flow_rate is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_minus",
        feature="ph_minus_flow_rate",
        translation_key="ph_minus_flow_rate",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.ph_minus_flow_rate
            if device.ph_minus_pump_running
            else 0
            if device.ph_minus_flow_rate is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_ph_plus",
        feature="ph_plus_flow_rate",
        translation_key="ph_plus_flow_rate",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.ph_plus_flow_rate
            if device.ph_plus_pump_running
            else 0
            if device.ph_plus_flow_rate is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_algicide",
        feature="algaecide_flow_rate",
        translation_key="algaecide_flow_rate",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.algaecide_flow_rate
            if device.algaecide_pump_running
            else 0
            if device.algaecide_flow_rate is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_floc",
        feature="flocculant_flow_rate",
        translation_key="flocculant_flow_rate",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.flocculant_flow_rate
            if device.flocculant_pump_running
            else 0
            if device.flocculant_flow_rate is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="flowrate_oxy",
        feature="oxygen_flow_rate",
        translation_key="oxygen_flow_rate",
        native_unit_of_measurement="mL/min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-pump",
        value_fn=lambda device: (
            device.oxygen_flow_rate
            if device.oxygen_pump_running
            else 0
            if device.oxygen_flow_rate is not None
            else None
        ),
        entity_registry_visible_default=False,
    ),
    AsekoSensorEntityDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda device: device.last_seen,
    ),
    AsekoSensorEntityDescription(
        key="filtration_1_start",
        feature="filtration_period_1_start",
        translation_key="filtration_period_1_start",
        icon="mdi:clock-start",
        value_fn=lambda device: (
            device.filtration_period_1_start.strftime("%H:%M")
            if device.filtration_period_1_start is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_1_stop",
        feature="filtration_period_1_end",
        translation_key="filtration_period_1_end",
        icon="mdi:clock-end",
        value_fn=lambda device: (
            device.filtration_period_1_end.strftime("%H:%M")
            if device.filtration_period_1_end is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_2_start",
        feature="filtration_period_2_start",
        translation_key="filtration_period_2_start",
        icon="mdi:clock-start",
        value_fn=lambda device: (
            device.filtration_period_2_start.strftime("%H:%M")
            if device.filtration_period_2_start is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_2_stop",
        feature="filtration_period_2_end",
        translation_key="filtration_period_2_end",
        icon="mdi:clock-end",
        value_fn=lambda device: (
            device.filtration_period_2_end.strftime("%H:%M")
            if device.filtration_period_2_end is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_schedule",
        feature="filtration_schedule",
        translation_key="filtration_schedule",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.ENUM,
        # What the unit runs when nobody is at it.  byte[37] bit 0x04 is a
        # separate fact and lives on binary_sensor.service_menu.
        options=[
            "nonstop_24h",
            "timer_period_1",
            "timer_period_1_and_2",
        ],
        value_fn=lambda device: (
            device.filtration_schedule.value
            if device.filtration_schedule is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="heating_condition",
        feature="heating_condition",
        translation_key="heating_condition",
        icon="mdi:thermostat-auto",
        device_class=SensorDeviceClass.ENUM,
        options=[condition.value for condition in AsekoHeatingCondition],
        value_fn=lambda device: (
            device.heating_condition.value
            if device.heating_condition is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="variable_speed_pump_type",
        feature="variable_speed_pump_type",
        translation_key="variable_speed_pump_type",
        icon="mdi:pump",
        device_class=SensorDeviceClass.ENUM,
        options=[pump.value for pump in AsekoVariableSpeedPumpType],
        value_fn=lambda device: (
            device.variable_speed_pump_type.value
            if device.variable_speed_pump_type is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="pool_volume",
        feature="pool_volume",
        translation_key="pool_volume",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.pool_volume,
    ),
    AsekoSensorEntityDescription(
        key="delay_after_startup",
        feature="startup_delay",
        translation_key="startup_delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-play-outline",
        unit_fn=_delay_unit,
        value_fn=lambda device: device.startup_delay,
    ),
    AsekoSensorEntityDescription(
        key="delay_after_dose",
        feature="dosing_delay",
        translation_key="dosing_delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        unit_fn=_delay_unit,
        value_fn=lambda device: device.dosing_delay,
    ),
    AsekoSensorEntityDescription(
        key="backwash_every_n_days",
        feature="backwash_interval",
        translation_key="backwash_interval",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-refresh",
        value_fn=lambda device: device.backwash_interval,
    ),
    AsekoSensorEntityDescription(
        key="backwash_time",
        feature="backwash_start_time",
        translation_key="backwash_start_time",
        icon="mdi:clock-start",
        value_fn=lambda device: (
            device.backwash_start_time.strftime("%H:%M")
            if device.backwash_start_time is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="backwash_duration",
        feature="backwash_duration",
        translation_key="backwash_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-sand",
        value_fn=lambda device: device.backwash_duration,
    ),
    # Observed backwash history.  Present on every unit with a backwash
    # valve (feature backwash_running), unknown until a cycle has actually
    # been seen.
    #
    # last_backwash is the *observed* one: the integration watched the backwash
    # valve stay open, so the cycle definitely happened.
    #
    # The scheduled/manual split is *derived* from it by a heuristic comparing
    # the start time against the configured schedule, and that heuristic can
    # get it wrong — the device never says why the valve opened.  Only the
    # timestamps stay exact.  "(estimated)" therefore marks just
    # next_scheduled_backwash, the one value that is calculated rather than
    # measured.  See trackers.backwash.BackwashTracker._classify.
    AsekoSensorEntityDescription(
        key="last_backwash",
        feature="backwash_running",
        translation_key="last_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
        value_fn=lambda device: device.last_backwash,
    ),
    # last_scheduled_backwash is not here: it is a writable datetime entity
    # (see datetime.py) so it can be set from the UI in one click, rather than
    # a read-only sensor plus a helper and a script to feed it.
    AsekoSensorEntityDescription(
        key="last_manual_backwash",
        feature="backwash_running",
        translation_key="last_manual_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:hand-back-right-outline",
        value_fn=lambda device: device.last_manual_backwash,
    ),
    AsekoSensorEntityDescription(
        # Renamed from "next_backwash" — see MIGRATED_UNIQUE_ID_SUFFIXES.
        key="next_scheduled_backwash",
        feature="backwash_running",
        translation_key="next_scheduled_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-alert-outline",
        value_fn=lambda device: device.next_scheduled_backwash,
        # No source attribute: projected from last_scheduled_backwash, or
        # after a schedule change from the day after it; on the unit's clock.
    ),
    AsekoSensorEntityDescription(
        # Minutes the unit's clock is ahead of Home Assistant's; see
        # trackers/clock.py.  Only models that send their clock have it.
        key="clock_offset",
        feature="unit_clock",
        translation_key="clock_offset",
        icon="mdi:clock-fast",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.clock_offset,
    ),
]

# Sensor keys that were renamed after release.  The unique_id is
# f"{serial_number}{key}", so renaming a key orphans the registry entry: the
# old entity goes unavailable forever and a fresh one appears beside it under a
# new entity_id, losing its history.  async_migrate_unique_ids rewrites them at
# setup instead.  Old suffix → new suffix; entries are matched on the suffix
# because the serial number prefix varies per device.
# Sensor keys that no longer exist.  Same problem as a rename, minus the
# destination: the registry entry outlives the description and the entity
# sits in the UI as unavailable forever.  async_remove_retired_entities
# deletes them at setup.  Suffixes, because the serial prefix varies.
RETIRED_UNIQUE_ID_SUFFIXES: frozenset[str] = frozenset(
    {
        # byte[37] bit 0x04 is not a filtration state — it marks the unit's
        # settings menu being open, and is now binary_sensor.service_menu.
        # What is left of the old sensor is filtration_schedule.
        "filtration_mode",
    }
)

MIGRATED_UNIQUE_ID_SUFFIXES: dict[str, str] = {
    # v1.7.x → next: renamed for symmetry with last_scheduled_backwash, and
    # because the value only ever projects the *scheduled* cycle.
    "next_backwash": "next_scheduled_backwash",
}


# ---------- Connection status sensor ----------

CONNECTION_STATUS_SENSOR = AsekoSensorEntityDescription(
    key="connection_status",
    translation_key="connection_status",
    device_class=SensorDeviceClass.ENUM,
    options=[state.value for state in AsekoConnectionState],
    icon="mdi:lan-connect",
    value_fn=lambda device: device.connection_state().value,
)

# ---------- Setup ----------


@callback
def async_migrate_unique_ids(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> None:
    """Rewrite registry unique_ids for sensor keys that have been renamed.

    Runs before the entities are added, so each renamed sensor keeps its
    entity_id, its history and any automation pointing at it.

    Nothing happens when there is no old entry, so this is a no-op on fresh
    installs and on every setup after the first.
    """
    registry = er.async_get(hass)
    existing = {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }

    for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id):
        if entry.domain != "sensor":
            continue
        for old_suffix, new_suffix in MIGRATED_UNIQUE_ID_SUFFIXES.items():
            if not entry.unique_id.endswith(old_suffix):
                continue
            new_unique_id = entry.unique_id[: -len(old_suffix)] + new_suffix
            if new_unique_id in existing:
                # Both ids present — the new entity was already created (e.g. a
                # partially completed earlier migration).  Renaming onto it
                # would raise, so leave the stale one for the user to delete.
                _LOGGER.debug(
                    ">>> [sensor] Skipping unique_id migration %s → %s: target exists",
                    entry.unique_id,
                    new_unique_id,
                )
                break
            _LOGGER.info(
                "Migrating Aseko sensor unique_id %s → %s",
                entry.unique_id,
                new_unique_id,
            )
            registry.async_update_entity(entry.entity_id, new_unique_id=new_unique_id)
            existing.add(new_unique_id)
            break


@callback
def async_remove_retired_entities(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> None:
    """Delete registry entries for sensors that no longer exist.

    Runs before the entities are added, so a retired one never gets a
    chance to be restored as unavailable.  A no-op once there is nothing
    left to remove.
    """
    async_remove_retired_platform_entities(
        hass, config_entry, Platform.SENSOR, RETIRED_UNIQUE_ID_SUFFIXES
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Aseko device sensors."""

    async_migrate_unique_ids(hass, config_entry)
    async_remove_retired_entities(hass, config_entry)
    async_setup_platform_entities(
        hass, config_entry, async_add_entities, Platform.SENSOR, _build_sensor_entities
    )


def _is_present(description: AsekoSensorEntityDescription, device: AsekoDevice) -> bool:
    """Return True if this unit's model has the quantity the description stands for."""
    return (
        description.feature is None or description.feature in device.possible_features
    )


def _wanted(feature: str | None, features: frozenset[str] | None) -> bool:
    """Return True if ``feature`` is among the ones being built right now.

    ``features`` is None when a device is set up for the first time and
    everything it has gets an entity; otherwise it is the set of fields the
    device has just started showing, and only their entities are built.
    """
    return features is None or feature in features


def _build_sensor_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
    features: frozenset[str] | None = None,
) -> list[SensorEntity]:
    """Create sensor entities for the given devices.

    With ``features`` given, only the entities for those fields are built --
    the ones a known device has just started showing.  Without it, every
    entity the device has, for a device seen for the first time.
    """
    entities: list[SensorEntity] = []

    for device in devices:
        _LOGGER.debug(
            ">>> [sensor] Setting up sensors for device (serial=%s)",
            device.serial_number,
        )

        for description in filter(lambda d: d.enabled, SENSORS):
            key = description.key
            # The decoder, not the current value, says whether this unit has
            # the quantity: a field missing from device.features is one the
            # unit does not have, a field in it that reads None is unknown.
            if not _is_present(description, device):
                _LOGGER.debug("   - Skipped sensor %s: not a feature of this unit", key)
                continue
            if not _wanted(description.feature, features):
                continue
            entity = AsekoLocalSensorEntity(device, coordinator, description)
            entities.append(entity)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "   - Regular sensor: %s (unique_id=%s, value=%s)",
                    key,
                    entity.unique_id,
                    description.value_fn(device),
                )

        for description in CONSUMPTION_SENSORS:
            if not model_has_pump(device, description.pump_key):
                continue
            if not _wanted(PUMP_RUNNING_ATTR[description.pump_key], features):
                continue
            entity = AsekoConsumptionSensorEntity(device, coordinator, description)
            entities.append(entity)
            _LOGGER.debug(
                "   - Consumption sensor: %s (unique_id=%s)",
                description.key,
                entity.unique_id,
            )

        # Connection status sensor – every device has one, so it is added
        # when the device is first set up and never again
        if features is None:
            entities.append(
                AsekoConnectionStatusSensorEntity(
                    device, coordinator, CONNECTION_STATUS_SENSOR
                )
            )

    return entities


class AsekoConsumptionSensorEntity(AsekoLocalEntity, RestoreSensor):
    """Sensor that reads L consumed from AsekoConsumptionTracker and restores across restarts."""

    entity_description: AsekoConsumptionSensorEntityDescription

    def __init__(
        self,
        unit: AsekoDevice,
        coordinator: AsekoLocalDataUpdateCoordinator,
        description: AsekoConsumptionSensorEntityDescription,
    ) -> None:
        """Set up one consumption counter of one pump of one unit."""
        AsekoLocalEntity.__init__(
            self,
            unit,
            coordinator,
            description,
            feature=PUMP_RUNNING_ATTR[description.pump_key],
        )

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
            # The coordinator's store holds the exact millilitres; the sensor's
            # rounded litres only seed a tracker that store had nothing for
            # (the first start after an upgrade).
            pump_key = self.entity_description.pump_key
            if tracker is not None and pump_key not in tracker.restored_keys:
                # Persisted value is in L; tracker works internally in mL
                tracker.seed_counter(
                    pump_key,
                    self.entity_description.counter,
                    value * 1000,
                )


class AsekoLocalSensorEntity(AsekoLocalEntity, SensorEntity):
    """Representation of an Aseko device sensor entity."""

    entity_description: AsekoSensorEntityDescription

    @property
    def native_unit_of_measurement(self) -> str | None:
        """The description's unit, or the device's where it depends on the protocol."""
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self.device)
        return super().native_unit_of_measurement

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
    """Connection status sensor: always available, shows 'online', 'offline' or 'service_menu'.

    Overrides the base available property so the sensor remains visible even
    when the device is offline – instead of going unavailable it shows 'offline'.
    """

    @property
    def available(self) -> bool:
        """Always available: reports 'offline' rather than becoming unavailable."""
        return True
