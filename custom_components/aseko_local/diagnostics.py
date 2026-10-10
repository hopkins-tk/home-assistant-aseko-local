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
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AsekoLocalConfigEntry
from .decoding.frames.v8 import parse_v8_sections
from .decoding.profiles import profile_named
from .trackers.consumption import PUMP_KEYS

if TYPE_CHECKING:
    from .coordinator import AsekoLocalDataUpdateCoordinator
    from .models import AsekoDevice

# Fields that may contain personally identifying information
_REDACT = {"host", "unique_id"}

# Maps byte index → human-readable name (for the annotated hex table)
_BYTE_LABELS: dict[int, str] = {
    0: "serial_number[0]",
    1: "serial_number[1]",
    2: "serial_number[2]",
    3: "serial_number[3]",
    4: "probe_info / device_type",
    5: "segment marker (0x01 live, 0x03 settings, 0x02 flow rates)",
    6: "year (+ 2000)",
    7: "month",
    8: "day",
    9: "hour",
    10: "minute",
    11: "second",
    12: "dosing_warning bitmask (0x20=Cl/disinfectant, 0x40=pH) ← HOME",
    13: "alarm bitmask (0x01=Cl/ORP doses, 0x02=pH doses, 0x04=no flow, 0x08=rapid pH)",
    14: "ph_value[hi]",
    15: "ph_value[lo]  (÷100 = pH)",
    16: "clf_or_redox[hi]",
    17: "clf_or_redox[lo]",
    18: "redox[hi] (PROFI)",
    19: "redox[lo] (PROFI)",
    20: "salinity (SALT) / free_chlorine_mv[hi] (NET)",
    21: "chlorine_production_measured (SALT) / free_chlorine_mv[lo] (NET)",
    22: "settings (0x01 heating time window, 0x02 by outside temp, 0x04 winter mode, 0x08 VS pump enabled, 0x10 backwash schedule, 0x20 outside temp below)",
    23: "air_temperature[hi]",
    24: "air_temperature[lo]  (signed, ÷10 = °C; SALT confirmed)",
    25: "water_temperature[hi]",
    26: "water_temperature[lo]  (÷10 = °C)",
    27: "water_level (cm; 0xFE = no level sensor)",
    28: "water_flow_to_probes",
    29: "outputs (0x01 backwash, 0x02 refilling, 0x04 heating, 0x08 filtration, 0x10/0x20/0x40/0x80 pumps by model; SALT 0x10 electrolysis, 0x40 polarity right)",
    30: "unknown",
    31: "unknown",
    32: "unknown",
    33: "unknown",
    34: "unknown",
    35: "unknown",
    36: "unknown",
    37: "settings (0x02 flow detection, 0x04 menu open, 0x08 heating control, 0x10/0x20 filtration periods, 0x40 waterlevel, 0x80 SALT algicide routing / HOME antifreeze)",
    38: "flags (0x10 heating linked to filtration; 0x01 unknown; 0x20 / 0xA1 around winter mode)",
    39: "checksum of bytes 0-38 (0xAA xor)",
    45: "segment marker",
    52: "ph_target  (÷10 = pH)",
    53: "required_clf_or_redox",
    54: "required_algicide_or_floc",
    55: "water_temperature_target",
    56: "filtration_start1_hour",
    57: "filtration_start1_minute",
    58: "filtration_stop1_hour",
    59: "filtration_stop1_minute",
    60: "filtration_start2_hour",
    61: "filtration_start2_minute",
    62: "filtration_stop2_hour",
    63: "filtration_stop2_minute",
    68: "backwash_interval",
    69: "backwash_time_hour",
    70: "backwash_time_minute",
    71: "backwash_duration (×10 s)",
    72: "algaecide_dose_target (HOME / OXY)",
    74: "startup_delay[hi]",
    75: "startup_delay[lo]",
    76: "max_refill_time[hi] (seconds)",
    77: "max_refill_time[lo] (seconds)",
    78: "live state (0x80 heating condition met, 0x40 winter mode, 0x0C VS pump type, 0x02 filtration running / 0x01 stopped)",
    79: "checksum of bytes 40-78 (0xAA xor)",
    85: "segment marker",
    92: "pool_volume[hi]",
    93: "pool_volume[lo]",
    94: "unknown",
    95: "ph_minus_flow_rate (ml/min)",
    96: "unknown",
    97: "ph_plus_flow_rate (ml/min) – byte position uncertain",
    98: "unknown",
    99: "chlorine_flow_rate (ml/min)",
    100: "unknown",
    101: "flocculant_flow_rate (ml/min); SALT/PROFI: algaecide_flow_rate instead when byte[37] 0x80 is set",
    102: "water_level_low_alarm (cm)",
    103: "water_level_refill_start (cm) on SALT/HOME; algaecide_flow_rate (ml/min) on OXY",
    104: "water_level_refill_stop (cm)",
    105: "water_level_high_alarm (cm)",
    106: "dosing_delay[hi]",
    107: "dosing_delay[lo]",
    112: "ph_minus_concentration (%)",
    115: "max_ph_doses",
    119: "checksum of bytes 80-118 (0xAA xor)",
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
    2: "filtration_relay (1=on)",
    8: "ph_minus_pump_running (1=dosing)",
}

_V8_AREQS_LABELS: dict[int, str] = {
    0: "required_pH × 10 (÷10 = pH)",
    1: "redox_target / 10 (×10 = mV)",
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
    17: "startup_delay (min)",
    18: "dosing_delay (min)",
    19: "unknown",
    21: "unknown",
    25: "unknown",
}

_V8_REQS_LABELS: dict[int, str] = {
    7: "filtration_hours_per_day (unconfirmed)",
}


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
    values: list[int | None], labels: dict[int, str]
) -> list[dict[str, Any]]:
    """Return annotated list for a single v8 section."""
    return [
        {"index": i, "value": v, "label": labels.get(i, "")}
        for i, v in enumerate(values)
    ]


def _parse_v8_frame(raw: bytes) -> dict[str, Any] | None:
    """Parse a v8 text frame into annotated sections. Returns None on failure."""
    text = raw.decode("ascii", errors="replace").strip()

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
    # read the way the decoder reads it: crc16 hexadecimal, an unreadable
    # token None with the rest of its section kept
    for section in parse_v8_sections(body):
        entry: dict[str, Any] = {
            "values": section.values,
            "annotated": _annotated_v8_section(
                section.values, section_labels.get(section.name, {})
            ),
        }
        if section.unreadable:
            entry["raw"] = section.text
            entry["unreadable"] = list(section.unreadable)
        sections[section.name] = entry

    return {
        "raw_text": text,
        "length_bytes": len(raw),
        "header": header,
        "sections": sections,
    }


# the v7 bytes the raw dump spells out on their own
PUMP_STATE_BYTE = 29
ALGICIDE_CONFIG_BYTE = 37


def _byte(raw: bytes, index: int, pattern: str) -> str:
    """``raw[index]`` formatted by ``pattern``, or "n/a" when the frame is shorter."""
    return pattern.format(raw[index]) if len(raw) > index else "n/a"


def _str_or_none(value: object) -> str | None:
    """Render an optional value as a string, keeping None as None.

    ``str(None)`` would produce the literal "None", which reads in a dump like
    a value rather than like "never observed".
    """
    return None if value is None else str(value)


def _reading_overrides(profile_name: str | None) -> dict[str, str]:
    """Feature field -> reading name for what the profile reads its own way."""
    profile = profile_named(profile_name)
    if profile is None:
        return {}
    return {
        feature.field: reading
        for feature, reading in sorted(
            profile.overrides.items(), key=lambda item: item[0].field
        )
    }


def _device_state(device: AsekoDevice) -> dict[str, Any]:
    """Return the decoded state of one unit, as the dump reports it."""
    serial = device.serial_number
    return {
        "serial_number": serial,
        "device_type": device.device_type.value if device.device_type else None,
        # the profile that read the last frame, and the fields it reads a
        # different way than the protocol default (feature field -> reading)
        "profile": getattr(device, "profile", None),
        "reading_overrides": _reading_overrides(getattr(device, "profile", None)),
        # values the parser could not read in the last frame (they read None)
        "frame_problems": list(getattr(device, "frame_problems", ())),
        # How the frame was read: which fields the chosen profile decodes,
        # and the semantic flags it carries.  A field missing from
        # "features" is one this model does not have, not one that failed
        # to decode.
        "features": sorted(device.features),
        # every field the model can have, and those the last frame did not
        # show present -- their entities are unavailable, or still disabled
        "possible_features": sorted(device.possible_features),
        "not_present_now": sorted(device.possible_features - device.present_features),
        "flags": sorted(flag.value for flag in device.flags),
        "configuration": [p.value for p in (device.configuration or [])],
        "online": device.online(),
        "timestamp": str(device.timestamp),
        # the clock as the unit sent it (None: not sent), and how far it is
        # off Home Assistant's -- see trackers/clock.py
        "unit_clock": _str_or_none(getattr(device, "unit_clock", None)),
        "clock_offset_minutes": getattr(device, "clock_offset", None),
        "clock_out_of_sync": getattr(device, "clock_out_of_sync", None),
        "air_temperature": device.air_temperature,
        "water_temperature": device.water_temperature,
        "ph": device.ph,
        "free_chlorine": device.free_chlorine,
        "free_chlorine_mv": device.free_chlorine_mv,
        "redox": device.redox,
        "salinity": device.salinity,
        "chlorine_production": device.chlorine_production,
        "chlorine_production_measured": device.chlorine_production_measured,
        "electrolysis_running": device.electrolysis_running,
        "electrode_polarity": (
            device.electrode_polarity.value if device.electrode_polarity else None
        ),
        "water_flow_to_probes": device.water_flow_to_probes,
        "filtration_running": device.filtration_running,
        "filtration_relay": device.filtration_relay,
        "heating_allowed": device.heating_allowed,
        "heating_condition_met": device.heating_condition_met,
        "heating_control_enabled": device.heating_control_enabled,
        "chlorine_pump_running": device.chlorine_pump_running,
        "ph_minus_pump_running": device.ph_minus_pump_running,
        "ph_plus_pump_running": device.ph_plus_pump_running,
        "algaecide_pump_running": device.algaecide_pump_running,
        "flocculant_pump_running": device.flocculant_pump_running,
        "chlorine_flow_rate_ml_min": device.chlorine_flow_rate,
        "ph_minus_flow_rate_ml_min": device.ph_minus_flow_rate,
        "ph_plus_flow_rate_ml_min": device.ph_plus_flow_rate,
        "algaecide_flow_rate_ml_min": device.algaecide_flow_rate,
        "flocculant_flow_rate_ml_min": device.flocculant_flow_rate,
        # Backwash: the live relay bit plus the observed history the
        # BackwashTracker has built from it.  Without these a dump only
        # carries the schedule config (bytes 68-71) and the raw byte[29],
        # so answering "did a backwash run?" meant decoding bit 0x01 by
        # hand across a series of dumps.  None = not yet observed.
        "backwash_running": device.backwash_running,
        "last_backwash": _str_or_none(device.last_backwash),
        "last_scheduled_backwash": _str_or_none(device.last_scheduled_backwash),
        "last_manual_backwash": _str_or_none(device.last_manual_backwash),
        "last_backwash_trigger": (
            device.last_backwash_trigger.value if device.last_backwash_trigger else None
        ),
        "next_scheduled_backwash": _str_or_none(device.next_scheduled_backwash),
    }


def _raw_frames(
    coordinator: AsekoLocalDataUpdateCoordinator, serial: int
) -> dict[str, Any]:
    """Return the last frames seen from one serial number, annotated for a GitHub issue."""
    # --- Raw frame (v7 binary) ---
    raw_info: dict[str, Any] = {"available": False}
    raw = coordinator.get_raw_frame(serial)
    if raw is not None:
        raw_info = {
            "available": True,
            "hex_dump": raw.hex(),
            "length_bytes": len(raw),
            "byte_29_pump_state_hex": _byte(raw, PUMP_STATE_BYTE, "0x{:02x}"),
            "byte_29_pump_state_bin": _byte(raw, PUMP_STATE_BYTE, "0b{:08b}"),
            "byte_37_algicide_cfg_hex": _byte(raw, ALGICIDE_CONFIG_BYTE, "0x{:02x}"),
            "annotated_table": _annotated_frame(raw),
        }

    # --- Raw frame (v8 text) ---
    v8_raw_info: dict[str, Any] = {"available": False}
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

    get_warnings = getattr(coordinator, "get_frame_warnings", None)
    return {
        "raw_frame_v7": raw_info,
        "raw_frame_v8": v8_raw_info,
        "partial_frame": partial_info,
        "implausible_frames": get_warnings(serial) if get_warnings else {},
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: AsekoLocalConfigEntry,
    *,
    frame_log_export: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    ``frame_log_export``: the frame log already exported from a snapshot
    (the export download reads it once for its frames and this).
    """

    coordinator = config_entry.runtime_data.coordinator
    devices = coordinator.get_devices()

    devices_info: list[dict[str, Any]] = []

    for device in devices:
        serial = device.serial_number

        device_state = _device_state(device)

        # --- Consumption counters ---
        tracker = coordinator.get_tracker(serial) if serial is not None else None
        consumption: dict[str, Any] = {}
        if tracker is not None:
            for key in PUMP_KEYS:
                consumption[key] = {
                    "canister_ml": round(tracker.get(key, "canister"), 1),
                    "total_ml": round(tracker.get(key, "total"), 1),
                }

        frames = _raw_frames(coordinator, serial) if serial is not None else {}

        devices_info.append(
            {"device": device_state, "consumption": consumption, **frames}
        )

    # Units whose type nobody has mapped get no entities, but they are the
    # whole reason the annotated frame exists: with it, and the values the
    # generic readings make of it, a new model can be added.
    unrecognised_info: list[dict[str, Any]] = []
    for device in coordinator.get_unrecognised_devices():
        serial = device.serial_number
        unrecognised_info.append(
            {
                "note": (
                    "The unit type (v7 byte[4]) or header type (v8) is not mapped "
                    "to a model; no entities were created.  The decoded values below "
                    "come from the generic readings and are unverified.  Please share "
                    "this download in a GitHub issue to help add support for this "
                    "device."
                ),
                "device": _device_state(device),
                **(_raw_frames(coordinator, serial) if serial is not None else {}),
            }
        )

    return {
        "config_entry": async_redact_data(
            {**config_entry.data, **config_entry.options},
            _REDACT,
        ),
        "devices": devices_info,
        "unrecognised_devices": unrecognised_info,
        # bytes the server could not align into a frame; they are in the
        # frame log as kind "rejected" with the reason
        "rejected_frames": getattr(coordinator, "get_rejected_frames", dict)(),
        # the test cases card turns it on; off, the log below is what it held
        "frame_log_enabled": coordinator.frame_log.enabled,
        "frame_log": (
            frame_log_export
            if frame_log_export is not None
            else await hass.async_add_executor_job(
                coordinator.frame_log.snapshot().export
            )
        ),
    }
