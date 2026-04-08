"""Data model for Aseko pool devices."""

from dataclasses import dataclass, field, fields
from datetime import datetime, time, timedelta
from enum import Enum

import homeassistant.util


class AsekoDeviceType(Enum):
    """Enumeration of Aseko pool device types."""

    HOME = "ASIN AQUA Home"
    NET = "ASIN AQUA NET"
    OXY = "ASIN AQUA Oxygen"
    PROFI = "ASIN AQUA Profi"
    SALT = "ASIN AQUA Salt"


class AsekoProbeType(Enum):
    """Enumeration of Aseko Probes."""

    CLF = "clf"
    CLT = "clt"
    DOSE = "dose"
    PH = "ph"
    REDOX = "redox"
    OXY = "oxy"


class AsekoElectrolyzerDirection(Enum):
    """Enumeration of Aseko Electrolyzer direction."""

    LEFT = "left"
    RIGHT = "right"
    WAITING = "waiting"


class AsekoThirdPumpSlot:
    """Semantics of byte[37] differ by device type.

    SALT (shared physical port): routing indicator.
        Bit 7 (0x80) set → algicide configured in the single port.
        Bit 7 (0x80) clear → flocculant configured.
        Confirmed by @hopkins-tk (SALT v7.x frames, 2025) and consistent with
        @jmnemonicj (SALT v5.0, Issue #84) where 0x03 & 0x80 == 0 → flocculant.

    OXY (two independent ports): suspected pump-presence bitmap.
        Bit 0 (0x01) = flocculant pump module connected.  # unconfirmed hypothesis
        Bit 1 (0x02) = algicide pump module connected.    # unconfirmed hypothesis
        Observed 0x03 on Winnetoux's OXY (both pumps present). Requires a frame
        with only one pump connected to confirm.
        TODO: confirm OXY semantics with an asymmetric frame.

    NET / PROFI / HOME: 0xFF (UNSPECIFIED) = no third-pump port, routing not applicable.
    """

    # SALT: bit 7 → algicide in the shared port; clear → flocculant
    SALT_ALGICIDE_ROUTING: int = 0x80

    # OXY: presence bits – which pump modules are physically connected.
    # UNCONFIRMED: based solely on the single observed value 0x03 (both present).
    OXY_FLOC_PRESENT: int = 0x01
    OXY_ALGICIDE_PRESENT: int = 0x02


@dataclass(frozen=True)
class AsekoActuatorMasks:
    """Byte 29 bit masks for actuator state detection (pumps + electrolyzer), per device type."""

    filtration: int = 0x00
    cl: int = 0x00
    ph_minus: int = 0x00
    algicide: int = 0x00
    flocculant: int = 0x00
    electrolyzer_running: int = 0x00
    electrolyzer_running_right: int = 0x00
    electrolyzer_running_left: int = 0x00
    # On devices with a single shared physical pump port (SALT and similar 2–3-pump
    # units), byte[37] carries a routing indicator: bit 7 set → algicide setpoint;
    # clear → flocculant setpoint (AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING).
    # Devices with 4+ independent pump ports (OXY, HOME, PROFI) do NOT use this
    # routing — algicide and flocculant have separate physical connections whose
    # setpoint byte positions are not yet confirmed from frames.
    # Set False for those devices so decode() skips the routing logic entirely.
    byte37_routes_pump_type: bool = True


ACTUATOR_MASKS: dict[AsekoDeviceType, AsekoActuatorMasks] = {
    AsekoDeviceType.OXY: AsekoActuatorMasks(
        filtration=0x08,  # confirmed: all captured frames
        flocculant=0x20,  # confirmed: toggles exactly at 19:33:52 floc event
        # algicide=0x10    unconfirmed – awaiting frame with algicide running
        # ph_minus=0x80    unconfirmed – awaiting frame with pH− running
        # cl=0x40          unconfirmed – awaiting frame with OXY Pure pump running
        byte37_routes_pump_type=False,  # OXY byte[37] = pump-presence bitmap, not routing
    ),
    AsekoDeviceType.NET: AsekoActuatorMasks(
        # Aqua NET has no filtration output — confirmed: Issue #66
        cl=0x02,  # confirmed: Issue #66 (Aqua NET)
        ph_minus=0x01,  # confirmed: Issue #66 (Aqua NET)
    ),
    AsekoDeviceType.SALT: AsekoActuatorMasks(
        filtration=0x08,  # confirmed: April 4, 2026 – set in all active phases (PR #87)
        ph_minus=0x80,  # unconfirmed – no frame captured with pH− pump running
        # SALT third-pump slot: one physical pump, configured as algicide OR flocculant.
        # Both chemicals use the same bit: byte[29] bit 5 (0x20) when running.
        # Routing: byte[37] & 0x80 set = algicide; clear = flocculant.
        # Confirmed by @hopkins-tk 2026-04-04: 27 algicide frames (no electrolyzer) → 0x28=0x08|0x20 (PR #87).
        algicide=0x20,  # confirmed: 27 frames, PR #87
        flocculant=0x20,  # confirmed: Apr 3 frames, same bit as algicide
        electrolyzer_running=0x10,  # confirmed: 25 frames → 0x18=0x08|0x10 (PR #87)
        electrolyzer_running_right=0x10,  # confirmed: same dataset
        electrolyzer_running_left=0x50,  # tentative: Apr 2 single frame 0x58=0x08|0x10|0x40
    ),
    AsekoDeviceType.HOME: AsekoActuatorMasks(
        filtration=0x08,  # uncertain
        cl=0x40,  # uncertain
        ph_minus=0x80,  # uncertain
        algicide=0x20,  # uncertain
        flocculant=0x20,  # uncertain
        byte37_routes_pump_type=False,  # HOME has 4 independent pump ports (cl, ph-, alg, floc)
    ),
    AsekoDeviceType.PROFI: AsekoActuatorMasks(
        filtration=0x08,  # uncertain
        cl=0x40,  # uncertain
        ph_minus=0x80,  # uncertain
        flocculant=0x20,  # uncertain
        byte37_routes_pump_type=False,  # PROFI has 5 independent pump ports (cl, ph-, ph+, alg, floc)
    ),
}


@dataclass
class AsekoDevice:
    """Holds data received from Aseko device."""

    device_type: AsekoDeviceType | None = None  # byte 4-7?
    configuration: set[AsekoProbeType] = field(default_factory=set)

    serial_number: int | None = None  # byte 0 - 4
    timestamp: datetime | None = None  # byte 6 - 11
    ph: float | None = None  # byte 14 & 15
    cl_free: float | None = None  # byte 16 & 17
    cl_free_mv: int | None = None  # for NET - free chlorine millivolts (byte 20 & 21)
    redox: int | None = None  # byte 16 & 17 or 18 & 19
    salinity: float | None = None  # byte 20
    electrolyzer_power: int | None = None  # byte 21
    electrolyzer_active: bool | None = None  # byte 29 (4-th bit)
    electrolyzer_direction: AsekoElectrolyzerDirection | None = (
        None  # byte 29 (6-th bit for LEFT)
    )
    water_temperature: float | None = None  # byte 25 & 26
    water_flow_to_probes: bool | None = None  # byte 28 == aah
    filtration_pump_running: bool | None = None  # byte 29 (3-rd bit)
    cl_pump_running: bool | None = None  # byte 29 (6-th bit)
    ph_minus_pump_running: bool | None = None  # byte 29 (7-th bit)
    ph_plus_pump_running: bool | None = (
        None  # byte 29 (unknown - 7-th bit for all except PROFI?)
    )
    algicide_pump_running: bool | None = (
        None  # byte 29 bit 4 (0x10) on SALT; uncertain on other types
    )
    floc_pump_running: bool | None = None  # byte 29 bit 5 (0x20)

    # NEW: flow rates (bytes 95, 97, 99, 101)
    flowrate_chlor: int | None = None
    flowrate_ph_minus: int | None = None
    flowrate_ph_plus: int | None = None

    # algicide/flocculant based on byte 37: bit 0x80 set = algicide, 0 = flocculant, 0xFF = undefined
    flowrate_algicide: int | None = None
    flowrate_floc: int | None = None

    required_ph: float | None = None  # byte 52/10
    required_redox: int | None = None  # byte 53*10
    required_cl_free: float | None = None  # byte 53/10 mg/L
    required_oxy_dose: int | None = None  # byte 53 raw ml/m³/day – OXY Pure device only
    required_cl_dose: int | None = (
        None  # byte 53 raw ml/m³/h – DOSE mode (volume-based Cl dosing)
    )

    # algicide/flocculant based on byte 37: bit 0x80 set = algicide, 0 = flocculant, 0xFF = undefined
    required_algicide: int | None = None  # byte 54
    required_floc: int | None = None  # byte 54

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
