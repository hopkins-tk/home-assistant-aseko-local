"""Aseko Local Entity."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aseko_data import AsekoUnitData
from .const import DOMAIN, MANUFACTURER
from .coordinator import AsekoLocalDataUpdateCoordinator


class AsekoLocalEntity(CoordinatorEntity[AsekoLocalDataUpdateCoordinator]):
    """Representation of an Aseko Local Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        unit: AsekoUnitData,
        coordinator: AsekoLocalDataUpdateCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the Aseko Local Entity."""

        super().__init__(coordinator)

        self.entity_description = description

        self.unit = unit
        self._attr_unique_id = f"{self.unit.serial_number}{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unit.serial_number)},
            serial_number=self.unit.serial_number,
            name=f"{MANUFACTURER} {self.unit.type.value} - {self.unit.serial_number}",
            manufacturer=MANUFACTURER,
            model=self.unit.type.value,
            configuration_url=f"https://aseko.cloud/unit/{self.unit.serial_number}",
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""

        return super().available and self.unit.online()
