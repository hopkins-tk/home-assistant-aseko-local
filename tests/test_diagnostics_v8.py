"""The diagnostics download reads a v8 frame the way the decoder does (audit K3)."""

from __future__ import annotations

from custom_components.aseko_local.decoding.frames.v8 import parse_v8
from custom_components.aseko_local.diagnostics import _parse_v8_frame

FRAME = (
    b"{v1 123456789 804 0 27 "
    b"ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0 "
    b"ains: 708 bad 774 "
    b"outs: 0 0 1 "
    b"areqs: 72 0 "
    b"crc16: 1234}"
)


def test_crc16_is_hexadecimal_in_both() -> None:
    runtime = parse_v8(FRAME)
    diagnostics = _parse_v8_frame(FRAME)

    assert runtime.sections["crc16"] == [0x1234]
    assert diagnostics["sections"]["crc16"]["values"] == [0x1234]


def test_one_unreadable_value_keeps_the_rest_of_the_section() -> None:
    runtime = parse_v8(FRAME)
    ains = _parse_v8_frame(FRAME)["sections"]["ains"]

    assert runtime.sections["ains"] == [708, None, 774]
    assert ains["values"] == [708, None, 774]
    assert ains["unreadable"] == [1]
    assert ains["raw"] == "708 bad 774"


def test_every_section_matches_the_decoder() -> None:
    runtime = parse_v8(FRAME)
    diagnostics = _parse_v8_frame(FRAME)

    assert {
        name: section["values"] for name, section in diagnostics["sections"].items()
    } == runtime.sections
    assert diagnostics["header"]["serial_number"] == 123456789
    assert diagnostics["raw_text"] == FRAME.decode()


def test_a_frame_without_braces_is_not_parsed() -> None:
    assert _parse_v8_frame(b"v1 123 804 0 27 ins: 1") is None
