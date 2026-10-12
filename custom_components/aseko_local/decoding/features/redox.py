"""Measured redox potential (mV)."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...const import UNSPECIFIED_VALUE
from ...models import AsekoProbeType
from ..feature import Feature
from ..presence import NOT_PRESENT
from .configuration import Configuration

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class Redox(Feature):
    """v7: bytes 18-19, or bytes 16-17 when 18-19 are 0xFFFF.  v8: ains[6]."""

    field = "redox"
    depends_on = (Configuration,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent | None:
        if AsekoProbeType.REDOX not in device.configuration:
            return NOT_PRESENT
        if frame[18] == UNSPECIFIED_VALUE and frame[19] == UNSPECIFIED_VALUE:
            return frame.word_or_none(16)  # 0xFFFF: installed but unreadable
        return frame.word_or_none(18)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int | NotPresent | None:
        if frame.unspecified("ains", 6):  # -500: no redox probe
            return NOT_PRESENT
        return frame.value("ains", 6)  # None: unreadable or not sent
