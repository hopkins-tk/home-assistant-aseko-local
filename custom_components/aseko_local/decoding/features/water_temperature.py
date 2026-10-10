"""Measured water temperature (degrees C)."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame
    from ..presence import NotPresent


class WaterTemperature(Feature):
    """v7: bytes 25-26 / 10.  v8: ins[0] / 10."""

    field = "water_temperature"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> float | None:
        raw = frame.word_or_none(25)  # 0xFFFF: probe unreadable
        return None if raw is None else raw / 10

    @override
    def decode_v8(
        self, frame: V8Frame, device: AsekoDevice
    ) -> float | NotPresent | None:
        return frame.measurement("ins", 0, divisor=10)  # -500: no probe
