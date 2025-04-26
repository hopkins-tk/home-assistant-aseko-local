"""Data model for Aseko pool devices."""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum


class AsekoDeviceType(Enum):
    """Enumeration of Aseko pool device types."""

    AQUA_NET = "ASIN AQUA NET"
    HOME = "ASIN AQUA Home"
    PRO = "ASIN AQUA Pro"
    PROFI = "ASIN AQUA Profi"
    SALT = "ASIN AQUA Salt"


@dataclass
class AsekoUnitData:
    """Holds data received from Aseko pool device."""

    # 4 bit ,1' aqua NET
    # 5 bit ,1' salt
    # 6 bit ,1' home
    # 7 bit ,1' profi
    type: AsekoDeviceType = None  # byte 4-7

    serial_number: int = None  # byte 0 - 4
    timestamp: datetime = None  # byte 6 - 11
    ph: float = None  # byte 14 & 15
    cl_free: int = None  # byte 16 & 17
    redox: int = None  # byte 18 & 19
    salinity: float = None  # byte 20
    electrolyzer: int = None  # byte 21
    water_temperature: float = None  # byte 25 & 26
    water_flow_to_probes: bool = None  # byte 28 == aah

    required_ph: float = None  # byte 52/10
    required_redox: int = None  # byte 53*10
    required_cl_free: int = None  # byte 53*10?
    required_algicide: int = None  # byte 54
    required_temperature: int = None  # byte 55

    start1: time = None  # byte 56 & 57
    stop1: time = None  # byte 58 & 59
    start2: time = None  # byte 60 & 61
    stop2: time = None  # byte 62 & 63

    pool_volume: int = None  # byte 92 & 93

    error_1: int = None
    error_2: int = None
    air_temperature: float = None
    power_active: bool = None
    power_direction: str = None
    required_flocc: float = None
    delay: int = None  # byte 30 & 31 ?
    delay_startup: int = None  # byte 74 & 75 ?

    def online(self) -> bool:
        """Check if the device is online."""
        return self.timestamp > datetime.now() - timedelta(seconds=20)


@dataclass(slots=True)
class AsekoData:
    """Hold a mapping of serial numbers to AsekoData."""

    units: dict[int, AsekoUnitData] = field(default_factory=dict)

    def get_all(self) -> list[AsekoUnitData] | None:
        """Return the AsekoData for all units."""
        return self.units.values()

    def get(self, serial_number: int) -> AsekoUnitData | None:
        """Return the AsekoData for a given serial number, or None if not found."""
        return self.units.get(serial_number)

    def set(self, serial_number: int, value: AsekoUnitData) -> None:
        """Set the AsekoData for a given serial number."""
        self.units[serial_number] = value
