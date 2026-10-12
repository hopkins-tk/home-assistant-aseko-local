"""Dosing delay after startup.  v7: bytes 74-75, seconds.  v8: areqs[17], minutes."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature
from ..frames import word_or_absent

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class StartupDelay(Feature):
    """v7: bytes 74-75.  v8: areqs[17]."""

    field = "startup_delay"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int | NotPresent:
        return word_or_absent(frame.word_or_none(74))

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int | None:
        return frame.get("areqs", 17)
