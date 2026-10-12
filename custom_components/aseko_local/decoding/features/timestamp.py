"""The unit's own clock at the moment the frame was sent."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, override

import homeassistant.util

from ..feature import Feature
from ..frames import decode_timestamp
from ..frames.values import unit_clock_v8

if TYPE_CHECKING:
    from ...models import AsekoDevice
    from ..frames import V7Frame, V8Frame


_LOGGER = logging.getLogger(__name__)


class Timestamp(Feature):
    """v7: bytes 6-11 (year offset 2000).  v8: hour and minute only."""

    field = "timestamp"

    @override
    def decode_v7(self, frame: V7Frame, device: AsekoDevice) -> datetime:
        return decode_timestamp(frame.raw)

    @override
    def decode_v8(self, frame: V8Frame, device: AsekoDevice) -> datetime:
        """Today's date from Home Assistant's clock, hour and minute from ins[16:18]."""
        now = datetime.now(tz=homeassistant.util.dt.get_default_time_zone())
        clock = unit_clock_v8(frame.get("ins", 16), frame.get("ins", 17))
        if clock is None:
            return now
        return now.replace(
            hour=clock.hour, minute=clock.minute, second=0, microsecond=0
        )
