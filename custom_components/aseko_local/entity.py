"""Aseko Local Entity."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aseko_data import AsekoDevice
from .const import DOMAIN, MANUFACTURER
from .coordinator import AsekoLocalDataUpdateCoordinator


class AsekoLocalEntity(CoordinatorEntity[AsekoLocalDataUpdateCoordinator]):
    """Representation of an Aseko Local Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        unit: AsekoDevice,
        coordinator: AsekoLocalDataUpdateCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the Aseko Local Entity."""

        super().__init__(coordinator)

        self.entity_description = description

        self.device = unit
        self._attr_unique_id = (
            f"{self.device.serial_number}{self.entity_description.key}"
        )
        model = self.device.device_type.value if self.device.device_type is not None else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.device.serial_number))},
            serial_number=str(self.device.serial_number),
            name=f"{MANUFACTURER} {model} - {self.device.serial_number}",
            manufacturer=MANUFACTURER,
            model=model,
            configuration_url=f"https://aseko.cloud/unit/{self.device.serial_number}",
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""

        return super().available and self.device.online()
