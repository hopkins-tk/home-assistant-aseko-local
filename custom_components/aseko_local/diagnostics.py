"""Diagnostics support for Aseko Local.

Accessible via Settings → Devices & Services → Aseko Local → Download Diagnostics.

The download contains:
- Integration configuration (host/port, options)
- Per-device: decoded state, consumption counters, annotated raw frame hex dump

The annotated frame table is designed so users can paste it directly into a
GitHub issue to help developers reverse-engineer unknown byte positions
(e.g. pH+ pump state, NET+ flocculant mask).
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AsekoLocalConfigEntry
from .consumption_tracker import PUMP_KEYS

# Fields that may contain personally identifying information
_REDACT = {"host", "unique_id"}

# Maps byte index → human-readable name (for the annotated hex table)
_BYTE_LABELS: dict[int, str] = {
    0: "serial_number[0]",
    1: "serial_number[1]",
    2: "serial_number[2]",
    3: "serial_number[3]",
    4: "probe_info / device_type",
    5: "unknown",
    6: "year (+ 2000)",
    7: "month",
    8: "day",
    9: "hour",
    10: "minute",
    11: "second",
    12: "unknown",
    13: "unknown",
    14: "ph_value[hi]",
    15: "ph_value[lo]  (÷100 = pH)",
    16: "clf_or_redox[hi]",
    17: "clf_or_redox[lo]",
    18: "redox[hi] (PROFI)",
    19: "redox[lo] (PROFI)",
    20: "salinity (SALT) / cl_free_mv[hi] (NET)",
    21: "electrolyzer_power (SALT) / cl_free_mv[lo] (NET)",
    22: "unknown",
    23: "unknown",
    24: "unknown",
    25: "water_temperature[hi]",
    26: "water_temperature[lo]  (÷10 = °C)",
    27: "unknown",
    28: "water_flow_to_probes",
    29: "pump_state bitmask ← KEY BYTE",
    30: "unknown",
    31: "unknown",
    32: "unknown",
    33: "unknown",
    34: "unknown",
    35: "unknown",
    36: "unknown",
    37: "pump bitmask algicide_configured or flocculant_configured",
    52: "required_ph  (÷10 = pH)",
    53: "required_clf_or_redox",
    54: "required_algicide_or_floc",
    55: "required_water_temperature",
    56: "filtration_start1_hour",
    57: "filtration_start1_minute",
    58: "filtration_stop1_hour",
    59: "filtration_stop1_minute",
    60: "filtration_start2_hour",
    61: "filtration_start2_minute",
    62: "filtration_stop2_hour",
    63: "filtration_stop2_minute",
    68: "backwash_every_n_days",
    69: "backwash_time_hour",
    70: "backwash_time_minute",
    71: "backwash_duration (×10 s)",
    74: "delay_after_startup[hi]",
    75: "delay_after_startup[lo]",
    92: "pool_volume[hi]",
    93: "pool_volume[lo]",
    94: "max_filling_time[hi]",
    95: "max_filling_time[lo] / flowrate_ph_minus (ml/min)",
    96: "unknown",
    97: "flowrate_ph_plus (ml/min) – byte position uncertain",
    98: "unknown",
    99: "flowrate_chlor (ml/min)",
    100: "unknown",
    101: "flowrate_floc (ml/min)",
    102: "unknown",
    103: "flowrate_algicide (ml/min)",
    104: "unknown",
    105: "unknown",
    106: "delay_after_dose[hi]",
    107: "delay_after_dose[lo]",
}

# Known field labels for v8 text frame sections
_V8_INS_LABELS: dict[int, str] = {
    0: "water_temperature_raw (÷10 = °C)",
    8: "water_flow_to_probes (1=flowing)",
    13: "unknown",
    14: "unknown",
    15: "unknown",
    16: "hour",
    17: "minute",
    18: "unknown",
}

_V8_AINS_LABELS: dict[int, str] = {
    0: "pH × 100 (-500=absent; ÷100 = pH)",
    1: "unknown (tracks pH)",
    2: "unknown",
    3: "unknown",
    6: "redox (mV; -500=absent)",
    7: "unknown (tracks redox)",
}

_V8_OUTS_LABELS: dict[int, str] = {
    2: "filtration_pump_running (1=on)",
    8: "ph_minus_pump_running (1=dosing)",
}

_V8_AREQS_LABELS: dict[int, str] = {
    0: "required_pH × 10 (÷10 = pH)",
    1: "required_redox / 10 (×10 = mV)",
    2: "unknown",
    3: "unknown",
    4: "unknown",
    5: "unknown",
    6: "unknown",
    10: "unknown",
    12: "unknown",
    14: "pool_volume (m³)",
    15: "unknown",
    16: "unknown",
    17: "delay_after_startup (min)",
    18: "delay_after_dose (min)",
    19: "unknown",
    21: "unknown",
    25: "unknown",
}

_V8_REQS_LABELS: dict[int, str] = {
    7: "filtration_hours_per_day (unconfirmed)",
}

_SECTION_RE = re.compile(r"(\w+):\s*(.*?)(?=\s+\w+:|$)", re.DOTALL)


def _annotated_frame(raw: bytes) -> list[dict[str, Any]]:
    """Return a list of dicts describing every byte in the raw frame."""
    rows = []
    for i, b in enumerate(raw):
        word = int.from_bytes(raw[i : i + 2], "big") if i + 1 < len(raw) else None
        rows.append(
            {
                "byte": i,
                "hex": f"0x{b:02x}",
                "dec": b,
                "word_dec": word,
                "label": _BYTE_LABELS.get(i, ""),
            }
        )
    return rows


def _annotated_v8_section(
    values: list[int], labels: dict[int, str]
) -> list[dict[str, Any]]:
    """Return annotated list for a single v8 section."""
    return [
        {"index": i, "value": v, "label": labels.get(i, "")}
        for i, v in enumerate(values)
    ]


def _parse_v8_frame(raw: bytes) -> dict[str, Any] | None:
    """Parse a v8 text frame into annotated sections. Returns None on failure."""
    try:
        text = raw.decode("ascii", errors="replace").strip()
    except Exception:
        return None

    if not text.startswith("{") or not text.endswith("}"):
        return None
    body = text[1:-1].strip()

    # Extract header tokens: v1 <serial> <f2> <f3> <f4>
    header_match = re.match(r"^(v\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)", body)
    header: dict[str, Any] = {}
    if header_match:
        header = {
            "version": header_match.group(1),
            "serial_number": int(header_match.group(2)),
            "device_type_raw": int(header_match.group(3)),
            "f3": header_match.group(4),
            "f4": header_match.group(5),
        }

    sections: dict[str, Any] = {}
    section_labels = {
        "ins": _V8_INS_LABELS,
        "ains": _V8_AINS_LABELS,
        "outs": _V8_OUTS_LABELS,
        "areqs": _V8_AREQS_LABELS,
        "reqs": _V8_REQS_LABELS,
    }
    for match in _SECTION_RE.finditer(body):
        name = match.group(1)
        raw_values_str = match.group(2).strip()
        try:
            values = [int(v) for v in raw_values_str.split()]
        except ValueError:
            sections[name] = {"raw": raw_values_str}
            continue
        labels = section_labels.get(name, {})
        sections[name] = {
            "values": values,
            "annotated": _annotated_v8_section(values, labels),
        }

    return {
        "raw_text": text,
        "length_bytes": len(raw),
        "header": header,
        "sections": sections,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices() or []

    devices_info: list[dict[str, Any]] = []

    for device in devices:
        serial = device.serial_number

        # --- Decoded device state ---
        device_state: dict[str, Any] = {
            "serial_number": serial,
            "device_type": device.device_type.value if device.device_type else None,
            "configuration": [p.value for p in (device.configuration or [])],
            "online": device.online(),
            "timestamp": str(device.timestamp),
            "water_temperature": device.water_temperature,
            "ph": device.ph,
            "cl_free": device.cl_free,
            "cl_free_mv": device.cl_free_mv,
            "redox": device.redox,
            "salinity": device.salinity,
            "electrolyzer_power": device.electrolyzer_power,
            "electrolyzer_active": device.electrolyzer_active,
            "electrolyzer_direction": (
                device.electrolyzer_direction.value
                if device.electrolyzer_direction
                else None
            ),
            "water_flow_to_probes": device.water_flow_to_probes,
            "filtration_pump_running": device.filtration_pump_running,
            "cl_pump_running": device.cl_pump_running,
            "ph_minus_pump_running": device.ph_minus_pump_running,
            "ph_plus_pump_running": device.ph_plus_pump_running,
            "algicide_pump_running": device.algicide_pump_running,
            "floc_pump_running": device.floc_pump_running,
            "flowrate_chlor_ml_min": device.flowrate_chlor,
            "flowrate_ph_minus_ml_min": device.flowrate_ph_minus,
            "flowrate_ph_plus_ml_min": device.flowrate_ph_plus,
            "flowrate_algicide_ml_min": device.flowrate_algicide,
            "flowrate_floc_ml_min": device.flowrate_floc,
        }

        # --- Consumption counters ---
        tracker = coordinator.get_tracker(serial) if serial is not None else None
        consumption: dict[str, Any] = {}
        if tracker is not None:
            for key in PUMP_KEYS:
                consumption[key] = {
                    "canister_ml": round(tracker.get(key, "canister"), 1),
                    "total_ml": round(tracker.get(key, "total"), 1),
                }

        # --- Raw frame (v7 binary) ---
        raw_info: dict[str, Any] = {"available": False}
        if serial is not None:
            raw = coordinator.get_raw_frame(serial)
            if raw is not None:
                raw_info = {
                    "available": True,
                    "hex_dump": raw.hex(),
                    "length_bytes": len(raw),
                    "byte_29_pump_state_hex": f"0x{raw[29]:02x}"
                    if len(raw) > 29
                    else "n/a",
                    "byte_29_pump_state_bin": f"0b{raw[29]:08b}"
                    if len(raw) > 29
                    else "n/a",
                    "byte_37_algicide_cfg_hex": f"0x{raw[37]:02x}"
                    if len(raw) > 37
                    else "n/a",
                    "annotated_table": _annotated_frame(raw),
                }

        # --- Raw frame (v8 text) ---
        v8_raw_info: dict[str, Any] = {"available": False}
        if serial is not None:
            v8_raw = coordinator.get_v8_frame(serial)
            if v8_raw is not None:
                parsed = _parse_v8_frame(v8_raw)
                if parsed is not None:
                    v8_raw_info = {"available": True, **parsed}
                else:
                    v8_raw_info = {
                        "available": True,
                        "raw_text": v8_raw.decode("ascii", errors="replace").strip(),
                        "length_bytes": len(v8_raw),
                        "parse_error": "Could not parse v8 frame structure",
                    }

        # --- Partial frame (device sent fewer bytes than the expected 120) ---
        partial_info: dict[str, Any] = {"available": False}
        if serial is not None:
            partial = coordinator.get_partial_frame(serial)
            if partial is not None:
                partial_info = {
                    "available": True,
                    "hex_dump": partial.hex(),
                    "length_bytes": len(partial),
                    "note": (
                        f"Device sent {len(partial)} bytes instead of the expected 120. "
                        "The frame could not be decoded. Please share this diagnostics "
                        "download in a GitHub issue to help add support for this device."
                    ),
                    "annotated_table": _annotated_frame(partial),
                }

        devices_info.append(
            {
                "device": device_state,
                "consumption": consumption,
                "raw_frame_v7": raw_info,
                "raw_frame_v8": v8_raw_info,
                "partial_frame": partial_info,
            }
        )

    return {
        "config_entry": async_redact_data(
            {**config_entry.data, **config_entry.options},
            _REDACT,
        ),
        "devices": devices_info,
    }
