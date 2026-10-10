"""Aseko Local Entity.

Every quantity a model can have gets an entity, whether this unit has shown
it or not, so an accessory fitted later (a level sensor, an air probe, the
shared pump port routed to the other chemical) does not need a new set-up
and one removed later does not lose its history:

* an entity for a quantity the unit has not shown since Home Assistant
  started is created **disabled**; when the quantity first arrives the
  platform enables it, and Home Assistant reloads the entry to add it;
* an enabled entity whose quantity the last frame did not show present is
  **unavailable** -- the accessory is not fitted (any more), the port is
  routed elsewhere, or the frame could not say.  The diagnostics download
  lists those fields under ``not_present_now``.

A description with ``entity_registry_enabled_default=False`` (a decoded value
next to its derived one, see ``decoding.derived``) stays disabled until a
user enables it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import AsekoLocalDataUpdateCoordinator
from .models import AsekoDevice, AsekoProfileFlag

if TYPE_CHECKING:
    from homeassistant.const import Platform
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import AsekoLocalConfigEntry

_LOGGER = logging.getLogger(__name__)

#: Builds a platform's entities for some devices; with ``features``, only the
#: entities for those fields (the ones a known device has just started showing).
type EntityBuilder = Callable[
    [list[AsekoDevice], AsekoLocalDataUpdateCoordinator, frozenset[str] | None],
    list[Entity],
]

# ``feature`` left at this default is read off the entity description.
_FROM_DESCRIPTION = object()

#: The algicide port's entities, named "Algicide / ACO" on a unit whose port
#: doses either (AsekoProfileFlag.ALGICIDE_OR_ACO) under ``<key>_or_aco``.
ALGICIDE_TRANSLATION_KEYS = frozenset(
    {
        "algaecide_pump_running",
        "algaecide_dose_target",
        "algicide_consumed",
        "algicide_total_consumed",
        "algicide_refill_reset",
    }
)


class AsekoLocalEntity(CoordinatorEntity[AsekoLocalDataUpdateCoordinator]):
    """Representation of an Aseko Local Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        unit: AsekoDevice,
        coordinator: AsekoLocalDataUpdateCoordinator,
        description: EntityDescription,
        feature: str | None | object = _FROM_DESCRIPTION,
    ) -> None:
        """Initialize the Aseko Local Entity.

        ``feature`` is the AsekoDevice field the entity stands for (None: one
        every unit has); by default the description's ``feature``.
        """

        super().__init__(coordinator)

        self.entity_description = description
        self._feature: str | None = (
            getattr(description, "feature", None)
            if feature is _FROM_DESCRIPTION
            else feature  # type: ignore[assignment]
        )

        self.device = unit
        if (
            AsekoProfileFlag.ALGICIDE_OR_ACO in unit.flags
            and description.translation_key in ALGICIDE_TRANSLATION_KEYS
        ):
            self._attr_translation_key = f"{description.translation_key}_or_aco"
        self._attr_unique_id = (
            f"{self.device.serial_number}{self.entity_description.key}"
        )
        # Disabled until the unit shows the quantity; see the module docstring.
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
            and (self._feature is None or self._feature in unit.features)
        )
        model = (
            self.device.device_type.value
            if self.device.device_type is not None
            else None
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.device.serial_number))},
            serial_number=str(self.device.serial_number),
            name=f"{MANUFACTURER} {model} - {self.device.serial_number}",
            manufacturer=MANUFACTURER,
            model=model,
            configuration_url=f"https://aseko.cloud/unit/{self.device.serial_number}",
        )

    @property
    def feature(self) -> str | None:
        """The AsekoDevice field this entity stands for, if any."""
        return self._feature

    @property
    def available(self) -> bool:
        """Unavailable while the coordinator is, or the quantity is not present now."""
        if not super().available:
            return False
        return self._feature is None or self._feature in self.device.present_features


@callback
def async_enable_entities(
    hass: HomeAssistant, platform: str, unique_ids: Iterable[str]
) -> None:
    """Enable entities this integration created disabled, now that their quantity arrived.

    Only entities disabled by the integration are touched -- one a user
    disabled stays disabled.  Home Assistant reloads the entry shortly after
    an entity is enabled, which is what adds it.
    """
    registry = er.async_get(hass)
    for unique_id in unique_ids:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
        if entity_id is None:
            continue
        entry = registry.async_get(entity_id)
        if (
            entry is not None
            and entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        ):
            registry.async_update_entity(entity_id, disabled_by=None)


def enabled_unique_ids(entities: Iterable[Any]) -> list[str]:
    """Return the unique ids of the entities this unit's features enable by default."""
    return [
        e.unique_id
        for e in entities
        if e.unique_id and getattr(e, "entity_registry_enabled_default", True)
    ]


@callback
def async_remove_retired_platform_entities(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    platform: Platform,
    retired_suffixes: frozenset[str],
) -> None:
    """Delete this entry's registry entries for keys the platform no longer has.

    The unique_id is f"{serial_number}{key}", so a removed key leaves its
    registry entry behind and the entity sits in the UI as unavailable
    forever.  Matched on the suffix, because the serial prefix varies.  Runs
    before the entities are added; a no-op once nothing is left to remove.
    """
    registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id):
        if entry.domain != platform:
            continue
        if not any(entry.unique_id.endswith(suffix) for suffix in retired_suffixes):
            continue
        _LOGGER.info(
            "Removing retired Aseko %s %s (unique_id %s)",
            platform,
            entry.entity_id,
            entry.unique_id,
        )
        registry.async_remove(entry.entity_id)


@callback
def async_setup_platform_entities(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    platform: Platform,
    build: EntityBuilder,
) -> None:
    """Add a platform's entities now, and for units and features seen later.

    Every platform sets up the same way: the entities of the known devices,
    enabled where the unit shows the quantity; then one listener adds a new
    unit's entities and another enables those a known unit has just started
    showing (they exist already, created disabled -- see the module docstring).
    Both listeners are removed when the entry unloads.
    """
    coordinator = config_entry.runtime_data.coordinator
    entities = build(coordinator.get_devices(), coordinator, None)
    _LOGGER.debug("%s: adding %s entities", platform, len(entities))
    async_add_entities(entities)
    async_enable_entities(hass, platform, enabled_unique_ids(entities))

    @callback
    def _add_new_device(device: AsekoDevice) -> None:
        new_entities = build([device], coordinator, None)
        async_enable_entities(hass, platform, enabled_unique_ids(new_entities))
        if new_entities:
            _LOGGER.debug(
                "%s: adding %s entities for new device %s",
                platform,
                len(new_entities),
                device.serial_number,
            )
            async_add_entities(new_entities)

    @callback
    def _add_new_features(device: AsekoDevice, features: frozenset[str]) -> None:
        grown = build([device], coordinator, features)
        async_enable_entities(
            hass, platform, [e.unique_id for e in grown if e.unique_id]
        )

    config_entry.async_on_unload(
        coordinator.async_add_new_device_listener(_add_new_device)
    )
    config_entry.async_on_unload(
        coordinator.async_add_new_features_listener(_add_new_features)
    )
