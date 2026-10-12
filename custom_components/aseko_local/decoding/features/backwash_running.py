"""Whether the backwash valve relay is currently energised.

v7: byte[29] bit 0x01 (JS-DE-Tech "relay_byte" bit 0).  Live confirmation on
SALT, 2026-08-11: a diagnostics capture spanning a manually started backwash
shows byte[29] going 0x48 -> 0x49 -> 0x48, with the bit set from 13:26:43 to
13:28:09 and clear again at 13:28:29.  The 86-106 s relay window matches the
unit's configured backwash_duration of 100 s (byte[71] = 0x0a), and no other
actuator bit moved during it.  A "no flow to probes" condition (byte[13] bit
0x04) was independently confirmed to go with byte[28] == 0, not with this
bit (Issue #100, DomSchCoding capture).

NET has no backwash valve, so no NET profile lists this feature and no
entity is created for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


BACKWASH = 0x01


class BackwashRunning(Feature):
    """v7: byte[29] bit 0x01."""

    field = "backwash_running"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool:
        return bool(frame[29] & BACKWASH)
