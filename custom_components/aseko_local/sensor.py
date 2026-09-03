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
from homeassistant.const import (
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
from .aseko_data import (
    ACTUATOR_MASKS,
    AsekoDevice,
    AsekoElectrolyzerDirection,
)
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import AsekoLocalEntity

_LOGGER = logging.getLogger(__name__)

# ---------- Base descriptions ----------


@dataclass(frozen=True, kw_only=True)
class AsekoSensorEntityDescription(SensorEntityDescription):
    """Describes a regular Aseko device sensor entity."""

    value_fn: Callable[[AsekoDevice], StateType]
    enabled: bool = True
    # Decides whether the device has this sensor at all.  By default a sensor
    # is created only when its value is already known, which is right for
    # values read straight out of the frame: a None there means the device
    # does not report that quantity.
    #
    # It is wrong for values that are legitimately unknown until an event is
    # observed — the observed-backwash timestamps start out None on a device
    # that does have a backwash valve, and without an explicit check their
    # entities would never be created.  Set this to decide presence from
    # something other than the current value.
    supported_fn: Callable[[AsekoDevice], bool] | None = None


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

# Sensor keys that no longer exist.  The registry entry outlives the
# description, so without this the old entity sits in the UI as unavailable
# forever.  Suffixes, because the unique_id is prefixed with the serial.
RETIRED_UNIQUE_ID_SUFFIXES: frozenset[str] = frozenset(
    {
        # byte[37] bit 0x04 is not a filtration state — it marks the unit's
        # settings menu being open, and is now binary_sensor.service_menu.
        # What is left of the old sensor is filtration_schedule.
        "filtration_mode",
    }
)


def _has_backwash(device: AsekoDevice) -> bool:
    """Return True if the device has a backwash valve.

    ``backwash_active`` is the decoder's presence marker for the backwash
    output: it is left as None on device types without one (NET), and is a
    real bool on every type that has one, whether or not the valve is
    currently open.  See ``AsekoDecoder._fill_backwash_active`` and Issue #129.
    """
    return device.backwash_active is not None


SENSORS: list[AsekoSensorEntityDescription] = [
    AsekoSensorEntityDescription(
        key="airTemp",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sun-thermometer",
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
        key="ph_minus_concentration",
        translation_key="ph_minus_concentration",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.ph_minus_concentration,
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
        key="water_level",
        translation_key="water_level",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves",
        value_fn=lambda device: device.water_level,
    ),
    AsekoSensorEntityDescription(
        key="water_level_low_alarm",
        translation_key="water_level_low_alarm",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-down",
        value_fn=lambda device: device.water_level_low_alarm,
    ),
    AsekoSensorEntityDescription(
        key="water_level_filling_on",
        translation_key="water_level_filling_on",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-up",
        value_fn=lambda device: device.water_level_filling_on,
    ),
    AsekoSensorEntityDescription(
        key="water_level_filling_off",
        translation_key="water_level_filling_off",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-up",
        value_fn=lambda device: device.water_level_filling_off,
    ),
    AsekoSensorEntityDescription(
        key="water_level_high_alarm",
        translation_key="water_level_high_alarm",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:waves-arrow-up",
        value_fn=lambda device: device.water_level_high_alarm,
    ),
    AsekoSensorEntityDescription(
        key="max_filling_time",
        translation_key="max_filling_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer",
        value_fn=lambda device: device.max_filling_time,
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
    AsekoSensorEntityDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda device: device.last_seen,
    ),
    AsekoSensorEntityDescription(
        key="filtration_1_start",
        translation_key="filtration_1_start",
        icon="mdi:clock-start",
        value_fn=lambda device: (
            device.start1.strftime("%H:%M") if device.start1 is not None else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_1_stop",
        translation_key="filtration_1_stop",
        icon="mdi:clock-end",
        value_fn=lambda device: (
            device.stop1.strftime("%H:%M") if device.stop1 is not None else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_2_start",
        translation_key="filtration_2_start",
        icon="mdi:clock-start",
        value_fn=lambda device: (
            device.start2.strftime("%H:%M") if device.start2 is not None else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_2_stop",
        translation_key="filtration_2_stop",
        icon="mdi:clock-end",
        value_fn=lambda device: (
            device.stop2.strftime("%H:%M") if device.stop2 is not None else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="filtration_schedule",
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
        key="pool_volume",
        translation_key="pool_volume",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pool",
        value_fn=lambda device: device.pool_volume,
    ),
    AsekoSensorEntityDescription(
        key="delay_after_startup",
        translation_key="delay_after_startup",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-play-outline",
        value_fn=lambda device: device.delay_after_startup,
    ),
    AsekoSensorEntityDescription(
        key="delay_after_dose",
        translation_key="delay_after_dose",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda device: device.delay_after_dose,
    ),
    AsekoSensorEntityDescription(
        key="backwash_every_n_days",
        translation_key="backwash_every_n_days",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-refresh",
        value_fn=lambda device: device.backwash_every_n_days,
    ),
    AsekoSensorEntityDescription(
        key="backwash_time",
        translation_key="backwash_time",
        icon="mdi:clock-start",
        value_fn=lambda device: (
            device.backwash_time.strftime("%H:%M")
            if device.backwash_time is not None
            else None
        ),
    ),
    AsekoSensorEntityDescription(
        key="backwash_duration",
        translation_key="backwash_duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-sand",
        value_fn=lambda device: device.backwash_duration,
    ),
    # Observed backwash history.  All four are gated on _has_backwash rather
    # than on their own value, because they are unknown until a cycle has
    # actually been seen — see supported_fn.
    #
    # last_backwash is the *observed* one: the integration watched the backwash
    # valve stay open, so the cycle definitely happened.
    #
    # The scheduled/manual split is *derived* from it by a heuristic comparing
    # the start time against the configured schedule, and that heuristic can
    # get it wrong — the device never says why the valve opened.  Only the
    # timestamps stay exact.  "(estimated)" therefore marks just
    # next_scheduled_backwash, the one value that is calculated rather than
    # measured.  See backwash_tracker.BackwashTracker._classify.
    AsekoSensorEntityDescription(
        key="last_backwash",
        translation_key="last_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
        value_fn=lambda device: device.last_backwash,
        supported_fn=_has_backwash,
    ),
    # last_scheduled_backwash is not here: it is a writable datetime entity
    # (see datetime.py) so it can be set from the UI in one click, rather than
    # a read-only sensor plus a helper and a script to feed it.
    AsekoSensorEntityDescription(
        key="last_manual_backwash",
        translation_key="last_manual_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:hand-back-right-outline",
        value_fn=lambda device: device.last_manual_backwash,
        supported_fn=_has_backwash,
    ),
    AsekoSensorEntityDescription(
        # Renamed from "next_backwash" — see MIGRATED_UNIQUE_ID_SUFFIXES.
        key="next_scheduled_backwash",
        translation_key="next_scheduled_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-alert-outline",
        value_fn=lambda device: device.next_scheduled_backwash,
        supported_fn=_has_backwash,
        # No source attribute: this is always projected from
        # last_scheduled_backwash, so that sensor's source is this one's too.
    ),
]

# Sensor keys that were renamed after release.  The unique_id is
# f"{serial_number}{key}", so renaming a key orphans the registry entry: the
# old entity goes unavailable forever and a fresh one appears beside it under a
# new entity_id, losing its history.  async_migrate_unique_ids rewrites them at
# setup instead.  Old suffix → new suffix; entries are matched on the suffix
# because the serial number prefix varies per device.
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
    options=["online", "offline"],
    icon="mdi:lan-connect",
    value_fn=lambda device: "online" if device.online() else "offline",
)

# ---------- Setup ----------


@callback
def async_remove_retired_entities(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> None:
    """Delete registry entries for sensors that no longer exist.

    Runs before the entities are added, so a retired one never gets a
    chance to come back as unavailable.  A no-op once there is nothing
    left to remove.
    """
    registry = er.async_get(hass)

    for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id):
        if entry.domain != "sensor":
            continue
        if not any(
            entry.unique_id.endswith(suffix) for suffix in RETIRED_UNIQUE_ID_SUFFIXES
        ):
            continue
        _LOGGER.info(
            "Removing retired Aseko sensor %s (unique_id %s)",
            entry.entity_id,
            entry.unique_id,
        )
        registry.async_remove(entry.entity_id)


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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Aseko device sensors."""

    async_remove_retired_entities(hass, config_entry)
    async_migrate_unique_ids(hass, config_entry)

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices() or []
    _LOGGER.debug(
        ">>> [sensor] Found %s devices: %s",
        len(devices),
        [d.serial_number for d in devices],
    )

    entities: list[SensorEntity] = _build_sensor_entities(devices, coordinator)
    _LOGGER.debug(">>> [sensor] Adding %s sensors", len(entities))
    async_add_entities(entities)

    @callback
    def _async_add_new_device(device: AsekoDevice) -> None:
        new_entities = _build_sensor_entities([device], coordinator)
        if new_entities:
            _LOGGER.debug(
                ">>> [sensor] Adding %s sensors for new device %s",
                len(new_entities),
                device.serial_number,
            )
            async_add_entities(new_entities)

    config_entry.async_on_unload(
        coordinator.async_add_new_device_listener(_async_add_new_device)
    )


def _build_sensor_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
) -> list[SensorEntity]:
    """Create sensor entities for the given list of devices."""
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

            # Without a supported_fn, a value of None means "device does not
            # report this".  With one, the device decides presence and the
            # sensor may legitimately start out unknown.
            if description.supported_fn is not None:
                if not description.supported_fn(device):
                    _LOGGER.debug(
                        "   - Skipped unsupported sensor: %s",
                        key,
                    )
                    continue
            elif val is None:
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
