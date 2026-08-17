"""Data model for Aseko pool devices.

This module defines the **protocol-agnostic target schema** (``AsekoDevice``)
that the entity layer (sensors, binary sensors, buttons, …) consumes.  It
also defines the device-type enum, the probe-type enum, the electrolyser
direction enum, and the filtration-mode enum.

Decoder-specific byte-level knowledge (v7 ``byte[29]`` masks, v8 ``fncs:``
capability codes, ``byte[37]`` routing constants, etc.) lives in
``aseko_v7_helpers.py`` and ``aseko_v8_helpers.py`` next to the corresponding
decoder.  The v7 constants ``AsekoActuatorMasks``, ``ACTUATOR_MASKS``, and
``AsekoThirdPumpSlot`` are re-exported at the bottom of this file for
backwards compatibility with existing import sites.
"""

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


class AsekoFiltrationMode(Enum):
    """Enumeration of the 4 filtration schedule states.

    Surfaced by the new `filtration_mode` sensor (Issue #133) and used
    internally to override `filtration_pump_running` when the user has
    manually switched the pump off on a HOME v7 device (firmware B).

    Enum values map directly to the translation keys in
    translations/{en,de,cs,fr}.json under entity.sensor.filtration_mode.state.
    """

    NONSTOP_24H = "nonstop_24h"
    TIMER_PERIOD_1 = "timer_period_1"
    TIMER_PERIOD_1_AND_2 = "timer_period_1_and_2"
    MANUAL = "off_manual"


# ---------------------------------------------------------------------------
# Re-exports for backwards compatibility
# ---------------------------------------------------------------------------
#
# ``AsekoActuatorMasks``, ``ACTUATOR_MASKS``, and ``AsekoThirdPumpSlot`` are
# **v7-decoder specific** (byte[29] bit masks, byte[37] routing constants).
# They used to live in this module, but they belong in ``aseko_v7_helpers.py``
# next to the v7 decoder.  We re-export them here so existing import sites
# (``aseko_decoder.py``, ``button.py``, ``sensor.py``, …) keep working without
# a global rename.  New code should import them from ``aseko_v7_helpers`` directly.
from .aseko_v7_helpers import (  # noqa: E402, F401
    ACTUATOR_MASKS,
    AsekoActuatorMasks,
    AsekoByte37Masks,
    AsekoThirdPumpSlot,
)


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
    heating_active: bool | None = None  # byte 29 (2-nd bit, 0x04)
    heating_control_enabled: bool | None = None  # byte 37 bit 3 (0x08) on HOME
    antifreeze_enabled: bool | None = None  # byte 37 bit 7 (0x80) on HOME
    vsp_pump_running: bool | None = None  # byte 22 bit 3 (0x08) on HOME
    ph_minus_concentration: int | None = None  # byte 112 (%) on HOME (Issue #139)
    cl_pump_running: bool | None = None  # byte 29 (6-th bit)
    ph_minus_pump_running: bool | None = None  # byte 29 (7-th bit)
    ph_plus_pump_running: bool | None = (
        None  # byte 29 (unknown - 7-th bit for all except PROFI?)
    )
    algicide_pump_running: bool | None = (
        None  # byte 29 bit 4 (0x10) on SALT; uncertain on other types
    )
    floc_pump_running: bool | None = None  # byte 29 bit 5 (0x20)
    oxy_pump_running: bool | None = (
        None  # byte 29 bit unconfirmed – OXY Pure device only
    )

    # NEW: flow rates (bytes 95, 97, 99, 101)
    flowrate_chlor: int | None = None
    flowrate_ph_minus: int | None = None
    flowrate_ph_plus: int | None = None
    flowrate_oxy: int | None = (
        None  # byte 99 on OXY Pure device (same slot as flowrate_chlor)
    )

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

    # Backwash running state — byte [29] bit 0x01
    # True while the backwash valve relay is currently energized.
    # NOTE: bit 0x01 is the backwash relay across all device types that
    # have a backwash valve (HOME, SALT, OXY).  NET has no backwash output.
    # The mapping is the same one JS-DE-Tech uses for `relay_byte` bit 0
    # ("backwash" relay).  Live confirmation is still pending — see
    # docs/temp/byte29_salt_pump_masks_analysis.md for context.
    backwash_active: bool | None = None

    pool_volume: int | None = None  # byte 92 & 93
    max_filling_time: int | None = None  # byte 94

    air_temperature: float | None = None

    # Water level
    water_level: int | None = None  # byte [27] (cm, real-time)
    water_level_low_alarm: int | None = None  # byte [102] (cm, config)
    water_level_filling_on: int | None = None  # byte [103] (cm, config)
    water_level_filling_off: int | None = None  # byte [104] (cm, config)
    water_level_high_alarm: int | None = None  # byte [105] (cm, config)

    # Water filling active — byte [29] bit 0x02
    water_filling_active: bool | None = None

    # Filtration mode — byte [37]
    # True = nonstop 24 h (0x43), False = timer (0x53), None = transitional/unknown
    filtration_nonstop24: bool | None = None

    # Filtration mode — 4-state enum (Issue #133).
    # Set for every device type in FILTRATION_TYPES = {SALT, HOME, OXY, PROFI}.
    # NET is excluded — no filtration output (see Issue #66).
    #
    # Every device type in FILTRATION_TYPES encodes the 4-state mode directly
    # in byte[37] with two firmware variants:
    #   Firmware A (serial 110128063, byte 4 = 0x02): high nibble 0x4 / 0x5
    #     0x43 → NONSTOP_24H
    #     0x53 → TIMER_PERIOD_1_AND_2 (cannot distinguish P1 vs P1&P2)
    #     0x47 / 0x57 → leave as None (transitional edit state)
    #   Firmware B (serial 110169464, byte 4 = 0x03): high nibble 0x0 / 0x1 / 0x3
    #     0x01 → NONSTOP_24H
    #     0x11 → TIMER_PERIOD_1
    #     0x31 → TIMER_PERIOD_1_AND_2
    #     0x15 → MANUAL (P1 + manual override, bit 0x04 set)
    #     0x35 → MANUAL (P1&P2 + manual override, bit 0x04 set)
    #
    # This guarantees that a single `filtration_mode` sensor shows the
    # same 4 states on every filtration-capable device.
    filtration_mode: AsekoFiltrationMode | None = None

    # Alarm/error bitmasks — bytes [12] (HOME dosing warnings) and [13]
    # byte [12] 0x20 = chlorine/disinfection dosing warning (HOME ✅, issue #134)
    # byte [12] 0x40 = pH dosing warning (HOME ✅, issue #134)
    # byte [13] 0x01 = disinfection/ORP dose fault (Issue #151, HOME serial 110175608;
    #                  config48 frame byte[13]=0x01 during "Maximum disinfection dose
    #                  exceeded" — same fault as v8 ins[12] bit 0x80)
    # byte [13] 0x02 = pH dose fault (inferred, symmetric to 0x01 — no direct capture yet)
    # byte [13] 0x04 = no flow to probes (confirmed)
    # byte [13] 0x08 = rapid pH change (error_codes.md, unconfirmed by capture)
    alarm_ph_too_many_doses: bool | None = None  # byte [13] 0x02 | byte [12] 0x40
    alarm_orp_too_many_doses: bool | None = None  # byte [13] 0x01 | byte [12] 0x20
    alarm_no_flow_to_probes: bool | None = None  # byte [13] bit 0x04 (confirmed)
    alarm_rapid_ph_change: bool | None = (
        None  # byte [13] bit 0x08 (error_codes.md, unconfirmed by capture)
    )

    delay_after_dose: int | None = None  # byte 107 & 108 ? (seconds)
    delay_after_startup: int | None = None  # byte 74 & 75 (seconds)

    # Computed backwash schedule (derived from backwash_time + backwash_every_n_days + timestamp).
    # last_backwash = most recent daily occurrence of backwash_time at or before
    #                  the frame timestamp.  After the first detected backwash
    #                  cycle, the BackwashTracker in coordinator.py overrides
    #                  this with a real observed timestamp (persistent across
    #                  restarts).  See custom_components/aseko_local/backwash_tracker.py.
    # next_backwash = last_backwash + backwash_every_n_days days.
    last_backwash: datetime | None = None
    next_backwash: datetime | None = None

    # Server-side receive timestamp – set by the coordinator on every incoming frame.
    # Independent of the device clock (which can be wrong or missing on some models).
    last_seen: datetime | None = None

    def online(self) -> bool:
        """Return True if a frame was received within the last 60 seconds."""
        return self.last_seen is not None and self.last_seen > datetime.now(
            tz=homeassistant.util.dt.get_default_time_zone()
        ) - timedelta(seconds=60)


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
