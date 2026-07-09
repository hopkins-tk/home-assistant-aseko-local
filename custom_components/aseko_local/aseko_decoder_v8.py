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
        # outs[2] = filtration pump running. SALT NET uses 2=ON, 0=OFF;
        # NET v8 uses 1=ON, 0=OFF. The "any non-zero ⇒ running" rule
        # (bool(outs2)) handles both.
        outs2 = _get(outs, 2)
        filtration_pump_running = bool(outs2) if outs2 is not None else None

        outs8 = _get(outs, 8)
        ph_minus_pump_running = bool(outs8) if outs8 is not None else None

        outs9 = _get(outs, 9)
        cl_pump_running = bool(outs9) if outs9 is not None else None

        # outs[15] = algicide pump running (SALT NET only, best guess).
        # Gated on device_type to avoid phantom "False" on NET frames
        # where outs[15] is zero-padded.
        algicide_pump_running: bool | None = None
        if is_salt_net:
            outs15 = _get(outs, 15)
            algicide_pump_running = bool(outs15) if outs15 is not None else None

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
        delay_after_startup = _get(areqs, 17)
        delay_after_dose = _get(areqs, 18)

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
            cl_pump_running=cl_pump_running,
            algicide_pump_running=algicide_pump_running,
            flowrate_algicide=flowrate_algicide,
            flowrate_ph_minus=60,
            flowrate_chlor=60,
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
