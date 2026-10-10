"""The diagnostics download: frames of every kind and units with little to report."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.diagnostics import (
    _parse_v8_frame,
    _raw_frames,
    _reading_overrides,
    async_get_config_entry_diagnostics,
)
from custom_components.aseko_local.models import AsekoDevice

from .test_decode_v8 import REFERENCE_FRAME
from .test_entity_growth import SERIAL, _coordinator, _salt_frame
from .test_unrecognised_device import _diagnostics_hass

V8_SERIAL = 123456789


def test_a_v8_frame_with_an_odd_header_keeps_its_sections() -> None:
    parsed = _parse_v8_frame(b"{v1 serial ins: 1 2}")
    assert parsed["header"] == {}
    assert parsed["sections"]["ins"]["values"] == [1, 2]


def test_reading_overrides_of_an_unknown_profile_are_empty() -> None:
    assert _reading_overrides(None) == {}
    assert _reading_overrides("v7 NOT A MODEL") == {}
    assert _reading_overrides("v7 SALT")  # a real profile has some


def test_raw_frames_of_every_kind_are_annotated() -> None:
    coordinator = _coordinator()
    coordinator.store_v8_frame(REFERENCE_FRAME)
    coordinator.store_raw_frame(_salt_frame(0xD3)[:50])  # the unit hung up early

    v8 = _raw_frames(coordinator, V8_SERIAL)
    assert v8["raw_frame_v7"] == {"available": False}
    assert v8["raw_frame_v8"]["available"] is True
    assert v8["raw_frame_v8"]["header"]["serial_number"] == V8_SERIAL
    assert v8["partial_frame"] == {"available": False}

    partial = _raw_frames(coordinator, SERIAL)["partial_frame"]
    assert partial["available"] is True
    assert partial["length_bytes"] == 50
    assert "50 bytes instead of the expected 120" in partial["note"]
    assert len(partial["annotated_table"]) == 50
    assert partial["annotated_table"][-1]["word_dec"] is None


def test_a_v8_frame_that_cannot_be_parsed_is_kept_as_text() -> None:
    coordinator = _coordinator()
    coordinator.store_v8_frame(b"{v1 555 804 0 27 ins: 1\n")  # no closing brace

    v8 = _raw_frames(coordinator, 555)["raw_frame_v8"]

    assert v8 == {
        "available": True,
        "raw_text": "{v1 555 804 0 27 ins: 1",
        "length_bytes": 24,
        "parse_error": "Could not parse v8 frame structure",
    }


def test_a_coordinator_without_a_warning_register_reports_none() -> None:
    coordinator = MagicMock(spec=["get_raw_frame", "get_v8_frame", "get_partial_frame"])
    coordinator.get_raw_frame.return_value = None
    coordinator.get_v8_frame.return_value = None
    coordinator.get_partial_frame.return_value = None

    assert _raw_frames(coordinator, SERIAL)["implausible_frames"] == {}


@pytest.mark.asyncio
async def test_units_without_counters_or_serial_and_a_ready_export() -> None:
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    coordinator._trackers.clear()  # no consumption counted for this unit
    coordinator.data.set(0, AsekoDevice())  # nothing known about it at all
    coordinator._unrecognised_devices[0] = AsekoDevice()

    entry = MagicMock()
    entry.data = {"host": "192.168.1.2", "port": 47524}
    entry.options = {"forwarder_enabled": False}
    entry.runtime_data.coordinator = coordinator
    export = {"records": ["already exported"]}

    dump = await async_get_config_entry_diagnostics(
        _diagnostics_hass(), entry, frame_log_export=export
    )

    assert dump["config_entry"]["host"] == "**REDACTED**"
    assert dump["frame_log"] is export
    salt, unknown = dump["devices"]
    assert salt["consumption"] == {}
    assert salt["device"]["profile"] == "v7 SALT"
    assert unknown == {
        "device": unknown["device"],
        "consumption": {},
    }  # no serial number: no frames to look up
    assert unknown["device"]["device_type"] is None
    assert unknown["device"]["serial_number"] is None
    (unrecognised,) = dump["unrecognised_devices"]
    assert set(unrecognised) == {"note", "device"}
