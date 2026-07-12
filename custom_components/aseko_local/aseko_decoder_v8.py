"""Decoder for Aseko fw v8 text frames."""

import logging
import re
from datetime import datetime

import homeassistant.util

from .aseko_data import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoFiltrationMode,
    AsekoProbeType,
)
from .aseko_v8_helpers import (
    AsekoV8_CAPABILITY_FLAGS,
    V8_DEFAULT_PUMP_FLOWRATE_ML_MIN,
    installed_pumps_from_fncs,
)
from .aseko_v8_dump import V8FrameDumper
from .const import UNSPECIFIED_V8

_LOGGER = logging.getLogger(__name__)

# Regex to extract each named section from the frame body.
# Matches "sectionname: <values>" up to the next section keyword or end of string.
_SECTION_RE = re.compile(r"(\w+):\s*(.*?)(?=\s+\w+:|$)", re.DOTALL)

# Maps known header type fields (f2) to their device type.
# Unknown values are tolerated — the decoder falls back to NET (all
# V8 frames observed so far use the same layout regardless of f2).
_V8_DEVICE_TYPE_BY_HEADER: dict[int, AsekoDeviceType] = {
    100: AsekoDeviceType.SALT_NET,  # ASIN Aqua Salt NET (Issue #131)
    105: AsekoDeviceType.SALT,  # ASIN Aqua Salt NET
    804: AsekoDeviceType.NET,
    805: AsekoDeviceType.NET,
    812: AsekoDeviceType.NET,
}


def _parse_int_list(text: str) -> list[int]:
    """Parse a space-separated list of integers."""
    return [int(v) for v in text.split()]


def _get(values: list[int], index: int) -> int | None:
    """Return values[index], or None if out of range."""
    return values[index] if index < len(values) else None


def _probe_value(values: list[int], index: int) -> int | None:
    """Return values[index] if present and not the v8 sentinel (-500), else None."""
    v = _get(values, index)
    return None if v is None or v == UNSPECIFIED_V8 else v


class AsekoV8Decoder:
    """Decoder for Aseko fw v8 text frames.

    Frame format:
        {v1 <serial> <f2> <f3> <f4>
         ins: <i0> <i1> ... <iN>
         ains: <a0> <a1> ... <aN>
         outs: <o0> <o1> ... <oN>
         areqs: <r0> <r1> ... <rN>
         reqs: ...
         fncs: ...
         mods: ...
         flags: ...
         crc16: XXXX}\\n
    """

    @classmethod
    def decode(cls, raw: bytes) -> AsekoDevice:
        """Decode a raw v8 frame into an AsekoDevice.

        Raises ValueError if the frame cannot be parsed.
        """
        # Issue #131 triage: dump the raw v8 frame to disk BEFORE
        # any parsing, so a developer (or mirovra) can post-hoc
        # decode a captured frame with `scripts/v8_tools.py` and see
        # every section — including fields we have not yet mapped
        # (e.g. unknown `fncs[6]` codes after a pump-type change).
        # The dumper is a no-op when `DUMP_ENABLED` is False; it
        # dedupes identical frames per serial, so a 1 Hz stream
        # produces at most a handful of lines per hour. Any I/O
        # error inside the dumper is swallowed there and never
        # reaches this function — see aseko_v8_dump.V8FrameDumper.
        V8FrameDumper.get().record(raw)

        try:
            text = raw.decode("ascii", errors="replace").strip()
        except Exception as exc:
            raise ValueError(f"v8 frame is not ASCII: {exc}") from exc

        # Strip surrounding braces
        if not text.startswith("{") or not text.endswith("}"):
            raise ValueError(f"v8 frame missing braces: {text[:40]!r}")
        body = text[1:-1].strip()

        # Parse header: "v1 <serial> <f2> <f3> <f4>"
        header_match = re.match(r"v1\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", body)
        if not header_match:
            raise ValueError(f"v8 frame header not recognised: {body[:60]!r}")
        serial_number = int(header_match.group(1))
        header_type = int(header_match.group(2))
        device_type = _V8_DEVICE_TYPE_BY_HEADER.get(header_type)
        if device_type is None:
            _LOGGER.warning(
                "Unknown V8 header type %s for serial %s — falling back to NET. "
                "Please report this at https://github.com/hopkins-tk/home-assistant-aseko-local/issues",
                header_type,
                serial_number,
            )
            device_type = AsekoDeviceType.NET

        # Parse all sections into a dict of {name: [int, ...]}
        sections: dict[str, list[int]] = {}
        for m in _SECTION_RE.finditer(body):
            name = m.group(1)
            if name == "v1":
                continue  # header — already parsed
            try:
                sections[name] = _parse_int_list(m.group(2))
            except ValueError:
                # crc16 value is hex, not decimal — store empty list, ignore
                sections[name] = []

        ins = sections.get("ins", [])
        ains = sections.get("ains", [])
        outs = sections.get("outs", [])
        areqs = sections.get("areqs", [])
        reqs = sections.get("reqs", [])
        fncs = sections.get("fncs", [])

        # --- Measurements ---
        water_temperature_raw = _probe_value(ins, 0)
        water_temperature = (
            water_temperature_raw / 10 if water_temperature_raw is not None else None
        )

        water_flow_raw = _get(ins, 8)
        water_flow_to_probes = (
            bool(water_flow_raw) if water_flow_raw is not None else None
        )

        ph_raw = _probe_value(ains, 0)
        ph = ph_raw / 100 if ph_raw is not None else None

        redox_raw = _probe_value(ains, 6)
        redox = redox_raw if redox_raw is not None else None

        # --- SALT NET-specific measurements (Issue #131) ---
        # These fields only exist on the SALT NET v8 frame (header[1]=100).
        # On NET v8, ains[8..15] are zero-padded (not absent), so reading
        # them would yield phantom "0" values that the entity layer would
        # surface. We therefore gate the read on device_type == SALT_NET.
        # See salt_net_v8_device_analysis.md §3.4 and §6.2.
        is_salt_net = device_type == AsekoDeviceType.SALT_NET

        # --- Structural capability flags from `fncs[]` ---
        # The `fncs:` (functions) section encodes the device's installed
        # modules. We use `fncs[2]` as a heuristic capability indicator
        # (no public Aseko documentation exists for the v8 frame layout):
        #
        #   fncs[2] = 3  → device has a CL (chlorine) pump module installed
        #   fncs[2] = 1  → device is a SALT family unit (electrolyzer cell,
        #                  no CL pump; algicide pump is on a dedicated port
        #                  routed via fncs[6] = 10 vs. CL's 2)
        #
        # This is the only field that distinguishes "has CL pump" from
        # "no CL pump" in the v8 text frame. Confirmed against:
        #   - NET v8 (110203680, 110999999): fncs[2] = 3, fncs[6] = 2
        #   - SALT NET v8 (110215844, mirovra F1/F2/F3): fncs[2] = 1, fncs[6] = 10
        # See salt_net_v8_device_analysis.md §11.5 (new section).
        #
        # The capability map lives in aseko_v8_helpers.AsekoV8_CAPABILITY_FLAGS.
        # We look it up here once and use it for both the per-pump
        # outs[X] reads and for the final installed_pumps population
        # — single source of truth.
        fncs2 = _get(fncs, 2)
        fncs6 = _get(fncs, 6)
        capability_flags = AsekoV8_CAPABILITY_FLAGS.get(device_type)

        # --- installed_pumps (computed early — gates the outs[X] reads) ---
        # **This is the source of truth for "which dosing pumps does
        # this device physically have", derived from the wire
        # `fncs[2]` (and `fncs[6]`) values.** It is computed *before*
        # the outs[X] reads below so that the per-pump outs reads can
        # use it as a gate: if a pump is not in `installed_pumps`,
        # `outs[i]` is irrelevant (could be 0 because the pump is off
        # OR because the pump does not exist — we cannot tell from
        # outs alone). See aseko_v8_helpers.installed_pumps_from_fncs
        # for the full rationale and salt_net_v8_device_analysis.md
        # §11.5 for context.
        installed_pumps: frozenset[str] = installed_pumps_from_fncs(
            fncs2, fncs6, capability_flags
        )

        # ains[8] = salinity (g/L × 10), only populated on SALT-family devices
        salinity: float | None = None
        # ains[10] = electrolyzer power (g/h × 10, or %), always non-zero when
        # the cell is producing chlorine (no separate "running" boolean)
        electrolyzer_power: float | None = None
        # ains[9] = algicide pump flow rate (ml/min × 10, best guess from F3)
        flowrate_algicide: float | None = None
        if is_salt_net:
            salinity_raw = _probe_value(ains, 8)
            if salinity_raw is not None:
                salinity = salinity_raw / 10

            electrolyzer_power_raw = _probe_value(ains, 10)
            if electrolyzer_power_raw is not None:
                electrolyzer_power = electrolyzer_power_raw / 10

            flowrate_algicide_raw = _probe_value(ains, 9)
            if flowrate_algicide_raw is not None:
                flowrate_algicide = flowrate_algicide_raw / 10

        electrolyzer_active = electrolyzer_power is not None and electrolyzer_power > 0

        # --- Pump states ---
        # **Every `*_pump_running` field is gated on the corresponding
        # pump being in `installed_pumps`.** This is critical: a
        # zero `outs[i]` byte is ambiguous (pump off OR pump absent)
        # and only `fncs[2]`/`fncs[6]` tell us which one it is. Without
        # the gate, a SALT NET carrying non-zero data at outs[9] (CL
        # pump slot) would incorrectly report `cl_pump_running = True`
        # even though the device has no CL pump.
        #
        # `filtration_pump_running` is the one exception: every v8
        # device that has a filtration schedule reports outs[2]. The
        # pump presence is determined by the schedule bytes (start1,
        # etc.), not by fncs[2].
        outs2 = _get(outs, 2)
        filtration_pump_running = bool(outs2) if outs2 is not None else None

        outs8 = _get(outs, 8)
        if "ph_minus" in installed_pumps:
            ph_minus_pump_running = bool(outs8) if outs8 is not None else None
        else:
            ph_minus_pump_running = None

        # CL-pump running bit. Gated on `cl` being in installed_pumps.
        if "cl" in installed_pumps and capability_flags is not None:
            outs9 = _get(outs, capability_flags.outs_cl or 0)
            cl_pump_running: bool | None = bool(outs9) if outs9 is not None else None
        else:
            cl_pump_running = None

        # pH+ pump: not present on any v8 device captured so far
        # (NET v8, SALT NET v8). Gate on installed_pumps for future
        # proofing.
        if (
            "ph_plus" in installed_pumps
            and capability_flags is not None
            and capability_flags.outs_ph_plus is not None
        ):
            ph_plus_pump_running: bool | None = (
                bool(_get(outs, capability_flags.outs_ph_plus))
                if len(outs) > capability_flags.outs_ph_plus
                else None
            )
        else:
            ph_plus_pump_running = None

        # Flocculant pump: not present on any v8 device captured so far.
        # SALT NET has algicide instead, on a different physical port.
        if (
            "floc" in installed_pumps
            and capability_flags is not None
            and capability_flags.outs_floc is not None
        ):
            floc_pump_running: bool | None = (
                bool(_get(outs, capability_flags.outs_floc))
                if len(outs) > capability_flags.outs_floc
                else None
            )
        else:
            floc_pump_running = None

        # OXY pump: not present on any v8 device captured so far.
        if (
            "oxy" in installed_pumps
            and capability_flags is not None
            and capability_flags.outs_oxy is not None
        ):
            oxy_pump_running: bool | None = (
                bool(_get(outs, capability_flags.outs_oxy))
                if len(outs) > capability_flags.outs_oxy
                else None
            )
        else:
            oxy_pump_running = None

        # outs[15] = algicide pump running (SALT NET only, best guess).
        # Gated on `algicide` being in installed_pumps.
        if (
            "algicide" in installed_pumps
            and capability_flags is not None
            and capability_flags.outs_algicide is not None
        ):
            algicide_pump_running: bool | None = (
                bool(_get(outs, capability_flags.outs_algicide))
                if len(outs) > capability_flags.outs_algicide
                else None
            )
        else:
            algicide_pump_running = None

        # --- No-flow alarm (SALT NET v8 dual encoding) ---
        # Reported in two places: ins[12] bit 0x100 AND flags[3] == 1.
        # We use ins[12] because flags[] is otherwise unused by NET v8.
        # This is the v8 counterpart of the v7 byte[13] bit 0x04 alarm;
        # both decoders write the SAME AsekoDevice field
        # (`alarm_no_flow_to_probes`) so the binary sensor in binary_sensor.py
        # is protocol-agnostic.  See AsekoDevice.alarm_no_flow_to_probes
        # docstring and salt_net_v8_device_analysis.md §10.
        alarm_no_flow_to_probes = bool(ins[12] & 0x100) if len(ins) > 12 else None

        # --- Configuration / setpoints ---
        areqs0 = _get(areqs, 0)
        required_ph = areqs0 / 10 if areqs0 is not None else None

        areqs1 = _get(areqs, 1)
        required_redox = areqs1 * 10 if areqs1 is not None else None

        pool_volume = _get(areqs, 14)
        # v8 firmware reports `delay_after_startup` and `delay_after_dose` in
        # MINUTES (confirmed vs. Aseko app on serial 110215844: 5 min, 5 min;
        # on serial 110203680: 2 min, 2 min). The v7 firmware reports the same
        # fields in SECONDS (e.g. 120 = 2 min). To keep the `AsekoDevice.delay_*`
        # field semantically consistent with v7 and the sensor unit
        # (`UnitOfTime.SECONDS` in sensor.py), we multiply v8 minutes by 60.
        # This preserves the numeric value of existing v7 user history
        # (a 2-min delay stays "120 s", not "2 min") at the cost of v8
        # users seeing the raw app-minute value scaled to seconds.
        delay_after_startup_v8 = _get(areqs, 17)
        delay_after_startup = (
            delay_after_startup_v8 * 60 if delay_after_startup_v8 is not None else None
        )
        delay_after_dose_v8 = _get(areqs, 18)
        delay_after_dose = (
            delay_after_dose_v8 * 60 if delay_after_dose_v8 is not None else None
        )

        # SALT NET-specific setpoint: required algicide dose (ml/m³/day)
        # at areqs[25]. Gated on device_type to avoid phantom "0" on NET
        # frames where areqs is zero-padded to length 25+.
        required_algicide: int | None = None
        if is_salt_net:
            required_algicide = _get(areqs, 25)

        # SALT NET: filtration hours per day at reqs[7] (probable).
        # Gated on device_type for the same reason.
        filtration_hours_per_day: int | None = None
        if is_salt_net:
            filtration_hours_per_day = _get(reqs, 7)

        # Filtration mode for SALT NET v8 (Issue #131 §6.2, Issue #133).
        # The v8 frame does NOT carry a byte[37]-style mode flag on SALT
        # NET, so the mode is derived from the available signals:
        #   - outs[2] = 0   → filtration pump off  → OFF_MANUAL
        #   - outs[2] != 0  + filtration_hours_per_day == 24 → NONSTOP_24H
        #   - outs[2] != 0  + filtration_hours_per_day < 24  → TIMER_PERIOD_1
        #     (SALT NET firmware does not expose a second filtration
        #      period in the decoded sections, so we cannot distinguish
        #      TIMER_PERIOD_1 from TIMER_PERIOD_1_AND_2 without a
        #      dedicated frame; this matches the OLD HOME v7 firmware A
        #      behaviour which also collapses P1 and P1&P2 into one
        #      "timer" state — see issue-133 §6.2 "Old encoding".)
        #   - filtration_hours_per_day is None → unknown, leave as None.
        filtration_mode: AsekoFiltrationMode | None = None
        if is_salt_net and filtration_pump_running is not None:
            if not filtration_pump_running:
                filtration_mode = AsekoFiltrationMode.OFF_MANUAL
            elif filtration_hours_per_day == 24:
                filtration_mode = AsekoFiltrationMode.NONSTOP_24H
            elif filtration_hours_per_day is not None:
                filtration_mode = AsekoFiltrationMode.TIMER_PERIOD_1
            # else: leave as None (schedule not yet known)

        # --- Probe configuration ---
        # Derive which probes are installed from which ains slots report real values.
        configuration: set[AsekoProbeType] = set()
        if _probe_value(ains, 0) is not None:
            configuration.add(AsekoProbeType.PH)
        if _probe_value(ains, 6) is not None:
            configuration.add(AsekoProbeType.REDOX)

        # --- Timestamp ---
        # The device reports local hour (ins[16]) and minute (ins[17]).
        # We use HA's clock for the date and replace hour/minute from the device.
        timestamp = cls._build_timestamp(ins)

        return AsekoDevice(
            serial_number=serial_number,
            device_type=device_type,
            configuration=configuration,
            installed_pumps=installed_pumps,
            timestamp=timestamp,
            water_temperature=water_temperature,
            water_flow_to_probes=water_flow_to_probes,
            ph=ph,
            redox=redox,
            salinity=salinity,
            electrolyzer_power=electrolyzer_power,
            electrolyzer_active=electrolyzer_active,
            filtration_pump_running=filtration_pump_running,
            ph_minus_pump_running=ph_minus_pump_running,
            ph_plus_pump_running=ph_plus_pump_running,
            cl_pump_running=cl_pump_running,
            algicide_pump_running=algicide_pump_running,
            floc_pump_running=floc_pump_running,
            oxy_pump_running=oxy_pump_running,
            flowrate_algicide=flowrate_algicide,
            # v8 firmware does NOT transmit per-pump flow-rate bytes
            # (v7 byte[95] / byte[99] / byte[101] have no v8
            # equivalent). The dosing rate in ml/min is constant on v8
            # because Aseko uses the same physical pump model across the
            # v8 product line and omits the value from the wire record.
            # See aseko_v8_helpers.V8_DEFAULT_PUMP_FLOWRATE_ML_MIN.
            flowrate_ph_minus=V8_DEFAULT_PUMP_FLOWRATE_ML_MIN,
            flowrate_chlor=V8_DEFAULT_PUMP_FLOWRATE_ML_MIN,
            required_ph=required_ph,
            required_redox=required_redox,
            required_algicide=required_algicide,
            pool_volume=pool_volume,
            delay_after_startup=delay_after_startup,
            delay_after_dose=delay_after_dose,
            filtration_hours_per_day=filtration_hours_per_day,
            filtration_mode=filtration_mode,
            alarm_no_flow_to_probes=alarm_no_flow_to_probes,
        )

    @classmethod
    def _build_timestamp(cls, ins: list[int]) -> datetime:
        """Build a datetime using today's date and the device-reported hour/minute."""
        now = datetime.now(tz=homeassistant.util.dt.get_default_time_zone())
        hour = _get(ins, 16)
        minute = _get(ins, 17)
        if hour is None or minute is None:
            return now
        try:
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError as exc:
            _LOGGER.debug(
                "v8 frame contains invalid time %02d:%02d (%s) — using now()",
                hour,
                minute,
                exc,
            )
            return now
