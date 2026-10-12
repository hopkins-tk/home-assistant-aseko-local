"""Data model for Aseko pool devices.

This module defines the **protocol-agnostic target schema** (``AsekoDevice``)
that the entity layer (sensors, binary sensors, buttons, ...) consumes.  It
also defines the device-type enum, the probe-type enum, the electrolyser
polarity enum, the filtration-schedule enum, and the two enums that describe
*how* a device was decoded: the fields its profile reads and the semantic flags its
profile carries.

Byte-level knowledge lives in ``decoding/``: one feature file per field in
``decoding/features/``, and one profile per (protocol, model) in
``decoding/profiles/``.  Nothing in this module knows a byte offset, and
nothing outside ``decoding/`` should either: the entity layer asks
``AsekoDevice.features`` and ``AsekoDevice.flags`` instead.
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


class AsekoProfileFlag(Enum):
    """Semantic facts about a model that are not values in the frame.

    A flag says how an already-decoded value may be *used*, which is model
    knowledge and therefore belongs on the profile.  Consumers check
    ``AsekoDevice.flags`` instead of branching on ``device_type``.
    """

    # byte[37] bit 0x04 (``service_menu_open``) marks a person standing at
    # the unit's settings menu and nothing more.  Where set, a backwash that
    # runs while the bit is on is manual as a matter of observation.  Where
    # not set (HOME, Issue #133) the same bit is a standing pump
    # override that can stay on indefinitely, so it proves nothing about who
    # started a backwash.  Read by ``trackers.backwash`` and by
    # ``AsekoDevice.connection_state`` (the ``service_menu`` state); adding the
    # flag to a profile turns both on for that model.
    MENU_BIT_IS_PRESENCE_ONLY = "menu_bit_is_presence_only"

    # On HOME (Issue #133) byte[37] bit 0x04 is set while the pump has been
    # switched off by hand at the unit, and the relay bit byte[29] 0x08 stays
    # set meanwhile.  Where set, the derived ``filtration_running`` reads
    # False while ``service_menu_open`` is True (``decoding.derived``); the
    # relay bit itself stays as sent in ``filtration_relay``.
    MENU_BIT_SWITCHES_FILTRATION_OFF = "menu_bit_switches_filtration_off"

    # ``startup_delay`` and ``dosing_delay`` are whole minutes (v8 areqs[17] /
    # areqs[18], 2 = "2 min" in the app) instead of v7's seconds.  The value is
    # kept as sent; ``sensor.py`` reads this flag for the unit.
    DELAYS_IN_MINUTES = "delays_in_minutes"

    # The algicide port doses by the day in ml/m3, Aseko ALGICID or the ACO
    # chlorine stabiliser alike: the Salt NET display labels it "Alg/Aco" and
    # its manual "Algicid / ACO".  The entities keep their keys and are named
    # for both (``entity.py``).
    ALGICIDE_OR_ACO = "algicide_or_aco"


class AsekoProbeType(Enum):
    """Enumeration of Aseko Probes."""

    CLF = "clf"
    CLT = "clt"
    DOSE = "dose"
    PH = "ph"
    REDOX = "redox"
    OXY = "oxy"


class AsekoElectrodePolarity(Enum):
    """Which way the salt electrolyser electrode is polarised (or waiting)."""

    LEFT = "left"
    RIGHT = "right"
    WAITING = "waiting"


class AsekoHeatingCondition(Enum):
    """What heating control waits for (byte[22] bits 0x01 / 0x02 / 0x20)."""

    ALWAYS = "always"
    TIME_WINDOW = "time_window"
    OUTSIDE_TEMPERATURE_ABOVE = "outside_temperature_above"
    OUTSIDE_TEMPERATURE_BELOW = "outside_temperature_below"


class AsekoVariableSpeedPumpType(Enum):
    """Variable-speed pump type (byte[78] bits 0x0C); brands share a protocol."""

    SPECK_UWE = "speck_uwe"
    PENTAIR_DAB = "pentair_dab"
    HAYWARD = "hayward"


class AsekoBackwashTrigger(Enum):
    """What started the most recently observed backwash cycle.

    SCHEDULED — the cycle started within the tolerance window around the
        configured ``backwash_start_time`` on a device whose backwash schedule is
        enabled, so the unit ran it on its own.
    MANUAL — somebody started it by hand.  On units whose profile carries
        ``MENU_BIT_IS_PRESENCE_ONLY`` only a cycle outside the window run while the
        menu was open; on the others, any cycle outside the window or with no
        usable schedule.  In the window a cycle is always SCHEDULED.
    UNKNOWN — a unit that reports its menu ran a cycle outside the window
        with the menu closed: neither the schedule nor a person explains it.

    The device does not transmit *why* the valve opened, so this is derived
    from the observed start time and, where reported, the menu.  See
    ``trackers/backwash.py``.
    """

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class AsekoBackwashSource(Enum):
    """Where ``last_scheduled_backwash`` came from.

    OBSERVED — the integration watched the backwash valve run a full cycle.
    MANUAL — the user entered it via ``aseko_local.set_last_scheduled_backwash``,
        to seed the schedule phase instead of waiting for the next real cycle.

    Last write wins, and the timestamps themselves are never compared.  A
    manual entry replaces whatever is stored, because whoever types a date in
    has a reason to.  A scheduled cycle detected afterwards replaces that in
    turn, because the guess it stood in for has now actually been seen.

    ``next_scheduled_backwash`` carries no source of its own — it is always
    projected from ``last_scheduled_backwash``, so its provenance is that
    sensor's and repeating it would only be one more thing to keep in sync.
    """

    OBSERVED = "observed"
    MANUAL = "manual"


class AsekoFiltrationSchedule(Enum):
    """The filtration schedule the unit is configured for (Issue #133).

    byte[37] bits 0x10 / 0x20.  What the unit runs when nobody is at it —
    see `AsekoDevice.service_menu_open`, which is decoded from the same
    byte but says nothing about filtration.

    Enum values map to the translation keys under
    entity.sensor.filtration_schedule.state.
    """

    NONSTOP_24H = "nonstop_24h"
    TIMER_PERIOD_1 = "timer_period_1"
    TIMER_PERIOD_1_AND_2 = "timer_period_1_and_2"


# A unit that sent nothing for this long is offline (Connection status).
OFFLINE_AFTER = timedelta(seconds=60)


class AsekoConnectionState(Enum):
    """What the Connection status entity shows.

    Enum values map to the translation keys under
    entity.sensor.connection_status.state.
    """

    ONLINE = "online"
    OFFLINE = "offline"
    # the last frame said the settings menu is open: frames may go on (a
    # backwash) or stop until it is closed (a filtration run by hand)
    SERVICE_MENU = "service_menu"


@dataclass
class AsekoDevice:
    """Holds data received from Aseko device."""

    device_type: AsekoDeviceType | None = None  # v7 byte[4], v8 header f2
    # How this device was decoded.  Both come from the profile that
    # ``decoding.profile.detect_profile`` picked for the frame, and they are
    # what the entity layer consults instead of byte masks or device types:
    #
    # features -- names of the AsekoDevice fields *this unit* has: the
    #     profile's list minus the readings that answered "not present" for
    #     this unit (probe not installed, shared port configured for the
    #     other chemical, setting never made).  A field not in here gets no
    #     entity; a field in here that reads None is unknown right now and
    #     its entity shows "unknown".  See ``decoding.presence``.
    # flags -- semantic facts about the model, see ``AsekoProfileFlag``.
    # possible_features -- every field this model's profile reads: what the
    #     unit *can* have.  Each gets an entity, created disabled until the
    #     unit first shows the quantity (see ``entity.py``).
    # present_features -- what the last frame showed present.  ``features``
    #     is the union of everything seen since Home Assistant started; an
    #     entity whose field is not present right now is unavailable.
    # profile -- name of the profile that read the last frame ("v7 SALT",
    #     "v8 unknown header type"); ``decoding.profiles.profile_named``
    #     returns it.
    # frame_problems -- what the parser could not read in the last frame.
    profile: str | None = None
    frame_problems: tuple[str, ...] = ()
    features: frozenset[str] = field(default_factory=frozenset)
    possible_features: frozenset[str] = field(default_factory=frozenset)
    present_features: frozenset[str] = field(default_factory=frozenset)
    flags: frozenset[AsekoProfileFlag] = field(default_factory=frozenset)
    configuration: set[AsekoProbeType] = field(default_factory=set)

    serial_number: int | None = None  # byte 0 - 4
    timestamp: datetime | None = None  # byte 6 - 11
    # the unit's clock as sent, no fallback: datetime (v7) or time (v8)
    unit_clock: datetime | time | None = None
    ph: float | None = None  # byte 14 & 15
    free_chlorine: float | None = None  # byte 16 & 17
    free_chlorine_mv: int | None = (
        None  # for NET - free chlorine millivolts (byte 20 & 21)
    )
    redox: int | None = None  # byte 16 & 17 or 18 & 19
    salinity: float | None = None  # byte 20
    chlorine_production_measured: int | None = None  # byte 21, as sent
    chlorine_production: int | None = None  # derived: 0 while not electrolysing
    electrolysis_running: bool | None = None  # byte 29 (4-th bit)
    electrode_polarity: AsekoElectrodePolarity | None = (
        None  # byte 29 (6-th bit for LEFT)
    )
    water_temperature: float | None = None  # byte 25 & 26
    water_flow_to_probes: bool | None = None  # byte 28 == aah
    filtration_relay: bool | None = None  # byte 29 bit 0x08, as sent
    filtration_running: bool | None = None  # derived: relay, HOME manual off
    heating_running: bool | None = None  # byte 29 (2-nd bit, 0x04)
    heating_control_enabled: bool | None = None  # byte 37 bit 3 (0x08) on HOME
    heating_linked_to_filtration: bool | None = None  # byte 38 bit 0x10 (setting)
    freeze_protection_enabled: bool | None = None  # byte 37 bit 7 (0x80) on HOME
    variable_speed_pump_enabled: bool | None = None  # byte 22 bit 0x08 (setting)
    variable_speed_pump_type: AsekoVariableSpeedPumpType | None = None  # byte 78 0x0C
    water_level_sensor_enabled: bool | None = None  # byte 37 bit 0x40
    flow_detection_enabled: bool | None = None  # byte 37 bit 0x02
    backwash_schedule_enabled: bool | None = None  # byte 22 bit 0x10
    heating_condition: AsekoHeatingCondition | None = None  # byte 22 0x01/0x02/0x20
    heating_condition_met: bool | None = None  # byte 78 bit 0x80 (live)
    heating_allowed: bool | None = None  # derived: control on and condition met
    ph_minus_concentration: int | None = None  # byte 112 (%) on HOME (Issue #139)
    chlorine_pump_running: bool | None = None  # byte 29 (6-th bit)
    ph_minus_pump_running: bool | None = None  # byte 29 (7-th bit)
    ph_plus_pump_running: bool | None = (
        None  # byte 29 (unknown - 7-th bit for all except PROFI?)
    )
    algaecide_pump_running: bool | None = (
        None  # byte 29 bit 4 (0x10) on SALT; uncertain on other types
    )
    flocculant_pump_running: bool | None = None  # byte 29 bit 5 (0x20)
    oxygen_pump_running: bool | None = (
        None  # byte 29 bit unconfirmed – OXY Pure device only
    )

    # NEW: flow rates (bytes 95, 97, 99, 101)
    chlorine_flow_rate: int | None = None
    ph_minus_flow_rate: int | None = None
    ph_plus_flow_rate: int | None = None
    oxygen_flow_rate: int | None = (
        None  # byte 99 on OXY Pure device (same slot as chlorine_flow_rate)
    )

    # algicide/flocculant based on byte 37: bit 0x80 set = algicide, 0 = flocculant, 0xFF = undefined
    algaecide_flow_rate: int | None = None
    flocculant_flow_rate: int | None = None

    ph_target: float | None = None  # byte 52/10
    redox_target: int | None = None  # byte 53*10
    free_chlorine_target: float | None = None  # byte 53/10 mg/L
    oxygen_dose_target: int | None = (
        None  # byte 53 raw ml/m³/day – OXY Pure device only
    )
    chlorine_dose_target: int | None = (
        None  # byte 53 raw ml/m³/h – DOSE mode (volume-based Cl dosing)
    )

    # algicide/flocculant based on byte 37: bit 0x80 set = algicide, 0 = flocculant, 0xFF = undefined
    algaecide_dose_target: int | None = None  # byte 54
    flocculant_dose_target: int | None = None  # byte 54

    water_temperature_target: int | None = None  # byte 55

    filtration_period_1_start: time | None = None  # byte 56 & 57
    filtration_period_1_end: time | None = None  # byte 58 & 59
    filtration_period_2_start: time | None = None  # byte 60 & 61
    filtration_period_2_end: time | None = None  # byte 62 & 63

    backwash_interval: int | None = None  # byte 68
    backwash_start_time: time | None = None  # byte 69 & 70
    backwash_duration: int | None = None  # byte 71

    # Backwash running state — byte [29] bit 0x01
    # True while the backwash valve relay is currently energized.
    # NOTE: bit 0x01 is the backwash relay across all device types that
    # have a backwash valve (HOME, SALT, OXY).  NET has no backwash output.
    # The mapping is the same one JS-DE-Tech uses for `relay_byte` bit 0
    # ("backwash" relay).  Live confirmation is still pending — see
    # docs/temp/byte29_salt_pump_masks_analysis.md for context.
    backwash_running: bool | None = None

    pool_volume: int | None = None  # byte 92 & 93
    max_refill_time: int | None = None  # bytes 76-77, seconds
    max_ph_doses: int | None = None  # byte 115, safety function

    air_temperature: float | None = None  # byte 23 & 24 (signed, ÷10 = °C)

    # Water level
    water_level: int | None = None  # byte [27] (cm, real-time)
    water_level_low_alarm: int | None = None  # byte [102] (cm, config)
    water_level_refill_start: int | None = None  # byte [103] (cm, config)
    water_level_refill_stop: int | None = None  # byte [104] (cm, config)
    water_level_high_alarm: int | None = None  # byte [105] (cm, config)

    # Water filling active — byte [29] bit 0x02
    refilling: bool | None = None

    # The filtration schedule the unit is configured for — byte [37]
    # bits 0x10 / 0x20, which the manual override (bit 0x04) does not
    # touch.  A unit can be in manual mode *and* configured for nonstop,
    # and both are worth showing, so the two are kept apart.
    filtration_schedule: AsekoFiltrationSchedule | None = None

    # Somebody has the unit's settings menu open — byte [37] bit 0x04.
    #
    # Not a filtration state, despite living in the same byte: it says a
    # person is standing at the unit, and nothing about what they are doing.
    # The menu is where filtration and backwash can be started by hand, but
    # the unit stops transmitting while it is open, so whether anything was
    # touched — and what — is not observable at all.  It may well override
    # filtration; there is no way to see that from here.
    #
    # Read from byte[37] bit 0x04 on every model with the bit field; left None where
    # bit 0x04 belongs to the transitional edit states, and on NET.
    service_menu_open: bool | None = None

    # Alarm/error bitmasks — bytes [12] (HOME dosing warnings) and [13]
    # byte [12] 0x20 = chlorine/disinfection dosing warning (HOME ✅, issue #134)
    # byte [12] 0x40 = pH dosing warning (HOME ✅, issue #134)
    # byte [13] 0x01 = disinfection/ORP dose fault (Issue #151, HOME serial 110175608;
    #                  config48 frame byte[13]=0x01 during "Maximum disinfection dose
    #                  exceeded" — same fault as v8 ins[12] bit 0x80)
    # byte [13] 0x02 = pH dose fault (inferred, symmetric to 0x01 — no direct capture yet)
    # byte [13] 0x04 = no flow to probes (confirmed)
    # byte [13] 0x08 = rapid pH change (error_codes.md, unconfirmed by capture)
    alarm_ph_dosing_ineffective: bool | None = None  # byte [13] 0x02 | byte [12] 0x40
    alarm_max_disinfection_dose: bool | None = None  # byte [13] 0x01 | byte [12] 0x20
    alarm_no_flow_to_probes: bool | None = None  # byte [13] bit 0x04 (confirmed)
    alarm_rapid_ph_change: bool | None = (
        None  # byte [13] bit 0x08 (error_codes.md, unconfirmed by capture)
    )

    dosing_delay: int | None = None  # byte 107 & 108 ? (seconds)
    startup_delay: int | None = None  # byte 74 & 75 (seconds)

    # Backwash history — filled by the coordinator from BackwashTracker
    # (persistent across restarts) and None until a real cycle has been seen.
    # The device never transmits its backwash history, so there is nothing to
    # derive these from before that: the schedule alone cannot tell us whether
    # a cycle actually ran, so guessing from it would show a confident
    # timestamp for something that may never have happened.
    # See custom_components/aseko_local/trackers/backwash.py.
    #
    # These differ in how much they can be trusted:
    #
    # OBSERVED — the integration watched the backwash valve stay open for a
    # full cycle, so this happened:
    #   last_backwash           = most recent cycle, whatever started it.
    #
    # DERIVED — split out of the above by a heuristic on the start time, which
    # can misclassify (see BackwashTracker._classify for how and when):
    #   last_scheduled_backwash = most recent cycle that looked like the unit's
    #                             own scheduled run.
    #   last_manual_backwash    = most recent cycle that did not.
    #   last_backwash_trigger   = which of the two the latest cycle was.  No
    #                             entity — it is redundant with comparing the
    #                             two timestamps above — but it is surfaced in
    #                             diagnostics so a misclassification is visible
    #                             in a dump.
    #   next_scheduled_backwash = last_scheduled_backwash projected forward by
    #                             backwash_interval, so it inherits any
    #                             error in that classification.  None while no
    #                             scheduled cycle is known: a manual backwash
    #                             does not reveal the schedule phase, and an
    #                             unscheduled one cannot be predicted.
    #
    # last_scheduled_backwash_source says whether that timestamp was observed
    # or entered by hand, and is exposed as a "source" state attribute so a
    # seeded value is never mistaken for a measured one.  next_scheduled_backwash
    # needs no equivalent: it is always projected from that same timestamp.
    last_backwash: datetime | None = None
    last_scheduled_backwash: datetime | None = None
    last_scheduled_backwash_source: AsekoBackwashSource | None = None
    last_manual_backwash: datetime | None = None
    last_backwash_trigger: AsekoBackwashTrigger | None = None
    next_scheduled_backwash: datetime | None = None

    # Server-side receive timestamp – set by the coordinator on every incoming frame.
    # Independent of the device clock (which can be wrong or missing on some models).
    last_seen: datetime | None = None

    # When Home Assistant received the frame this device was decoded from:
    # stamped by the server as soon as the frame is complete, in UTC.  The
    # transmission delay from the unit is not corrected for.
    received_at: datetime | None = None

    # From trackers/clock.py: minutes the unit's clock is ahead of Home
    # Assistant's (negative: behind), and whether that is past the alert
    # limit set in the integration's options.  None until measured.
    clock_offset: float | None = None
    clock_out_of_sync: bool | None = None

    def online(self) -> bool:
        """Return True if a frame was received within ``OFFLINE_AFTER``.

        The other entities keep their last values while a unit is offline;
        this is the flag that says they are not fresh.
        """
        # compared normalised to UTC: a change of summer / winter time in
        # Home Assistant must not age or rejuvenate the last frame
        return (
            self.last_seen is not None
            and homeassistant.util.dt.as_utc(self.last_seen)
            > homeassistant.util.dt.utcnow() - OFFLINE_AFTER
        )

    def connection_state(self) -> AsekoConnectionState:
        """Return what the Connection status entity shows.

        A unit whose last frame had the settings menu open says so at once
        instead of online or offline.  What it sends next depends on what is
        done in the menu: frames go on during a backwash started there, but
        stop during a filtration run by hand until the menu is closed, which
        can take hours.  Neither can be told from the menu frame, so there is
        no timeout and the state does not claim offline.  Only where the
        menu bit means a person at the unit (``MENU_BIT_IS_PRESENCE_ONLY`` in
        its profile); no model is named here, the flag decides.  On HOME the
        same bit is a standing pump override that keeps sending, so its
        profile does not carry the flag.
        """
        if (
            self.service_menu_open
            and AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY in self.flags
        ):
            return AsekoConnectionState.SERVICE_MENU
        if self.online():
            return AsekoConnectionState.ONLINE
        return AsekoConnectionState.OFFLINE


@dataclass
class AsekoData:
    """Holds a mapping of serial numbers to Aseko devices."""

    devices: dict[int, AsekoDevice] = field(default_factory=dict)

    def _copy_attributes(self, src: AsekoDevice, dest: AsekoDevice) -> None:
        for f in fields(AsekoDevice):
            setattr(dest, f.name, getattr(src, f.name))

    def get_all(self) -> list[AsekoDevice]:
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
