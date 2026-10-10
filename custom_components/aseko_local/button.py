"""Aseko Local canister-reset button entities."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AsekoLocalConfigEntry
from .coordinator import AsekoLocalDataUpdateCoordinator
from .entity import AsekoLocalEntity, async_setup_platform_entities
from .models import AsekoDevice
from .sensor import PUMP_RUNNING_ATTR, model_has_pump


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
    async_setup_platform_entities(
        hass, config_entry, async_add_entities, Platform.BUTTON, _build_button_entities
    )


def _build_button_entities(
    devices: list[AsekoDevice],
    coordinator: AsekoLocalDataUpdateCoordinator,
    features: frozenset[str] | None = None,
) -> list[ButtonEntity]:
    """Create button entities for the given devices.

    With ``features`` given, only the buttons for pumps in that set are
    built -- the ones a known device has just started showing.
    """
    entities: list[ButtonEntity] = []

    for device in devices:
        for description in RESET_BUTTONS:
            if not model_has_pump(device, description.pump_key):
                continue
            if (
                features is not None
                and PUMP_RUNNING_ATTR[description.pump_key] not in features
            ):
                continue
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
        """Set up the reset button of one pump counter of one unit."""
        super().__init__(
            unit,
            coordinator,
            description,
            feature=PUMP_RUNNING_ATTR[description.pump_key],
        )
        self._pump_key = description.pump_key

    async def async_press(self) -> None:
        """Reset the canister counter for this pump."""
        # this unit's canister only: other units in the entry keep theirs
        self.coordinator.reset_consumption(
            pump_key=self._pump_key,
            counter="canister",
            serial_number=self.device.serial_number,
        )
