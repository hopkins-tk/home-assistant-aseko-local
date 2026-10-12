"""Measured free chlorine (mg/l)."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ...models import AsekoProbeType
from ..feature import Feature
from ..presence import NOT_PRESENT
from .configuration import Configuration

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame
    from ..presence import NotPresent


class FreeChlorine(Feature):
    """v7: bytes 16-17 / 100, when a CLF probe is installed."""

    field = "free_chlorine"
    depends_on = (Configuration,)

    @override
    def decode_v7(
        self, frame: V7Frame, device: AsekoDevice
    ) -> float | NotPresent | None:
        if AsekoProbeType.CLF not in device.configuration:
            return NOT_PRESENT
        raw = frame.word_or_none(16)  # 0xFFFF: installed but unreadable
        return None if raw is None else raw / 100
