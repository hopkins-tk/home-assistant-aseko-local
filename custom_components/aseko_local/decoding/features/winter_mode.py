"""Whether Winter mode is switched on.

v7: byte[22] bit 0x04.  On HOME this is its own setting, next to the
antifreeze one (byte[37] 0x80, ``freeze_protection_enabled``): the unit's
Configuration menu lists "Winter mode" and "Freeze protection" as separate
entries.  Confirmed on serial 110215864 with Winter mode ON and freeze
protection OFF on the display (2026-10-29): 0x90 before, 0x84 after, while
the setpoints switched to the winter program (water 2 C, algicide 2 ml,
filtration 12:00-12:15, backwash off).  SALT carries the same bit, read there
as ``freeze_protection_enabled`` (decode_v7_winter_mode).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


MASK = 0x04


class WinterMode(Feature):
    """v7: byte[22] bit 0x04."""

    field = "winter_mode"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[22], MASK)
