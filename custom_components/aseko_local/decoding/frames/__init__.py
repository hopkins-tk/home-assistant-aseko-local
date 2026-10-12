"""Frame parsers: raw bytes to a protocol-specific view.

This is the only place that knows how a frame is laid out as a whole:
``v7`` for the 120-byte binary frame, ``v8`` for the text frame, ``values``
for the helpers that read one value, ``protocol`` for telling them apart.
"""

from __future__ import annotations

from .protocol import V8_SIGNATURE, Protocol
from .v7 import (
    V7_CHECKSUM_SEED,
    V7_SEGMENT_LENGTH,
    V7Frame,
    parse_v7,
    v7_bad_checksum_segments,
)
from .v8 import (
    THIRD_PUMP_ALGICIDE,
    THIRD_PUMP_FLOCCULANT,
    V8Frame,
    parse_v8,
)
from .values import (
    UNSPECIFIED_WORD,
    byte_or_absent,
    byte_or_none,
    byte_when_flags,
    decode_time,
    decode_timestamp,
    flag_or_none,
    flag_when_known,
    time_or_absent,
    word_or_absent,
)


def parse_frame(raw: bytes, protocol: Protocol | None = None) -> V7Frame | V8Frame:
    """Parse ``raw`` as ``protocol``, or detect the protocol from the first bytes."""
    if protocol is Protocol.V8:
        return parse_v8(raw)
    if protocol is Protocol.V7:
        return parse_v7(raw)
    if bytes(raw).lstrip(b"\r\n\t\x00").startswith(V8_SIGNATURE):
        return parse_v8(raw)
    return parse_v7(raw)


__all__ = [
    "THIRD_PUMP_ALGICIDE",
    "THIRD_PUMP_FLOCCULANT",
    "UNSPECIFIED_WORD",
    "V7_CHECKSUM_SEED",
    "V7_SEGMENT_LENGTH",
    "V8_SIGNATURE",
    "Protocol",
    "V7Frame",
    "V8Frame",
    "byte_or_absent",
    "byte_or_none",
    "byte_when_flags",
    "decode_time",
    "decode_timestamp",
    "flag_or_none",
    "flag_when_known",
    "parse_frame",
    "parse_v7",
    "parse_v8",
    "time_or_absent",
    "v7_bad_checksum_segments",
    "word_or_absent",
]
