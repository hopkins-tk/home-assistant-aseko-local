"""Maximum filling-valve open time (seconds).

v7: bytes 76-77, big-endian, in seconds exactly as the unit transmits it,
matching the neighbouring startup_delay (74-75) and dosing_delay
(106-107).  Verified on an ASIN AQUA Salt by changing the setting in the
Aseko Live app and re-reading the frame:

    0x0708 = 1800 -> app showed 30 min
    0x0B04 = 2820 -> app showed 47 min

Bytes 94-95 were the previous guess and are wrong: byte 95 is
ph_minus_flow_rate.  0xFFFF = the device does not implement the feature
(Issue #129: a bare int would otherwise read 65535 on NET / PROFI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import word_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class MaxRefillTime(Feature):
    """v7: bytes 76-77, 0xFFFF = not implemented."""

    field = "max_refill_time"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return word_or_absent(frame.word_or_none(76))
