"""How far a unit's clock is off Home Assistant's, and whether that is too far.

Every frame that carries the unit's own clock (``unit_clock``) is compared
with the moment Home Assistant received it:

    offset = unit clock - Home Assistant clock at reception

so a negative offset is a unit that runs late.  A v7 unit sends seconds; a v8
unit sends hour and minute only, so its reading is taken as the middle of
that minute and the offset is folded into +/-12 h (there is no date to tell
a day apart).

The published offset is the median of the last ``SAMPLES`` readings, so one
late or odd frame does not move it.  ``out_of_sync`` needs every one of the
last ``SAMPLES`` readings on the same side:

* on  -- all at least ``alert_minutes`` off;
* off -- all less than ``alert_minutes`` minus the hysteresis: a fifth of the
  limit, at most 3 minutes (12 min for the default 15, 48 s for 1 min, 177 min
  for 180), so it can always clear;
* in between it keeps what it was.  Before it has been on, anything that is
  not three readings past the limit is off: turning on always takes three.
  With fewer readings than that it is None.

Nothing is compared while no frames arrive, so an offline unit keeps its last
offset instead of drifting further away from a clock that moves on.  Nothing
is stored either: after a restart three frames, half a minute, give the
answer again.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, time
from statistics import median

from homeassistant.util import dt as dt_util

DEFAULT_ALERT_MINUTES = 15
SAMPLES = 3
_HALF_DAY = 12 * 3600
_DAY = 24 * 3600


def offset_seconds(unit_clock: datetime | time, received: datetime) -> float:
    """Seconds the unit's clock is ahead of ``received`` (negative: behind).

    The unit sends its clock as wall-clock numbers with no zone, so the
    difference is taken between those numbers and Home Assistant's local wall
    clock at ``received`` -- not between two instants.  ``received`` may be
    in any zone (the server stamps UTC); only its local reading counts.  On
    the night of a change of time an instant comparison would be an hour
    off: the second 02:30 in autumn on both clocks is no offset at all.
    """
    local = dt_util.as_local(received)
    if isinstance(unit_clock, datetime):
        return (
            unit_clock.replace(tzinfo=None) - local.replace(tzinfo=None)
        ).total_seconds()
    unit = unit_clock.hour * 3600 + unit_clock.minute * 60 + 30  # middle of the minute
    ha = local.hour * 3600 + local.minute * 60 + local.second + local.microsecond / 1e6
    return (unit - ha + _HALF_DAY) % _DAY - _HALF_DAY


class ClockTracker:
    """Offset of one unit's clock and whether it is past the alert limit."""

    def __init__(self, alert_minutes: float = DEFAULT_ALERT_MINUTES) -> None:
        """Set up the tracker of one unit with the alert limit in minutes."""
        self.alert_minutes = float(alert_minutes)
        self._samples: deque[float] = deque(maxlen=SAMPLES)
        self.offset_minutes: float | None = None
        self.out_of_sync: bool | None = None

    @property
    def _clear_below_seconds(self) -> float:
        limit = self.alert_minutes * 60
        return limit - min(180.0, limit / 5)

    def update(self, unit_clock: datetime | time | None, received: datetime) -> None:
        """Take one frame's clock reading; None (not sent, not valid) is skipped."""
        if unit_clock is None:
            return
        self._samples.append(offset_seconds(unit_clock, received))
        self.offset_minutes = round(median(self._samples) / 60, 1)
        if len(self._samples) < SAMPLES:
            return
        limit = self.alert_minutes * 60
        if all(abs(s) >= limit for s in self._samples):
            self.out_of_sync = True
        elif (
            all(abs(s) < self._clear_below_seconds for s in self._samples)
            or self.out_of_sync is None
        ):
            # the first answer is off unless three readings say otherwise
            self.out_of_sync = False
