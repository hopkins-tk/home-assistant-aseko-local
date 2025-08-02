"""Data model for Aseko pool devices."""

from dataclasses import dataclass, field, fields
from datetime import datetime, time, timedelta
from enum import Enum

import homeassistant.util


class AsekoDeviceType(Enum):
    """Enumeration of Aseko pool device types."""

    HOME = "ASIN AQUA Home"
    NET = "ASIN AQUA NET"
    PROFI = "ASIN AQUA Profi"
    SALT = "ASIN AQUA Salt"


class AsekoProbeType(Enum):
    """Enumeration of Aseko Probes."""

    CLF = "clf"
    CLT = "clt"
    DOSE = "dose"
    PH = "ph"
    REDOX = "redox"
    SANOSIL = "sanosil"


class AsekoElectrolyzerDirection(Enum):
    """Enumeration of Aseko Electrolyzer direction."""

    LEFT = "left"
    RIGHT = "right"
    WAITING = "waiting"


@dataclass
class AsekoDevice:
    """Holds data received from Aseko device."""

    type: AsekoDeviceType | None = None  # byte 4-7?

    serial_number: int | None = None  # byte 0 - 4
    timestamp: datetime | None = None  # byte 6 - 11
    ph: float | None = None  # byte 14 & 15
    cl_free: float | None = None  # byte 16 & 17
    redox: int | None = None  # byte 18 & 19
    salinity: float | None = None  # byte 20
    electrolyzer_power: int | None = None  # byte 21
    electrolyzer_active: bool | None = None  # byte 29 (4-th bit)
    electrolyzer_direction: AsekoElectrolyzerDirection | None = (
        None  # byte 29 (6-th bit for LEFT)
    )
    water_temperature: float | None = None  # byte 25 & 26
    water_flow_to_probes: bool | None = None  # byte 28 == aah
    pump_running: bool | None = None  # byte 29 (3-rd bit)

    required_ph: float | None = None  # byte 52/10
    required_redox: int | None = None  # byte 53*10
    required_cl_free: float | None = None  # byte 53*10?
    required_algicide: int | None = None  # byte 54
    required_water_temperature: int | None = None  # byte 55

    start1: time | None = None  # byte 56 & 57
    stop1: time | None = None  # byte 58 & 59
    start2: time | None = None  # byte 60 & 61
    stop2: time | None = None  # byte 62 & 63

    backwash_every_n_days: int | None = None  # byte 68
    backwash_time: time | None = None  # byte 69 & 70
    backwash_duration: int | None = None  # byte 71

    pool_volume: int | None = None  # byte 92 & 93
    max_filling_time: int | None = None  # byte 94

    air_temperature: float | None = None
    delay_after_dose: int | None = None  # byte 107 & 108 ? (seconds)
    delay_after_startup: int | None = None  # byte 74 & 75 (seconds)

    def online(self) -> bool:
        """Check if the device is online."""
        return self.timestamp is not None and self.timestamp > datetime.now(
            tz=homeassistant.util.dt.get_default_time_zone()
        ) - timedelta(seconds=20)


@dataclass
class AsekoData:
    """Holds a mapping of serial numbers to Aseko devices."""

    devices: dict[int, AsekoDevice] = field(default_factory=dict)

    def _copy_attributes(self, src: AsekoDevice, dest: AsekoDevice) -> None:
        for f in fields(AsekoDevice):
            setattr(dest, f.name, getattr(src, f.name))

    def get_all(self) -> list[AsekoDevice] | None:
        """Return the list of Aseko devices."""
        return list(self.devices.values())

    def get(self, serial_number: int) -> AsekoDevice | None:
        """Return the Aseko device for a given serial number, or None if not found."""
        return self.devices.get(serial_number)

    def set(self, serial_number: int, value: AsekoDevice) -> None:
        """Set the Aseko device for a given serial number."""

        if serial_number in self.devices:
            self._copy_attributes(value, self.devices[serial_number])
        else:
            self.devices[serial_number] = value
