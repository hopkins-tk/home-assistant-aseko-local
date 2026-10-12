"""v7: the 120-byte binary frame, firmware up to 7.x.

A ``V7Frame`` wraps the raw bytes; features read individual values off it
and never touch the transport again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...const import MESSAGE_SIZE, SERIAL_NUMBER_LENGTH
from .protocol import Protocol
from .values import UNSPECIFIED_WORD

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class V7Frame:
    """Read-only view over a 120-byte binary frame.

    ``frame[i]`` and ``frame[a:b]`` index the raw bytes; ``frame.word(i)``
    reads the big-endian 16-bit value at ``i``.
    """

    raw: bytes
    protocol: Protocol = field(default=Protocol.V7, init=False)

    def __getitem__(self, index: int | slice) -> int | bytes:
        """Return the byte at ``index``, or the bytes of a slice."""
        return self.raw[index]

    def word(self, index: int) -> int:
        """Return the unsigned big-endian 16-bit value at ``index``."""
        return int.from_bytes(self.raw[index : index + 2], "big")

    def word_or_none(self, index: int) -> int | None:
        """Like ``word`` but None for the 0xFFFF "unspecified" marker."""
        value = self.word(index)
        return None if value == UNSPECIFIED_WORD else value

    @property
    def serial_number(self) -> int:
        """Serial number, bytes 0-3."""
        return int.from_bytes(self.raw[0:4], "big")

    @property
    def unit_type(self) -> int:
        """The device-type / probe-configuration byte, byte[4]."""
        return self.raw[4]


V7_SEGMENT_LENGTH = 40
V7_CHECKSUM_SEED = 0xAA

# Serials whose bad checksum was already logged as a warning; later ones go to
# debug so a unit that keeps sending them does not flood the log.
_checksum_warned: set[int] = set()


def v7_bad_checksum_segments(raw: bytes) -> list[int]:
    """Return the indexes (0-2) of the 40-byte segments whose checksum fails.

    The last byte of every segment (39, 79, 119) is 0xAA XOR the 39 bytes
    before it -- the rule of the manufacturer's RS485 protocol document,
    which matches every segment of the captured v7 frames.  A trailing
    partial segment is not checked.
    """
    bad = []
    for index in range(len(raw) // V7_SEGMENT_LENGTH):
        start = index * V7_SEGMENT_LENGTH
        checksum = V7_CHECKSUM_SEED
        for value in raw[start : start + V7_SEGMENT_LENGTH - 1]:
            checksum ^= value
        if checksum != raw[start + V7_SEGMENT_LENGTH - 1]:
            bad.append(index)
    return bad


def parse_v7(raw: bytes) -> V7Frame:
    """Wrap a binary frame.  Alignment is the server's job, not this one's.

    A failed segment checksum is only logged: the frame is decoded as before.
    Raises ValueError for anything but a whole frame -- the server keeps
    fragments as partial frames and never decodes them.
    """
    if len(raw) != MESSAGE_SIZE:
        msg = f"v7 frame is {len(raw)} bytes, not {MESSAGE_SIZE}"
        raise ValueError(msg)
    frame = V7Frame(bytes(raw))
    bad = v7_bad_checksum_segments(frame.raw)
    if bad:
        serial = frame.serial_number if len(frame.raw) >= SERIAL_NUMBER_LENGTH else 0
        log = _LOGGER.debug if serial in _checksum_warned else _LOGGER.warning
        _checksum_warned.add(serial)
        log(
            "v7 frame from serial %s failed the checksum of segment(s) %s; "
            "decoding it anyway. Frame: %s",
            serial,
            bad,
            frame.raw.hex(),
        )
    return frame
