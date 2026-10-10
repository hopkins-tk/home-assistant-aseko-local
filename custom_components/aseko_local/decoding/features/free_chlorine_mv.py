"""Raw free-chlorine probe voltage (mV)."""

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


class FreeChlorineMv(Feature):
    """v7: bytes 20-21, when a CLF probe is installed."""

    field = "free_chlorine_mv"
    depends_on = (Configuration,)

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent | None:
        if AsekoProbeType.CLF not in device.configuration:
            return NOT_PRESENT
        return frame.word_or_none(20)  # 0xFFFF: installed but unreadable
