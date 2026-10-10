"""Interfaces with the Aseko Local binary sensors."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AsekoLocalConfigEntry
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import (
    AsekoLocalEntity,
    async_remove_retired_platform_entities,
    async_setup_platform_entities,
)
from .models import AsekoDevice

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AsekoLocalBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Aseko device binary sensor entity."""

    value_fn: Callable[[AsekoDevice], bool | None]
    enabled: bool = True
    # The AsekoDevice field this sensor stands for; the entity exists when it
    # is in ``device.features``, and reads "unknown" while the value is None.
    feature: str = ""


BINARY_SENSORS: tuple[AsekoLocalBinarySensorEntityDescription, ...] = (
    AsekoLocalBinarySensorEntityDescription(
        key="water_flow_to_probes",
        feature="water_flow_to_probes",
        translation_key="water_flow_to_probes",
        icon="mdi:waves-arrow-right",
        value_fn=lambda device: device.water_flow_to_probes,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="electrolyzer_active",
        feature="electrolysis_running",
        translation_key="electrolysis_running",
        icon="mdi:lightning-bolt",
        value_fn=lambda device: device.electrolysis_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="pump_running",
        feature="filtration_running",
        translation_key="filtration_running",
        icon="mdi:pump",
        value_fn=lambda device: device.filtration_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="filtration_relay",
        feature="filtration_relay",
        translation_key="filtration_relay",
        icon="mdi:pump",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.filtration_relay,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="heating_active",
        feature="heating_running",
        translation_key="heating_running",
        icon="mdi:radiator",
        value_fn=lambda device: device.heating_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="heating_control_enabled",
        feature="heating_control_enabled",
        translation_key="heating_control_enabled",
        icon="mdi:thermostat",
        value_fn=lambda device: device.heating_control_enabled,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="heating_linked_to_filtration",
        feature="heating_linked_to_filtration",
        translation_key="heating_linked_to_filtration",
        icon="mdi:radiator",
        value_fn=lambda device: device.heating_linked_to_filtration,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="antifreeze_enabled",
        feature="freeze_protection_enabled",
        translation_key="freeze_protection_enabled",
        icon="mdi:snowflake-thermometer",
        value_fn=lambda device: device.freeze_protection_enabled,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="vsp_pump_running",
        feature="variable_speed_pump_enabled",
        translation_key="variable_speed_pump_enabled",
        icon="mdi:pump",
        value_fn=lambda device: device.variable_speed_pump_enabled,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="water_level_sensor_enabled",
        feature="water_level_sensor_enabled",
        translation_key="water_level_sensor_enabled",
        icon="mdi:waves-arrow-up",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.water_level_sensor_enabled,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="flow_detection_enabled",
        feature="flow_detection_enabled",
        translation_key="flow_detection_enabled",
        icon="mdi:waves-arrow-right",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.flow_detection_enabled,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="backwash_schedule_enabled",
        feature="backwash_schedule_enabled",
        translation_key="backwash_schedule_enabled",
        icon="mdi:calendar-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.backwash_schedule_enabled,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="heating_allowed",
        feature="heating_allowed",
        translation_key="heating_allowed",
        icon="mdi:radiator",
        value_fn=lambda device: device.heating_allowed,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="heating_condition_met",
        feature="heating_condition_met",
        translation_key="heating_condition_met",
        icon="mdi:thermostat",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.heating_condition_met,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="cl_pump_running",
        feature="chlorine_pump_running",
        translation_key="chlorine_pump_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.chlorine_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="ph_minus_pump_running",
        feature="ph_minus_pump_running",
        translation_key="ph_minus_pump_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.ph_minus_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="ph_plus_pump_running",
        feature="ph_plus_pump_running",
        translation_key="ph_plus_pump_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.ph_plus_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="algicide_pump_running",
        feature="algaecide_pump_running",
        translation_key="algaecide_pump_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.algaecide_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="floc_pump_running",
        feature="flocculant_pump_running",
        translation_key="flocculant_pump_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.flocculant_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="oxy_pump_running",
        feature="oxygen_pump_running",
        translation_key="oxygen_pump_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.oxygen_pump_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="water_filling_active",
        feature="refilling",
        translation_key="refilling",
        icon="mdi:water-plus",
        value_fn=lambda device: device.refilling,
    ),
    AsekoLocalBinarySensorEntityDescription(
        # byte[37] bit 0x04.  A device state, not a filtration one: while it
        # is on the unit sends nothing, so what is being done in there — to
        # filtration or anything else — cannot be seen from here.
        key="service_menu",
        feature="service_menu_open",
        translation_key="service_menu",
        icon="mdi:tune",
        value_fn=lambda device: device.service_menu_open,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="alarm_ph_too_many_doses",
        feature="alarm_ph_dosing_ineffective",
        translation_key="alarm_ph_dosing_ineffective",
        icon="mdi:alert",
        value_fn=lambda device: device.alarm_ph_dosing_ineffective,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="alarm_orp_too_many_doses",
        feature="alarm_max_disinfection_dose",
        translation_key="alarm_max_disinfection_dose",
        icon="mdi:alert",
        value_fn=lambda device: device.alarm_max_disinfection_dose,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="alarm_no_flow_to_probes",
        feature="alarm_no_flow_to_probes",
        translation_key="alarm_no_flow_to_probes",
        icon="mdi:waves-arrow-right",
        value_fn=lambda device: device.alarm_no_flow_to_probes,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="alarm_rapid_ph_change",
        feature="alarm_rapid_ph_change",
        translation_key="alarm_rapid_ph_change",
        icon="mdi:alert",
        value_fn=lambda device: device.alarm_rapid_ph_change,
    ),
    AsekoLocalBinarySensorEntityDescription(
        key="backwash_active",
        feature="backwash_running",
        translation_key="backwash_running",
        icon="mdi:water-pump",
        value_fn=lambda device: device.backwash_running,
    ),
    AsekoLocalBinarySensorEntityDescription(
        # The unit's clock is off Home Assistant's by at least the limit set
        # in the options (15 min by default); see trackers/clock.py.
        key="clock_out_of_sync",
        feature="unit_clock",
        translation_key="clock_out_of_sync",
        icon="mdi:clock-alert-outline",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.clock_out_of_sync,
    ),
)


# Binary sensor keys that no longer exist.  The unique_id is
# f"{serial_number}{key}", so a removed key leaves its registry entry
# behind: the entity would sit in the UI as unavailable forever, with no
# hint that it is not coming back.  async_remove_retired_entities deletes
# them at setup instead.  Suffixes, because the serial prefix varies.
RETIRED_UNIQUE_ID_SUFFIXES: frozenset[str] = frozenset(
    {
        # Superseded by sensor.filtration_schedule, which names the schedule
        # instead of answering only "nonstop or not" (Issue #133).
        "filtration_nonstop24",
    }
)


@callback
def async_remove_retired_entities(
    hass: HomeAssistant, config_entry: AsekoLocalConfigEntry
) -> None:
    """Delete registry entries for binary sensors that no longer exist.

    Runs before the entities are added, so the retired one never gets a
    chance to be restored as unavailable.

    Nothing happens when there is no matching entry, so this is a no-op on
    fresh installs and on every setup after the first.
    """
    async_remove_retired_platform_entities(
        hass, config_entry, Platform.BINARY_SENSOR, RETIRED_UNIQUE_ID_SUFFIXES
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Aseko device binary sensors."""

    async_remove_retired_entities(hass, config_entry)
    async_setup_platform_entities(
        hass,
        config_entry,
        async_add_entities,
        Platform.BINARY_SENSOR,
        _build_binary_sensor_entities,
    )


def _build_binary_sensor_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
    features: frozenset[str] | None = None,
) -> list[BinarySensorEntity]:
    """Create binary sensor entities for the given devices.

    With ``features`` given, only the entities for those fields are built --
    the ones a known device has just started showing.  Without it, every
    entity the device has, for a device seen for the first time.
    """
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

            if description.feature not in device.possible_features:
                _LOGGER.debug(
                    "   - Skipped binary sensor %s: not a feature of this unit", key
                )
                continue
            if features is not None and description.feature not in features:
                continue
            entity = AsekoLocalBinarySensorEntity(device, coordinator, description)
            entities.append(entity)
            _LOGGER.debug(
                "   - Regular binary sensor: %s (unique_id=%s)",
                key,
                entity.unique_id,
            )

    return entities


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
