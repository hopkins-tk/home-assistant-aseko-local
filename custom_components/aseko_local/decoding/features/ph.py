"""Measured pH."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...models import AsekoProbeType
from ..feature import Feature
from ..presence import NOT_PRESENT
from .configuration import Configuration

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class Ph(Feature):
    """v7: bytes 14-15 / 100, when a pH probe is installed.  v8: ains[0] / 100."""

    field = "ph"
    depends_on = (Configuration,)

    @override
    def decode_v7(
        self, frame: V7Frame, device: AsekoDevice
    ) -> float | NotPresent | None:
        if AsekoProbeType.PH not in device.configuration:
            return NOT_PRESENT
        raw = frame.word_or_none(14)  # 0xFFFF: installed but unreadable
        return None if raw is None else raw / 100

    @override
    def decode_v8(
        self, frame: V8Frame, device: AsekoDevice
    ) -> float | NotPresent | None:
        return frame.measurement("ains", 0, divisor=100)  # -500: no pH probe
