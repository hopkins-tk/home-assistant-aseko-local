"""Diagnostics support for Aseko Local."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import AsekoLocalConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AsekoLocalConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    devices = coordinator.get_devices() or []

    devices_info = []
    for device in devices:
        raw = coordinator.get_raw_frame(device.serial_number)
        raw_hex = raw.hex(" ") if raw else None

        annotated: list[dict[str, Any]] = []
        if raw:
            for i, byte in enumerate(raw):
                annotated.append({"offset": i, "hex": f"{byte:02x}", "dec": byte})

        devices_info.append(
            {
                "serial_number": device.serial_number,
                "device_type": device.device_type.value if device.device_type else None,
                "configuration": [p.value for p in (device.configuration or [])],
                "raw_frame_hex": raw_hex,
                "raw_frame_annotated": annotated,
            }
        )

    return {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
        },
        "devices": devices_info,
    }
