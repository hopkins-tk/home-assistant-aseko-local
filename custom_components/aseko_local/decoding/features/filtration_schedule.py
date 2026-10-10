"""The filtration schedule the unit is configured for (Issue #133).

What the unit runs when nobody is at it, read from byte[37] bits 0x10
(period 1 enabled) and 0x20 (period 2 enabled):
0x00 = nonstop 24h, 0x10 = period 1, 0x30 = periods 1 and 2.  0x20 without
0x10 has never been seen -- period 2 is only offered on top of period 1 --
and leaves the schedule unset rather than guessed.

The same on every model.  Confirmed on an ASIN AQUA Salt in both directions of
every transition, and on HOME serial 110169464: 0x01 / 0x11 / 0x31.  The HOME
values once read as a separate "firmware A" encoding (0x43 nonstop, 0x53
timer, 0x47 / 0x57 "transitional") are the same bits with the Waterlevel
(0x40), Flow detection (0x02) and menu (0x04) flags set.

v8 has no such byte: the schedule follows from the hours themselves, reqs[5]
to reqs[7].  0 to 24 is the nonstop setting, anything else the timer.  A v8
unit offers one period only (Issue #131), so periods 1 and 2 never appear.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import UNSPECIFIED_VALUE
from ...models import AsekoFiltrationSchedule
from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


#: v8: the hours a unit running nonstop sends (reqs[5], reqs[7])
V8_NONSTOP = (0, 24)

PERIOD_BITS = 0x30
_BY_PERIOD_BITS = {
    0x00: AsekoFiltrationSchedule.NONSTOP_24H,
    0x10: AsekoFiltrationSchedule.TIMER_PERIOD_1,
    0x30: AsekoFiltrationSchedule.TIMER_PERIOD_1_AND_2,
}


class FiltrationSchedule(Feature):
    """v7: byte[37] bits 0x10 / 0x20.  v8: the hours in reqs[5] / reqs[7]."""

    field = "filtration_schedule"

    @override
    def decode_v7(
        self, frame: V7Frame, device: AsekoDevice
    ) -> AsekoFiltrationSchedule | None:
        """Bit flags: 0x10 period 1, 0x20 period 2."""
        b = frame[37]
        if b == UNSPECIFIED_VALUE:
            return None
        return _BY_PERIOD_BITS.get(b & PERIOD_BITS)

    @override
    def decode_v8(
        self, frame: V8Frame, device: AsekoDevice
    ) -> AsekoFiltrationSchedule | None:
        hours = (frame.value("reqs", 5), frame.value("reqs", 7))
        if None in hours:
            return None
        if hours == V8_NONSTOP:
            return AsekoFiltrationSchedule.NONSTOP_24H
        return AsekoFiltrationSchedule.TIMER_PERIOD_1
