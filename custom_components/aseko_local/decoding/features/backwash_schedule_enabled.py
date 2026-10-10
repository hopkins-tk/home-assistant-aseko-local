"""Whether the automatic filter backwash is enabled.

v7: byte[22] bit 0x10.  Confirmed on an ASIN AQUA Salt: switching the
backwash schedule off cleared the bit together with byte[68] (interval)
dropping to 0 (2026-09-13 marked test case).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import flag_or_none

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame


MASK = 0x10


class BackwashScheduleEnabled(Feature):
    """v7: byte[22] bit 0x10."""

    field = "backwash_schedule_enabled"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> bool | None:
        return flag_or_none(frame[22], MASK)
