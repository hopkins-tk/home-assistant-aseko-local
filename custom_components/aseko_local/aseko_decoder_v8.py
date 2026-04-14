"""Decoder for Aseko fw v8 text frames."""

import logging
import re
from datetime import datetime

import homeassistant.util

from .aseko_data import AsekoDevice, AsekoDeviceType, AsekoProbeType
from .const import UNSPECIFIED_V8

_LOGGER = logging.getLogger(__name__)

# Regex to extract each named section from the frame body.
# Matches "sectionname: <values>" up to the next section keyword or end of string.
_SECTION_RE = re.compile(r"(\w+):\s*(.*?)(?=\s+\w+:|$)", re.DOTALL)

# Maps the header type field (f2) to the corresponding device type.
_V8_DEVICE_TYPE_BY_HEADER: dict[int, AsekoDeviceType] = {
    804: AsekoDeviceType.NET,
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
            raise ValueError(f"v8 frame: unknown device type {header_type}")

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

        # --- Measurements ---
        water_temperature_raw = _probe_value(ins, 0)
        water_temperature = water_temperature_raw / 10 if water_temperature_raw is not None else None

        water_flow_raw = _get(ins, 8)
        water_flow_to_probes = bool(water_flow_raw) if water_flow_raw is not None else None

        ph_raw = _probe_value(ains, 0)
        ph = ph_raw / 100 if ph_raw is not None else None

        redox_raw = _probe_value(ains, 6)
        redox = redox_raw if redox_raw is not None else None

        # --- Pump states ---
        outs2 = _get(outs, 2)
        filtration_pump_running = bool(outs2) if outs2 is not None else None

        # --- Configuration / setpoints ---
        areqs0 = _get(areqs, 0)
        required_ph = areqs0 / 10 if areqs0 is not None else None

        areqs1 = _get(areqs, 1)
        required_redox = areqs1 * 10 if areqs1 is not None else None

        pool_volume = _get(areqs, 14)
        delay_after_startup = _get(areqs, 17)
        delay_after_dose = _get(areqs, 18)

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
            filtration_pump_running=filtration_pump_running,
            required_ph=required_ph,
            required_redox=required_redox,
            pool_volume=pool_volume,
            delay_after_startup=delay_after_startup,
            delay_after_dose=delay_after_dose,
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
            _LOGGER.warning(
                "v8 frame contains invalid time %02d:%02d (%s) — using now()",
                hour,
                minute,
                exc,
            )
            return now
