"""Configured pH-minus acid concentration (percent).

v7: byte[112], e.g. 5 -> 5 %, 10 -> 10 %.  Confirmed on serial 110175608
(ASIN AQUA Home REDOX, Issue #139).  0xFF = not reported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import byte_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class PhMinusConcentration(Feature):
    """v7: byte[112]."""

    field = "ph_minus_concentration"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return byte_or_absent(frame[112])
