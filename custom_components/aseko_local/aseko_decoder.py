import logging
from datetime import datetime, time, timedelta
import homeassistant.util
from typing import Type, TypeVar


from .aseko_data import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoFiltrationMode,
    AsekoProbeType,
)
from .aseko_v7_helpers import (
    ACTUATOR_MASKS,
    AsekoActuatorMasks,
    AsekoByte37Masks,
    AsekoThirdPumpSlot,
)
from .const import (
    FILTRATION_PERIOD2_ENABLED_MASK,
    PROBE_CLF_MISSING,
    PROBE_DOSE_MISSING,
    PROBE_REDOX_MISSING,
    UNIT_TYPE_HOME,
    UNIT_TYPE_HOME_CLF,
    UNIT_TYPE_HOME_REDOX,
    UNIT_TYPE_NET,
    UNIT_TYPE_OXY,
    UNIT_TYPE_PROFI,
    UNIT_TYPE_SALT,
    UNSPECIFIED_VALUE,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

# Device types that expose a filtration schedule. Aqua NET has no filtration
# output; unknown/new types are excluded by default so they never get garbage
# filtration sensors until explicitly verified and added here.
FILTRATION_TYPES = frozenset(
    {
        AsekoDeviceType.SALT,
        AsekoDeviceType.HOME,
        AsekoDeviceType.OXY,
        AsekoDeviceType.PROFI,
    }
)

# Device types verified to encode the second-filtration-period enable flag in
# byte 37 bit 0x20: SALT (on/off frame diff), HOME and OXY (maintainer feedback,
# PR #122). For any other type the second period is reported as before, because
# its enable mechanism is unverified — never assume this bit for a new type.
FILTRATION_PERIOD2_FLAG_TYPES = frozenset(
    {
        AsekoDeviceType.SALT,
        AsekoDeviceType.HOME,
        AsekoDeviceType.OXY,
    }
)

# Device types that have a backwash valve/output and therefore expose a
# backwash schedule (bytes 68-71) plus a backwash-active bit (byte 29 bit 0x01).
# NET (Aqua NET) is a measurement + dosing unit only — it has neither a filter
# nor a backwash valve, so the corresponding sensors must be suppressed.
# Issue #129: prior to this filter, the decoder blindly read bytes 68-71 on
# every device type, so a NET frame carrying non-0xFF data in those slots
# would surface phantom backwash entities.
BACKWASH_TYPES = frozenset(
    {
        AsekoDeviceType.SALT,
        AsekoDeviceType.HOME,
        AsekoDeviceType.OXY,
        AsekoDeviceType.PROFI,
    }
)

# Device types that have a water-level probe + filling-valve output and
# therefore expose the water_level live value plus the four threshold setpoints
# (bytes 27, 102-105) and the max_filling_time (bytes 94-95).
# NET (Aqua NET) and PROFI do not have a filling valve → skip the whole group.
# Mirrors the existing _fill_home_water_level_data() NET early-return.
WATER_LEVEL_TYPES = frozenset(
    {
        AsekoDeviceType.SALT,
        AsekoDeviceType.HOME,
        AsekoDeviceType.OXY,
    }
)


class AsekoDecoder:
    """Decoder of Aseko unit data."""

    @staticmethod
    def _normalize_value(value: int | str | None, type: Type[T]) -> T | None:
        """Normalize raw values to None if they are unspecified/invalid.
        Rules:
        - None stays None
        - Integer 255 (0xFF) → None
        - Empty string "" → None
        - String "255" → None
        - Otherwise: return value unchanged
        """

        if value is None:
            return None

        if type is int and isinstance(value, int):
            return None if value == UNSPECIFIED_VALUE else type(value)

        if type is str and isinstance(value, str):
            val = value.strip()
            if not val or val == str(UNSPECIFIED_VALUE):
                return None
            return type(val)

        raise ValueError(f"Unsupported type {type} or value {value}")

    @staticmethod
    def _unit_type(data: bytes) -> AsekoDeviceType | None:
        """Determine the Aseko device type. Returns None until a reliable detection is possible."""

        if data[4] == UNIT_TYPE_PROFI:  # Uncertain
            return AsekoDeviceType.PROFI

        if data[4] > UNIT_TYPE_SALT:
            return AsekoDeviceType.SALT

        if data[4] > UNIT_TYPE_NET:
            return AsekoDeviceType.NET

        if data[4] == UNIT_TYPE_OXY:
            return AsekoDeviceType.OXY

        if data[4] >= UNIT_TYPE_HOME:
            return AsekoDeviceType.HOME

        _LOGGER.warning("Unknown unit type: %s", data[4])
        return None

    @staticmethod
    def _configuration(
        data: bytes, device_type: AsekoDeviceType | None = None
    ) -> set[AsekoProbeType]:
        """Determine types of probes installed from the binary data."""

        # Let's try to read everything for unknown unit type
        if device_type is None:
            return {
                AsekoProbeType.PH,
                AsekoProbeType.CLF,
                AsekoProbeType.CLT,
                AsekoProbeType.REDOX,
                AsekoProbeType.DOSE,
                AsekoProbeType.OXY,
            }

        # OXY has no CLF/REDOX probe hardware. The SANOSIL (OXY Pure) probe
        # occupies the CLF slot physically, so PROBE_CLF_MISSING bit is 0 –
        # which would incorrectly add CLF without this guard.
        elif device_type == AsekoDeviceType.OXY:
            return {AsekoProbeType.PH, AsekoProbeType.OXY}

        # HOME units have different bitmask logic, and the bits are not consistent across HOME vs. NET/SALT as initially hoped
        # – instead, they seem to indicate specific HOME subtypes with fixed probe configurations.
        # The CLF vs. REDOX distinction is determined by the unit type byte rather than a missing probe bit.
        elif device_type == AsekoDeviceType.HOME:
            if data[4] == UNIT_TYPE_HOME_CLF:
                return {AsekoProbeType.PH, AsekoProbeType.CLF}

            elif data[4] == UNIT_TYPE_HOME_REDOX:
                return {AsekoProbeType.PH, AsekoProbeType.REDOX}

            else:
                return {AsekoProbeType.PH, AsekoProbeType.DOSE}

        else:
            probe_info = data[4]

            probes = set()
            probes.add(AsekoProbeType.PH)

            if not bool(probe_info & PROBE_REDOX_MISSING):
                probes.add(AsekoProbeType.REDOX)

            if not bool(probe_info & PROBE_CLF_MISSING):
                probes.add(AsekoProbeType.CLF)

            if device_type != AsekoDeviceType.PROFI and not bool(
                probe_info & PROBE_DOSE_MISSING
            ):
                probes.add(AsekoProbeType.DOSE)

            return probes

    @staticmethod
    def _timestamp(data: bytes) -> datetime | None:
        """Extract timestamp from data and validates timestamp."""

        if (
            len(data) < 12
            or data[6] == UNSPECIFIED_VALUE
            or data[7] == UNSPECIFIED_VALUE
            or data[8] == UNSPECIFIED_VALUE
            or data[9] == UNSPECIFIED_VALUE
            or data[10] == UNSPECIFIED_VALUE
            or data[11] == UNSPECIFIED_VALUE
        ):
            _LOGGER.info(
                "Received unspecified timestamp – falling back to now(). Frame: %s",
                data.hex(),
            )
            return datetime.now(tz=homeassistant.util.dt.get_default_time_zone())

        try:
            year = YEAR_OFFSET + data[6]

            month = data[7]
            day = data[8]
            hour = data[9]
            minute = data[10]
            second = data[11]

            return datetime(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second,
                tzinfo=homeassistant.util.dt.get_default_time_zone(),
            )

        except ValueError as e:
            _LOGGER.warning(
                "Received invalid timestamp (%s) – falling back to now(). Frame: %s",
                e,
                data.hex(),
            )
            return datetime.now(tz=homeassistant.util.dt.get_default_time_zone())

    @staticmethod
    def _max_filling_time_from_bytes(data: bytes) -> int | None:
        """Decode max_filling_time (bytes 94-95) as a 2-byte big-endian minute value.

        Returns None for the 0xFFFF sentinel (device does not implement the
        feature) so that downstream consumers see ``None`` instead of ``65535``.
        Issue #129: a bare ``int.from_bytes(...)`` would otherwise turn
        unspecified frame data into a bogus 65535-minute value on NET/PROFI.
        """
        value = int.from_bytes(data, "big")
        if value == 0xFFFF:
            return None
        return value

    @staticmethod
    def _time(data: bytes) -> time | None:
        if data[0] == UNSPECIFIED_VALUE:
            return None

        hour = data[0]
        minute = data[1]

        try:
            return time(hour=hour, minute=minute)
        except ValueError as e:
            _LOGGER.warning("Invalid time in frame (%s) – data=%s", e, data.hex())
            return None

    @staticmethod
    def _electrolyzer_direction(
        data: bytes, masks: AsekoActuatorMasks
    ) -> AsekoElectrolyzerDirection:
        if (
            masks.electrolyzer_running_left
            and (data[29] & masks.electrolyzer_running_left)
            == masks.electrolyzer_running_left
        ):
            return AsekoElectrolyzerDirection.LEFT
        if (
            masks.electrolyzer_running_right
            and data[29] & masks.electrolyzer_running_right
        ):
            return AsekoElectrolyzerDirection.RIGHT
        return AsekoElectrolyzerDirection.WAITING

    @staticmethod
    def _fill_ph_data(unit: AsekoDevice, data: bytes) -> None:
        if AsekoProbeType.PH not in unit.configuration:
            return
        unit.ph = int.from_bytes(data[14:16], "big") / 100

    @staticmethod
    def _fill_redox_data(unit: AsekoDevice, data: bytes) -> None:
        if AsekoProbeType.REDOX not in unit.configuration:
            return
        if data[18] == UNSPECIFIED_VALUE and data[19] == UNSPECIFIED_VALUE:
            unit.redox = int.from_bytes(data[16:18], "big")
        else:
            unit.redox = int.from_bytes(data[18:20], "big")

    @staticmethod
    def _fill_clf_data(unit: AsekoDevice, data: bytes) -> None:
        if AsekoProbeType.CLF not in unit.configuration:
            return
        unit.cl_free = int.from_bytes(data[16:18], "big") / 100
        unit.cl_free_mv = int.from_bytes(data[20:22], "big")

    @staticmethod
    def _fill_salt_unit_data(unit: AsekoDevice, data: bytes) -> None:
        if unit.device_type != AsekoDeviceType.SALT:
            return
        masks = ACTUATOR_MASKS[AsekoDeviceType.SALT]
        unit.salinity = data[20] / 10
        unit.electrolyzer_power = (
            data[21] if data[29] & masks.electrolyzer_running else 0
        )
        unit.electrolyzer_active = bool(data[29] & masks.electrolyzer_running)
        unit.electrolyzer_direction = AsekoDecoder._electrolyzer_direction(data, masks)

    @staticmethod
    def _fill_required_data(unit: AsekoDevice, data: bytes) -> None:
        """Fill all required setpoint fields.

        byte[52] → required_ph        (PH probe)
        byte[53] → one of (mutually exclusive, evaluated in priority order):
            required_oxy_dose         OXY device
            required_cl_free          CLF probe
            required_cl_dose          DOSE probe without CLF (pure dosing mode)
            required_redox            REDOX probe, not on PROFI (× 10)
        byte[54] → required_floc      (OXY and HOME: independent pump ports)
                 → required_algicide or required_floc
                   (SALT: shared pump port, routed via byte[37])
        byte[72] → required_algicide  (OXY and HOME: independent pump ports)
        """
        # byte[52]: pH setpoint — present on all devices with a pH probe.
        if AsekoProbeType.PH in unit.configuration:
            unit.required_ph = data[52] / 10

        # OXY firmware fills CLF/REDOX slots with placeholder 0x001E — skip them.
        # All OXY setpoint bytes are independent of the non-OXY routing logic below.
        if unit.device_type == AsekoDeviceType.OXY:
            unit.required_oxy_dose = data[53]
            # byte[54] = required_floc (ml/h)           confirmed: 2026-04-11 value=10
            # byte[72] = required_algicide (ml/m³/d)    confirmed: 2026-04-11 value=15
            unit.required_floc = AsekoDecoder._normalize_value(data[54], int)
            unit.required_algicide = AsekoDecoder._normalize_value(data[72], int)
            return

        # HOME devices have independent pump ports for algicide and flocculant
        # (same layout as OXY Pure for these two setpoints).
        # byte[54] = required_floc (ml/h)         confirmed: 2026-04-28, serial 110128063, value=10
        # byte[72] = required_algicide (ml/m³/d)  confirmed: 2026-04-28, serial 110128063, value=0
        # Fall through so byte[53] is still decoded as required_cl_free / required_redox below.
        if unit.device_type == AsekoDeviceType.HOME:
            unit.required_floc = AsekoDecoder._normalize_value(data[54], int)
            unit.required_algicide = AsekoDecoder._normalize_value(data[72], int)

        # byte[53]: mutually exclusive interpretations determined by probe/device type.
        if AsekoProbeType.CLF in unit.configuration:
            unit.required_cl_free = data[53] / 10
        elif (
            AsekoProbeType.REDOX in unit.configuration
            and unit.device_type != AsekoDeviceType.PROFI
        ):
            unit.required_redox = data[53] * 10
        elif AsekoProbeType.DOSE in unit.configuration:
            # Pure DOSE mode: no CLF and no REDOX probe. Timed volume dosing active.
            # byte[53] = required chlorine/disinfectant dose in ml/m³/h.
            unit.required_cl_dose = data[53]

        # byte[54]: algicide or flocculant setpoint, routed via byte[37] (SALT shared port).
        masks = ACTUATOR_MASKS.get(unit.device_type)
        if (
            masks is not None
            and masks.byte37_routes_pump_type
            and data[37] != UNSPECIFIED_VALUE
        ):
            if bool(data[37] & AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING):
                unit.required_algicide = AsekoDecoder._normalize_value(data[54], int)
            else:
                unit.required_floc = AsekoDecoder._normalize_value(data[54], int)

    @staticmethod
    def _fill_flowrate_data(unit: AsekoDevice, data: bytes) -> None:
        # byte[95] = pH− flowrate (all devices).
        unit.flowrate_ph_minus = AsekoDecoder._normalize_value(data[95], int)

        if unit.device_type == AsekoDeviceType.OXY:
            # OXY Pure: independent pump ports, no byte[37] routing.
            # byte[99]  = OXY chemical pump flowrate (confirmed).
            # byte[101] = flocculant flowrate (confirmed).
            # byte[103] = algicide flowrate   (confirmed: 2026-04-11 value=60 ml/min).
            unit.flowrate_oxy = AsekoDecoder._normalize_value(data[99], int)
            unit.flowrate_floc = AsekoDecoder._normalize_value(data[101], int)
            unit.flowrate_algicide = AsekoDecoder._normalize_value(data[103], int)
            return

        if unit.device_type == AsekoDeviceType.HOME:
            # HOME devices have independent pump ports for flocculant and algicide
            # (same layout as OXY Pure for these two flowrates — confirmed by
            # real HOME frames from serial 110071590 / 110128063, see Issue #110
            # and #115).  No byte[37] routing is involved.
            # byte[99]  = chlorine / Chlor Pure flowrate (matches byte[54] family).
            # byte[101] = flocculant flowrate (ml/min).
            # byte[103] = algicide flowrate   (ml/min).
            unit.flowrate_chlor = AsekoDecoder._normalize_value(data[99], int)
            unit.flowrate_floc = AsekoDecoder._normalize_value(data[101], int)
            unit.flowrate_algicide = AsekoDecoder._normalize_value(data[103], int)
            return

        # SALT / NET / PROFI: byte[99] = chlorine pump flowrate.
        unit.flowrate_chlor = AsekoDecoder._normalize_value(data[99], int)

        # byte[101]: shared "third pump slot" — algicide OR flocculant per byte[37].
        # bit 0x80 in byte[37] = algicide (ml/m³/day); not set = flocculant (ml/h).
        # 0xFF (UNSPECIFIED) → configuration unknown → leave both as None.
        if data[37] != UNSPECIFIED_VALUE and bool(
            data[37] & AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING
        ):
            unit.flowrate_algicide = AsekoDecoder._normalize_value(data[101], int)
        elif data[37] != UNSPECIFIED_VALUE:
            unit.flowrate_floc = AsekoDecoder._normalize_value(data[101], int)
        # flowrate_ph_plus (byte 97): mapping unconfirmed

    @staticmethod
    def _fill_home_water_level_data(unit: AsekoDevice, data: bytes) -> None:
        """Decode water level fields for HOME, SALT and OXY devices.

        Confirmed byte positions (all sources zero-based):
          byte [27]  = current water level in cm     (domin211 ✅, issue #110 ✅)
          byte [29] bit 0x02 = water filling active  (DomSchCoding #100 ✅)
          byte [102] = low alarm threshold (cm)       (domin211 ✅, issue #110 ✅)
          byte [103] = filling ON threshold (cm)      (domin211 ✅, DomSchCoding ✅, issue #110 ✅)
          byte [104] = filling OFF threshold (cm)     (domin211 ✅, DomSchCoding ✅, issue #110 ✅)
          byte [105] = high alarm threshold (cm)      (domin211 ✅, issue #110 ✅)

        NET is excluded: bytes [102..104] contain unrelated non-FF data on NET devices
        that would produce incorrect water level threshold readings.
        Note: byte [103] overlaps with OXY flowrate_algicide AND with HOME
        flowrate_algicide.  Both OXY and HOME have an early return in
        _fill_flowrate_data, so flowrate_algicide and water_level_filling_on
        read the SAME byte without conflict.  SALT ignores byte[103] (it is
        the duplicate flocculant slot — see salt_device_analysis.md).
        """
        if unit.device_type == AsekoDeviceType.NET:
            return

        unit.water_level = AsekoDecoder._normalize_value(data[27], int)
        unit.water_filling_active = bool(data[29] & 0x02)

        unit.water_level_low_alarm = AsekoDecoder._normalize_value(data[102], int)
        unit.water_level_filling_on = AsekoDecoder._normalize_value(data[103], int)
        unit.water_level_filling_off = AsekoDecoder._normalize_value(data[104], int)
        unit.water_level_high_alarm = AsekoDecoder._normalize_value(data[105], int)

    @staticmethod
    def _fill_heating_demand(unit: AsekoDevice, data: bytes) -> None:
        """Decode the heating demand relay state from byte[29] bit 0x04.

        byte[29] bit 0x04 = heating demand relay (JS-DE-Tech "relay_byte"
        bit 2).  Set whenever the pool controller is requesting heat from
        the configured heater source (heat pump, electric heater, etc.).

        Available on HOME, SALT, OXY.  NET does not have a heating output,
        so the field stays None for NET (and no binary sensor is
        registered).

        The bit-0x04 mapping is the same one JS-DE-Tech uses and was
        independently listed by the prior Node-RED decoder.

        Additionally decodes the heating control master enable from
        byte[37] (HOME v7 devices, Issue #135).  Diagnostics from serial
        110175608 (ASIN AQUA Home, byte 4 = 0x03, firmware A high nibble
        0x4) show bit 3 (0x08) set when heating control is ON (0x49) and
        clear when OFF (0x41).  The initial unconfigured state (0x45) also
        has bit 3 clear.
        """
        if unit.device_type == AsekoDeviceType.NET:
            return
        unit.heating_active = bool(data[29] & 0x04)

        # byte[37] bit 3 = heating control master enable (HOME only).
        # Gated on HOME so SALT / OXY / NET / PROFI behaviour is unchanged.
        if unit.device_type == AsekoDeviceType.HOME and data[37] != UNSPECIFIED_VALUE:
            unit.heating_control_enabled = bool(
                data[37] & AsekoByte37Masks.HOME_FWA_HEATING_ENABLED
            )

    @staticmethod
    def _fill_backwash_active(unit: AsekoDevice, data: bytes) -> None:
        """Decode the backwash relay state from byte[29] bit 0x01.

        byte[29] bit 0x01 = backwash relay active (JS-DE-Tech "relay_byte" bit 0).

        This bit is set across all device types that have a backwash valve
        (HOME, SALT, OXY).  NET has no backwash output, so the field stays
        None for NET — it is the user's responsibility to interpret "no entity
        at all" as "device does not have a backwash output".

        Live confirmation: not yet captured in a frame while a backwash cycle
        is actually running.  A "no flow to probes" condition (byte[13] bit
        0x04) was independently confirmed to be associated with byte[28] == 0
        (and not byte[29] bit 0x01) — see Issue #100, DomSchCoding capture.
        The bit-0x01 mapping is the same one JS-DE-Tech uses and DomSchCoding
        identified as a candidate in Issue #100 §"Open: Dynamic State Bytes".
        """
        if unit.device_type == AsekoDeviceType.NET:
            # NET has no backwash valve — leave the field as None so the
            # binary sensor is not registered.
            return

        unit.backwash_active = bool(data[29] & 0x01)

    @staticmethod
    def _fill_backwash_schedule(unit: AsekoDevice) -> None:
        """Compute estimated last/next backwash datetimes from the schedule config.

        Algorithm:
          last_backwash = most recent occurrence of backwash_time at or before
                          the frame timestamp (i.e. today's or yesterday's slot).
          next_backwash = last_backwash + backwash_every_n_days days.

        Caveat (last_backwash): This is a schedule-based *estimate*.  The actual
        backwash phase is unknown from the device because it does not transmit
        when the last backwash physically ran.

        The coordinator (``coordinator.py``) overrides ``last_backwash`` with
        the value from ``BackwashTracker`` (a persistent store of the last
        observed ≥60 s relay-on window) once a real backwash has been seen.
        So:
            * Before the first observed backwash: the value here is shown
              (i.e. the latest scheduled slot in the past).
            * After the first observed backwash: the tracker's value wins
              (and persists across HA restarts).

        See ``backwash_tracker.py`` for the live-tracking implementation.
        """
        # Defensive: the schedule fields are already gated on BACKWASH_TYPES in
        # decode(), but we re-check the device type here so this method stays
        # safe even if it is ever called from a code path that didn't pre-filter.
        if unit.device_type is None or unit.device_type not in BACKWASH_TYPES:
            return
        if (
            unit.backwash_every_n_days is None
            or unit.backwash_time is None
            or unit.timestamp is None
        ):
            return

        # `0` means "schedule disabled" per the device config / README.
        # In that case the schedule-derived sensors stay None so the user
        # does not see bogus last/next datetimes that all collapse to
        # the same value.
        if unit.backwash_every_n_days <= 0:
            return

        tz = unit.timestamp.tzinfo
        today_at_backwash = datetime.combine(
            unit.timestamp.date(), unit.backwash_time
        ).replace(tzinfo=tz)

        # If the scheduled time is still in the future today, use yesterday's slot.
        if today_at_backwash > unit.timestamp:
            last = today_at_backwash - timedelta(days=1)
        else:
            last = today_at_backwash

        unit.last_backwash = last
        unit.next_backwash = last + timedelta(days=unit.backwash_every_n_days)

    @staticmethod
    def _fill_alarm_data(unit: AsekoDevice, data: bytes) -> None:
        """Decode alarm bitmasks (bytes [12] and [13]) for all device types.

        byte [13] bitmask (multiple bits can be set simultaneously):
          0x01 = pH alarm: too many doses, no value change   (error_codes.md)
          0x02 = ORP/clf alarm: 30 doses, no value change    (error_codes.md)
          0x04 = no flow to probes                           (DomSchCoding ✅, NET frame ✅)
          0x08 = rapid pH change, stops regulation ~2 h      (error_codes.md, unconfirmed)

        byte [12] dosing-warning bitmask (HOME ✅, issue #134 before/after captures):
          0x20 = disinfection / chlorine dosing warning
                 (Pool Live: MAXIMUM_DISINFECTION_DOSE_EXCEEDED)
          0x40 = pH dosing warning
                 (Pool Live: TOO_MANY_PH_DOSING_ATTEMPTS_WITHOUT_CHANGE)

        On NET, byte [12] is typically 0x00 while no-flow lives in byte [13]
        (byte [13] = 0x04). HOME dosing lockouts set byte [12] and leave
        byte [13] at 0x00, so both bytes must be consulted.
        """
        unit.alarm_ph_too_many_doses = bool(data[13] & 0x01) or bool(data[12] & 0x40)
        unit.alarm_orp_too_many_doses = bool(data[13] & 0x02) or bool(data[12] & 0x20)
        unit.alarm_no_flow_to_probes = bool(data[13] & 0x04)
        unit.alarm_rapid_ph_change = bool(data[13] & 0x08)

    @staticmethod
    def _fill_filtration_mode(unit: AsekoDevice, data: bytes) -> None:
        """Decode filtration mode into `filtration_mode` (enum).

        Runs for every device type in FILTRATION_TYPES = {SALT, HOME, OXY, PROFI}.
        NET is excluded — it has no filtration output (see Issue #66).

        HOME v7 devices encode the full 4-state mode in byte[37] with two
        firmware variants (Issue #133):

          Old encoding (home_device_analysis.md, serial 110128063, byte 4 = 0x02):
            high nibble 0x4 / 0x5
            0x43 = nonstop 24h
            0x53 = timer (P1 or P1&P2, indistinguishable)
            0x47 / 0x57 = transitional edit state — leave as None

          New encoding (Issue #133, serial 110169464, byte 4 = 0x03):
            high nibble 0x0 / 0x1 / 0x3
            0x01 = nonstop 24h
            0x11 = P1 only
            0x31 = P1 & P2
            0x15 = P1 + manual override     → OFF_MANUAL (bit 0x04 set)
            0x35 = P1 & P2 + manual override → OFF_MANUAL (bit 0x04 set)

        SALT / OXY / PROFI do not put a filtration mode flag in byte[37]
        (SALT uses it for algicide/flocculant routing + dosage encoding,
        OXY uses it for the pump-presence bitmap, PROFI has no live frame
        captured yet). For those device types the mode is derived from
        the schedule fields that are already decoded:

          NONSTOP_24H           ⇔ start1 is None (no schedule)
          TIMER_PERIOD_1        ⇔ start1 set, period-2 byte 0x20 clear
          TIMER_PERIOD_1_AND_2  ⇔ start1 set, period-2 byte 0x20 set
          OFF_MANUAL            ⇔ only HOME firmware B (0x35)

        The legacy `filtration_nonstop24` boolean field is kept for
        backwards compatibility and is derived from `filtration_mode` here.
        """
        if unit.device_type is None or unit.device_type not in FILTRATION_TYPES:
            return

        mode: AsekoFiltrationMode | None = None
        b = data[37]

        if unit.device_type == AsekoDeviceType.HOME:
            # HOME: byte[37] carries the mode flag (two firmware variants).
            # Firmware A (high nibble 0x4/0x5, serial 110128063, byte 4 = 0x02)
            # uses exact byte values. Firmware B (high nibble 0x0/0x1/0x3,
            # serial 110169464, byte 4 = 0x03) uses bit flags:
            #   bit 2 (0x04) = manual override active
            #   bit 4 (0x10) = period 1 enabled
            #   bit 5 (0x20) = period 2 enabled
            if b != UNSPECIFIED_VALUE:
                if b & 0x40:
                    # Firmware A: high nibble 0x4/0x5.
                    if b == 0x43:
                        mode = AsekoFiltrationMode.NONSTOP_24H
                    elif b == 0x53:
                        mode = AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
                    # 0x47 / 0x57 → transitional edit state, leave as None.
                else:
                    # Firmware B: high nibble 0x0/0x1/0x3.
                    if b & 0x04:
                        # Manual override active — bit 2 set.
                        # Observed values: 0x15 (P1 + override),
                        # 0x35 (P1&P2 + override).
                        mode = AsekoFiltrationMode.OFF_MANUAL
                    elif (b & 0x30) == 0x00:
                        mode = AsekoFiltrationMode.NONSTOP_24H
                    elif (b & 0x30) == 0x10:
                        mode = AsekoFiltrationMode.TIMER_PERIOD_1
                    elif (b & 0x30) == 0x30:
                        mode = AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
            # Fallback for unrecognised HOME firmware A values (Issue #135):
            # serial 110175608 (byte 4=0x03 REDOX HOME) has values 0x45/0x49/0x41
            # that don't match the known CLF HOME patterns (0x43/0x53/0x47/0x57).
            # Transitional edit states (0x47, 0x57) have bit 1 set — keep them
            # as None.  All other unrecognised firmware A values fall back to
            # schedule-derived mode.
            if (
                mode is None
                and b & 0x40
                and not (b & AsekoByte37Masks.HOME_FWA_TRANSITIONAL_MASK)
            ):
                p1_set = data[56] != UNSPECIFIED_VALUE and data[57] != UNSPECIFIED_VALUE
                p2_set = data[60] != UNSPECIFIED_VALUE and data[61] != UNSPECIFIED_VALUE
                if not p1_set:
                    mode = AsekoFiltrationMode.NONSTOP_24H
                elif p2_set or bool(b & FILTRATION_PERIOD2_ENABLED_MASK):
                    mode = AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
                else:
                    mode = AsekoFiltrationMode.TIMER_PERIOD_1
        else:
            # SALT / OXY / PROFI: byte[37] does not encode filtration mode.
            # Derive from the raw schedule bytes 56-63 (read here directly
            # because this function runs before the schedule is decoded into
            # `unit.start1` / `unit.start2`).
            p1_set = data[56] != UNSPECIFIED_VALUE and data[57] != UNSPECIFIED_VALUE
            p2_set = data[60] != UNSPECIFIED_VALUE and data[61] != UNSPECIFIED_VALUE
            if not p1_set:
                # No period 1 schedule → device is in NONSTOP_24H mode
                # (or filtration is not actually configured on PROFI).
                mode = AsekoFiltrationMode.NONSTOP_24H
            elif p2_set or bool(b & FILTRATION_PERIOD2_ENABLED_MASK):
                # Period 2 enabled (per byte 37 bit 0x20) or period 2 times
                # are present in bytes 60-63.
                mode = AsekoFiltrationMode.TIMER_PERIOD_1_AND_2
            else:
                mode = AsekoFiltrationMode.TIMER_PERIOD_1

        if mode is None:
            return

        unit.filtration_mode = mode
        # Mirror onto the legacy boolean for backwards compatibility.
        unit.filtration_nonstop24 = mode == AsekoFiltrationMode.NONSTOP_24H

    @staticmethod
    def _fill_consumable_data(unit: AsekoDevice, data: bytes) -> None:
        masks = ACTUATOR_MASKS.get(unit.device_type)
        if masks is None:
            _LOGGER.warning("No actuator masks for device type %s", unit.device_type)
            return

        if masks.filtration:
            unit.filtration_pump_running = bool(data[29] & masks.filtration)

        if masks.cl:
            unit.cl_pump_running = bool(data[29] & masks.cl)

        if masks.ph_minus:
            unit.ph_minus_pump_running = bool(data[29] & masks.ph_minus)

        # Algicide and flocculant share bit 0x20 on some device types and byte 37
        # (AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING) is unreliable (0xFF = unspecified) on several devices.
        # Instead, use flowrate presence (non-0xFF in the respective flowrate byte) as
        # the pump-existence discriminator. _fill_flowrate_data must run first.
        if masks.algicide and unit.flowrate_algicide is not None:
            unit.algicide_pump_running = bool(data[29] & masks.algicide)

        if masks.flocculant and unit.flowrate_floc is not None:
            unit.floc_pump_running = bool(data[29] & masks.flocculant)

        if masks.oxy and unit.flowrate_oxy is not None:
            unit.oxy_pump_running = bool(data[29] & masks.oxy)

        # Issue #133: on HOME v7 firmware B, byte[29] bit 3 stays set even
        # when the user has manually switched the pump off on the unit
        # (the override state lives in byte[37], not byte[29]). Trust the
        # explicit OFF_MANUAL mode flag instead of the schedule-driven bit.
        # Gated on HOME so SALT / OXY / NET / PROFI behaviour is unchanged.
        if (
            unit.device_type == AsekoDeviceType.HOME
            and unit.filtration_mode == AsekoFiltrationMode.OFF_MANUAL
            and unit.filtration_pump_running is True
        ):
            _LOGGER.debug(
                "Manual OFF override active (filtration_mode=OFF_MANUAL) — "
                "forcing filtration_pump_running to False (byte[29]=0x%02x)",
                data[29],
            )
            unit.filtration_pump_running = False

    @staticmethod
    def decode(data: bytes) -> AsekoDevice:
        unit_type = AsekoDecoder._unit_type(data)
        probes = AsekoDecoder._configuration(data, unit_type)
        ts = AsekoDecoder._timestamp(data)
        _LOGGER.debug("Decoded timestamp = %s (raw: %s)", ts, data[6:12].hex())

        # Filtration schedule, by device type (PR #122):
        #  - NET / unknown types have no filtration → no schedule reported.
        #  - The second period can be switched off on the unit while it keeps
        #    reporting the last-configured start2/stop2 times (bytes 60-63);
        #    byte 37 bit 0x20 is the enable flag on the verified types.
        has_filtration = unit_type in FILTRATION_TYPES
        filtration2_enabled = has_filtration and (
            bool(data[37] & FILTRATION_PERIOD2_ENABLED_MASK)
            if unit_type in FILTRATION_PERIOD2_FLAG_TYPES
            else True
        )
        # Issue #129: gate backwash schedule + active bit on device type so
        # measurement-only units (NET) do not surface phantom backwash entities
        # from non-0xFF frame data.
        has_backwash = unit_type in BACKWASH_TYPES
        has_water_level = unit_type in WATER_LEVEL_TYPES

        device = AsekoDevice(
            serial_number=int.from_bytes(data[0:4], "big"),
            device_type=unit_type,
            configuration=probes,
            timestamp=ts,
            water_temperature=int.from_bytes(data[25:27], "big") / 10,
            water_flow_to_probes=(data[28] == WATER_FLOW_TO_PROBES),
            required_water_temperature=AsekoDecoder._normalize_value(data[55], int),
            start1=AsekoDecoder._time(data[56:58]) if has_filtration else None,
            stop1=AsekoDecoder._time(data[58:60]) if has_filtration else None,
            start2=AsekoDecoder._time(data[60:62]) if filtration2_enabled else None,
            stop2=AsekoDecoder._time(data[62:64]) if filtration2_enabled else None,
            backwash_every_n_days=(
                AsekoDecoder._normalize_value(data[68], int) if has_backwash else None
            ),
            backwash_time=(AsekoDecoder._time(data[69:71]) if has_backwash else None),
            backwash_duration=(
                data[71] * 10
                if has_backwash and data[71] != UNSPECIFIED_VALUE
                else None
            ),
            pool_volume=int.from_bytes(data[92:94], "big"),
            # max_filling_time is stored in minutes (verified against Aseko Live
            # app for serial 110071590: raw bytes 94:95 = 0x003c = 60, app shows
            # 60 min). The earlier "× 30 seconds" interpretation was wrong.
            # See water_level_backwash_analysis.md and home_device_analysis.md
            # (Bug 1, the 30 s hypothesis from DomSchCoding #100 was rejected by
            # the live app screenshot).
            #
            # Gated on WATER_LEVEL_TYPES: NET (Aqua NET) and PROFI have no filling
            # valve, so bytes 94-95 either carry unrelated data or are 0xFFFF.
            # A bare int.from_bytes(..., "big") would otherwise turn 0xFFFF into
            # 65535 — fix that by normalising to None on 0xFFFF as well.
            max_filling_time=(
                AsekoDecoder._max_filling_time_from_bytes(data[94:96])
                if has_water_level
                else None
            ),
            delay_after_startup=int.from_bytes(data[74:76], "big"),
            delay_after_dose=int.from_bytes(data[106:108], "big"),
        )

        AsekoDecoder._fill_ph_data(device, data)
        AsekoDecoder._fill_redox_data(device, data)
        AsekoDecoder._fill_clf_data(device, data)
        AsekoDecoder._fill_salt_unit_data(device, data)
        AsekoDecoder._fill_required_data(device, data)
        # Flowrate must be decoded before consumable data: pump presence for
        # algicide/flocculant is determined by whether the flowrate byte is set (≠ 0xFF).
        AsekoDecoder._fill_flowrate_data(device, data)
        # Filtration mode must be decoded before consumable data (Issue #133):
        # the OFF_MANUAL state in byte[37] short-circuits
        # `filtration_pump_running` in `_fill_consumable_data`.
        AsekoDecoder._fill_filtration_mode(device, data)
        AsekoDecoder._fill_consumable_data(device, data)
        AsekoDecoder._fill_home_water_level_data(device, data)
        AsekoDecoder._fill_alarm_data(device, data)
        AsekoDecoder._fill_heating_demand(device, data)
        AsekoDecoder._fill_backwash_active(device, data)
        AsekoDecoder._fill_backwash_schedule(device)

        return device
