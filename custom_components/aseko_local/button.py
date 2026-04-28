"""Aseko Local canister-reset button entities."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AsekoLocalConfigEntry
from .aseko_data import AsekoDevice, ACTUATOR_MASKS
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import AsekoLocalEntity
from .sensor import PUMP_MASK_FIELD, PUMP_RUNNING_ATTR


@dataclass(frozen=True, kw_only=True)
class AsekoResetButtonEntityDescription(ButtonEntityDescription):
    """Describes a canister-reset button entity."""

    pump_key: str = ""


RESET_BUTTONS: list[AsekoResetButtonEntityDescription] = [
    AsekoResetButtonEntityDescription(
        key="chlor_refill_reset",
        translation_key="chlor_refill_reset",
        icon="mdi:cup-water",
        pump_key="cl",
    ),
    AsekoResetButtonEntityDescription(
        key="ph_minus_refill_reset",
        translation_key="ph_minus_refill_reset",
        icon="mdi:cup-water",
        pump_key="ph_minus",
    ),
    AsekoResetButtonEntityDescription(
        key="ph_plus_refill_reset",
        translation_key="ph_plus_refill_reset",
        icon="mdi:cup-water",
        pump_key="ph_plus",
    ),
    AsekoResetButtonEntityDescription(
        key="algicide_refill_reset",
        translation_key="algicide_refill_reset",
        icon="mdi:cup-water",
        pump_key="algicide",
    ),
    AsekoResetButtonEntityDescription(
        key="floc_refill_reset",
        translation_key="floc_refill_reset",
        icon="mdi:cup-water",
        pump_key="floc",
    ),
    AsekoResetButtonEntityDescription(
        key="oxy_refill_reset",
        translation_key="oxy_refill_reset",
        icon="mdi:cup-water",
        pump_key="oxy",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up canister-reset button entities for each active chemical pump."""

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices()
    entities = _build_button_entities(devices, coordinator)
    async_add_entities(entities)

    @callback
    def _async_add_new_device(device: AsekoDevice) -> None:
        new_entities = _build_button_entities([device], coordinator)
        if new_entities:
            async_add_entities(new_entities)

    config_entry.async_on_unload(
        coordinator.async_add_new_device_listener(_async_add_new_device)
    )


def _build_button_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
) -> list[ButtonEntity]:
    """Create button entities for the given list of devices."""
    entities: list[ButtonEntity] = []

    for device in devices:
        device_masks = (
            ACTUATOR_MASKS.get(device.device_type) if device.device_type else None
        )
        for description in RESET_BUTTONS:
            mask_field = PUMP_MASK_FIELD[description.pump_key]
            if mask_field is None:
                continue  # pump byte position not yet confirmed (e.g. ph_plus)
            if device_masks is None or getattr(device_masks, mask_field, 0) == 0:
                continue  # pump not configured for this device type
            running_attr = PUMP_RUNNING_ATTR.get(description.pump_key)
            if running_attr and getattr(device, running_attr, None) is None:
                continue  # decoder determined pump absent on this specific unit
            entities.append(AsekoResetButtonEntity(device, coordinator, description))

    return entities


class AsekoResetButtonEntity(AsekoLocalEntity, ButtonEntity):
    """Pressing this button resets the canister consumption counter for one pump."""

    def __init__(
        self,
        unit: AsekoDevice,
        coordinator: AsekoLocalDataUpdateCoordinator,
        description: AsekoResetButtonEntityDescription,
    ) -> None:
        super().__init__(unit, coordinator, description)
        self._pump_key = description.pump_key

    async def async_press(self) -> None:
        """Reset the canister counter for this pump."""
        self.coordinator.reset_consumption(pump_key=self._pump_key, counter="canister")
