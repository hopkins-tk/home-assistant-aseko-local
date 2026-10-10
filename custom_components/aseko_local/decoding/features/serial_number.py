"""The unit's serial number."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from ..feature import Feature

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


class SerialNumber(Feature):
    """v7: bytes 0-3, big-endian.  v8: second header token."""

    field = "serial_number"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> int:
        return frame.serial_number

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> int:
        return frame.serial_number
