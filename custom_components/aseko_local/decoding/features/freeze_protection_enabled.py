"""Antifreeze master enable (Issue #136).

v7: byte[37] bit 0x80 on HOME.  Confirmed on serial 110175608 (ASIN AQUA
Home REDOX): 0x81 with antifreeze ON, 0x41 with it OFF.  When
enabled, byte[55] shows the antifreeze threshold (4 C) instead of the normal
heating setpoint.  On SALT the same bit is the algicide routing indicator
and Winter mode is byte[22] bit 0x04 (decode_v7_winter_mode).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


ANTIFREEZE = 0x80
WINTER_MODE = 0x04  # byte[22], SALT


class FreezeProtectionEnabled(Feature):
    """v7: byte[37] bit 0x80."""

    field = "freeze_protection_enabled"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[37], ANTIFREEZE)

    def decode_v7_winter_mode(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        """SALT: "Winter mode" is byte[22] bit 0x04.

        Confirmed on an ASIN AQUA Salt (2026-09-13 marked test cases, twice):
        the bit set with Winter mode ON, together with byte[78] bit 0x40, and
        the setpoint bytes switched to the winter program (water 2 C,
        algicide 2 ml, filtration 12:00-12:15, backwash off).
        """
        return flag_or_none(frame[22], WINTER_MODE)
