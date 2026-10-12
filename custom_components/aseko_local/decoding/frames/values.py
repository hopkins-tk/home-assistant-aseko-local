"""Reading single values out of a frame: unset markers, times, the clock.

Shared by both protocols' features.  0xFF (a byte) and 0xFFFF (a word) are
the markers of a value the unit did not fill in.
"""

from __future__ import annotations

import logging
from datetime import datetime, time

import homeassistant.util

from ...const import UNSPECIFIED_VALUE, YEAR_OFFSET
from ..presence import NOT_PRESENT, NotPresent

_LOGGER = logging.getLogger(__name__)

# Two 0xFF bytes: a 16-bit value the unit did not fill in.
UNSPECIFIED_WORD = 0xFFFF

# v7 bytes 6-11: year (from 2000), month, day, hour, minute, second
CLOCK_BYTES = slice(6, 12)


def word_or_absent(value: int | None) -> int | NotPresent:
    """NOT_PRESENT for a 16-bit setting read as None by ``word_or_none``."""
    return NOT_PRESENT if value is None else value


def byte_or_absent(value: int) -> int | NotPresent:
    """Return ``value``, or NOT_PRESENT for the 0xFF "unspecified" marker.

    For a configuration byte 0xFF means the setting was never made or the
    input is not fitted, which is a fact about this unit rather than a value
    that happens to be unknown -- see ``presence``.
    """
    return NOT_PRESENT if value == UNSPECIFIED_VALUE else value


def byte_or_none(value: int) -> int | None:
    """Return ``value``, or None for the 0xFF "not filled in" marker.

    For a measurement or a setpoint the unit has: 0xFF says this frame does
    not carry the value, not that the unit lacks it -- see ``byte_or_absent``.
    """
    return None if value == UNSPECIFIED_VALUE else value


def flag_or_none(flags: int, mask: int) -> bool | None:
    """Return whether ``mask`` is set in ``flags``, or None when ``flags`` is 0xFF.

    For a settings byte 0xFF means this frame does not say, e.g. while the
    unit starts; a clear bit is a real False.
    """
    if flags == UNSPECIFIED_VALUE:
        return None
    return bool(flags & mask)


def flag_when_known(required: object, flags: int, mask: int) -> bool | NotPresent:
    """Return whether ``mask`` is set in ``flags``, or NOT_PRESENT while ``required`` is None.

    For a bit that means something only once another value is known -- a
    pump's running bit, say, which counts only while its flow rate is set.
    """
    if required is None:
        return NOT_PRESENT
    return bool(flags & mask)


def byte_when_flags(
    value: int, flags: int, mask: int, expected: int
) -> int | NotPresent:
    """``byte_or_absent(value)`` while ``flags & mask == expected``, else NOT_PRESENT.

    For a byte whose meaning depends on a setting in another byte -- a port
    shared by two uses, say, routed by a bit.  An unset settings byte (0xFF)
    says nothing about the routing, so it reads NOT_PRESENT as well.
    """
    if flags == UNSPECIFIED_VALUE or (flags & mask) != expected:
        return NOT_PRESENT
    return byte_or_absent(value)


def decode_time(data: bytes) -> time | None:
    """Decode an (hour, minute) byte pair; 0xFF in the hour means unset."""
    if data[0] == UNSPECIFIED_VALUE:
        return None

    hour = data[0]
    minute = data[1]

    try:
        return time(hour=hour, minute=minute)
    except ValueError as e:
        _LOGGER.warning("Invalid time in frame (%s) - data=%s", e, data.hex())
        return None


def time_or_absent(data: bytes) -> time | NotPresent:
    """Like ``decode_time`` but NOT_PRESENT for an unset or invalid pair."""
    value = decode_time(data)
    return NOT_PRESENT if value is None else value


def unit_clock_v7(data: bytes) -> datetime | None:
    """Return the unit's clock from bytes 6-11 as sent, or None when unset or not a date.

    Wall-clock time in Home Assistant's time zone: the unit sends no zone.
    """
    if len(data) < CLOCK_BYTES.stop or UNSPECIFIED_VALUE in data[CLOCK_BYTES]:
        return None
    try:
        return datetime(
            year=YEAR_OFFSET + data[6],
            month=data[7],
            day=data[8],
            hour=data[9],
            minute=data[10],
            second=data[11],
            tzinfo=homeassistant.util.dt.get_default_time_zone(),
        )
    except ValueError:
        return None


def unit_clock_v8(hour: int | None, minute: int | None) -> time | None:
    """Return a v8 unit's clock (hour and minute, no date), or None when not valid."""
    if hour is None or minute is None:
        return None
    try:
        return time(hour, minute)
    except (TypeError, ValueError):
        return None


def decode_timestamp(data: bytes) -> datetime:
    """Decode the device clock from bytes 6-11, falling back to now()."""
    clock = unit_clock_v7(data)
    if clock is not None:
        return clock
    if len(data) >= CLOCK_BYTES.stop and UNSPECIFIED_VALUE not in data[CLOCK_BYTES]:
        # filled in, but not a date: worth a look, unlike the routine unset
        # bytes of a unit that sends no clock (v7 NET)
        _LOGGER.warning(
            "Received invalid timestamp %s - falling back to now()", data[6:12].hex()
        )
    return datetime.now(tz=homeassistant.util.dt.get_default_time_zone())
