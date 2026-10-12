"""Persistent tracker for observed filter backwash cycles.

A "successful" backwash is defined as the backwash relay (byte[29] bit 0x01)
remaining continuously active for at least 60 seconds.  Short relay
activations (e.g. menu navigation, output-test mode) are ignored.

That much is observed fact.  Everything else here is derived from it.

Each recorded cycle is *classified* as scheduled or manual by comparing the
moment the relay opened against the unit's configured ``backwash_start_time``:

    * within ±``OFFSET_MATCH_TOLERANCE`` (5 min) of the configured time on
      the unit's clock -- the start moved by the clock offset in the frame
      that opened the valve, drift and a missed change of summer / winter
      time together -- on a unit whose schedule is enabled  →  SCHEDULED
      (the unit ran it itself);
      ±``SCHEDULED_MATCH_TOLERANCE`` (15 min) on Home Assistant's clock
      while no offset is known
    * anything else                                    →  MANUAL

— except on units that report their settings menu (below), where MANUAL
needs the menu to have been open outside the window, and a cycle that neither
the schedule nor the menu explains is UNKNOWN.

The device does not transmit *why* the valve opened, nor when it last ran, so
on most units the start time is the only signal available and the
classification is a guess that can be wrong — ``_classify`` lists the specific
ways.  Consumers should treat ``last_backwash`` as reliable and the
scheduled/manual split (and the ``next_scheduled_backwash`` projection built
on it) as an estimate.

Units whose profile carries ``AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY``
(SALT today) are the exception: byte[37] bit 0x04 marks their settings menu
being open, and that is the menu a backwash is started by hand from — so a
cycle that runs while the bit is set is manual as a matter of observation
rather than inference — outside the schedule window.  In the window a cycle
is always SCHEDULED; outside it with the menu closed it is UNKNOWN: nobody was
at the menu and the schedule does not explain it.  See ``_service_menu_open``.

Nothing is guessed before the first observation, though: every recorded value
starts out as ``None``: until a cycle has actually been seen, the honest answer
is "unknown" rather than a timestamp derived from the schedule.  The one
projection made without an observed cycle is the day after a schedule change
(below), because the unit itself fixes that day.

The last scheduled cycle is what drives the "next backwash" projection — a
manual backwash does not reveal (nor, on the unit, reset) the schedule phase.
A change of the schedule does reset it: once the unit shows a new backwash
time or interval, or the schedule switched back on, its next cycle runs the
day after the change at the new time and the interval counts from there
(confirmed on an ASIN Aqua Salt).  The tracker keeps that day as an anchor
until a scheduled cycle on it, or later, has been seen.

Times, three kinds:

* ``last_backwash`` and ``last_manual_backwash`` are when Home Assistant saw
  the cycle (the midpoint of the relay window, from the frames' receive
  times);
* ``last_scheduled_backwash`` and ``next_scheduled_backwash`` are on the
  unit's clock: the ``backwash_start_time`` slot the recognised cycle ran
  in, e.g. 08:30, and the next such slot;
* durations and gaps are measured between receive times normalised to UTC,
  so a change of summer / winter time in Home Assistant does not stretch or
  shrink them.

The schedule is set on the unit's own clock, which runs apart from Home
Assistant's (``trackers.clock``).  Once the offset is measured, classification
compares the cycle's start with the schedule on the unit's clock, within the
tighter ``OFFSET_MATCH_TOLERANCE``.  The offset is the whole difference, drift
and a change of time (summer / winter) the unit did not follow alike.  The
projection is not moved by it: it shows the backwash time exactly as it is
set on the unit, and ``clock_offset`` tells how far that is from Home
Assistant's clock.

The recorded timestamps are stored persistently via the Home Assistant
``Store`` API and survive:
    * Home Assistant restarts
    * Integration reloads
    * Integration updates
    * Network interruptions (a gap of up to ``MAX_FRAME_GAP`` keeps a cycle open)

Modelled after JS-DE-Tech's hacs-aseko-asin-aqua-home-clf integration:
    * https://github.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf

Public API:
    * ``BackwashTracker(hass, serial_number)`` — one instance per device
    * ``await tracker.async_load()`` — call once at startup
    * ``tracker.update(device, now)`` — call after every received frame
    * ``await tracker.async_save()`` — fire-and-forget after a recordable event
    * ``tracker.last_backwash`` / ``last_scheduled_backwash`` /
      ``last_manual_backwash`` / ``last_trigger`` — read-only properties
    * ``tracker.next_scheduled_backwash(device, now)`` — projected next
      automatic cycle
"""

from __future__ import annotations

import logging
from collections.abc import Coroutine
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..models import (
    AsekoBackwashSource,
    AsekoBackwashTrigger,
    AsekoProfileFlag,
)
from .clock import offset_seconds

if TYPE_CHECKING:
    from ..models import AsekoDevice

_LOGGER = logging.getLogger(__name__)


def _service_menu_open(device: AsekoDevice) -> bool:
    """Return True if somebody has the unit's settings menu open.

    On v7, byte[37] bit 0x04 marks that menu — the one filtration and
    backwash can be started by hand from.  It appears on entering, before
    anything is touched, so on its own it says only that a person is at the
    unit.  Paired with a running backwash it says more: a capture of a
    by-hand cycle has the bit set on every frame from ~30 s before the valve
    opened until ~20 s after it closed.  Somebody was standing at the menu
    the button lives on — observed, not inferred from the clock.

    Honoured only where the device's profile says the bit means presence and
    nothing more (``AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY``, SALT
    today).  On HOME (Issue #133) the same bit is a standing
    manual override that forces the pump off and can stay set indefinitely;
    honouring it there would misclassify every scheduled cycle that ran
    while the override was on, so that profile does not carry the flag.
    The tracker itself knows no models.

    The bit is only ever *additional* evidence.  It is never used to call a
    cycle scheduled: nobody being at the unit is no proof that the unit
    started the cycle itself.
    """
    return (
        AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY in device.flags
        and device.service_menu_open is True
    )


# Minimum continuous relay-on duration to count as a real backwash cycle.
# The device has reported backwash durations of 1:40 to 2:00 minutes; 60 s
# comfortably separates a real cycle from a brief relay blip in menu mode.
MIN_BACKWASH_DURATION = timedelta(seconds=60)

# Maximum gap between two consecutive frames to consider the backwash as
# "still running" (vs. lost connection).  If the gap exceeds this, the
# tracker resets its start time to avoid recording a stale window.
# Aseko typically transmits every 30 s when idle, so 5 minutes (300 s) is
# a comfortable upper bound that covers transient disconnects without
# being so long that a genuine connection loss is mistaken for a cycle.
MAX_FRAME_GAP = timedelta(minutes=5)

# How far the observed relay-on start may drift from the configured
# ``backwash_start_time`` and still count as the unit's own scheduled cycle.
# The unit fires on its own clock, which can be a few minutes off from HA's,
# and the frame that first reports the relay as on can lag the actual start
# by one transmit interval (~30 s).  15 minutes absorbs both while staying
# far below any plausible "user pressed the button around that time" overlap.
SCHEDULED_MATCH_TOLERANCE = timedelta(minutes=15)

# The same window once the unit's clock offset is known and taken out of the
# comparison: what is left is the lag of the first frame that reports the
# valve open and the unit's own start-up (the flag rises ~30 s early).
OFFSET_MATCH_TOLERANCE = timedelta(minutes=5)

# Home Assistant Store schema versioning — bump if the persisted shape changes.
# Version 1 held only ``last_backwash``; the classification keys added later are
# optional on load, so old stores keep working and simply report the trigger of
# the pre-upgrade cycle as unknown.
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "aseko_local_backwash_"


class _CurrentOffset:
    """Default of the ``offset_minutes`` arguments: the offset as it is now."""

    def __repr__(self) -> str:
        """Name the sentinel in a traceback."""
        return "CURRENT_OFFSET"


#: Told apart from an explicit ``None``, which says the offset was *not known*
#: when the valve opened -- the cycle is then compared on Home Assistant's
#: clock with the wider tolerance, and a value measured later does not
#: reinterpret the start.
CURRENT_OFFSET = _CurrentOffset()

_OffsetArg = float | None | _CurrentOffset


class BackwashTracker:
    """Detects, classifies and persistently records filter backwash events.

    One instance per device (keyed by ``serial_number``).  Holds the relay
    state machine between frames and is responsible for saving the
    confirmed backwash timestamps to disk so they survive restarts.
    """

    def __init__(self, hass: HomeAssistant, serial_number: int) -> None:
        """Set up the tracker of one unit; ``async_load`` restores its history."""
        self._hass = hass
        self._serial = serial_number
        self._store: Store[dict] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}{serial_number}",
        )

        # State machine: when did the current "relay on" window start?
        # None = relay is currently off, or we have not seen it on yet.
        self._relay_on_since: datetime | None = None

        # Was the settings menu open during the current window?  Latched
        # across the whole window rather than read at the end: the unit
        # drops the flag a frame or two after the valve closes, so by the
        # time the window is recorded it has usually gone again.
        self._service_menu_in_window = False

        # The clock offset when the current window opened, read from the
        # frame that opened it (``_offset_when_opened``): the cycle is
        # recognised against it, so a later change of the offset (Home
        # Assistant switching to summer / winter time mid-cycle, the unit's
        # clock set by hand) does not change what the start was on the
        # unit's clock.
        self._window_offset_minutes: float | None = None

        # Last frame timestamp we processed — used to detect dropped connections.
        self._last_frame_at: datetime | None = None

        # Recorded timestamps (loaded from / saved to storage).
        self._last_backwash: datetime | None = None
        self._last_scheduled_backwash: datetime | None = None
        self._last_manual_backwash: datetime | None = None
        self._last_trigger: AsekoBackwashTrigger | None = None

        # Where _last_scheduled_backwash came from: OBSERVED (we watched the
        # valve run) or MANUAL (the user seeded it).  Drives the "source"
        # attribute on both the last- and next-scheduled sensors.
        self._last_scheduled_source: AsekoBackwashSource | None = None

        # The unit-clock day of the schedule slot the last scheduled cycle
        # belongs to, fixed when it is recorded, so a later change of the
        # backwash time does not move it to a neighbouring day.
        self._last_scheduled_day: date | None = None

        # The schedule (time, interval) last seen in a frame, and the day a
        # change of it restarts the schedule on (see the module docstring).
        self._schedule_seen: tuple[time, int] | None = None
        self._restart_day: date | None = None

        # Minutes the unit's clock is ahead of Home Assistant's (clock
        # tracker), kept so a restart does not lose it before frames arrive.
        self._clock_offset_minutes: float | None = None

        # True from ``load_soon`` until the stored state is in.  Until then
        # nothing is saved and frames are not taken: Home Assistant's Store
        # hands a pending write back to a load, so a save made before the
        # load finished would replace the stored history with an empty one.
        self._loading = False

    @property
    def serial_number(self) -> int:
        """Return the device serial number this tracker belongs to."""
        return self._serial

    @property
    def last_backwash(self) -> datetime | None:
        """Return the most recent observed backwash of any kind, or None."""
        return self._last_backwash

    @property
    def last_scheduled_backwash(self) -> datetime | None:
        """Return the most recent backwash that ran on the unit's schedule."""
        return self._last_scheduled_backwash

    @property
    def loading(self) -> bool:
        """Whether the stored history is still on its way in from the Store.

        A typed-in date written now would be replaced by the stored one when
        the load finishes, and it could not be saved either (``async_save``),
        so the services refuse while this is True instead of losing it.
        """
        return self._loading

    @property
    def last_scheduled_source(self) -> AsekoBackwashSource | None:
        """Return where ``last_scheduled_backwash`` came from, or None if unset."""
        return self._last_scheduled_source

    def set_last_scheduled_backwash(self, moment: datetime) -> None:
        """Record a user-supplied timestamp for the last scheduled backwash.

        Lets the schedule projection start working immediately instead of
        waiting out a whole interval for the next real cycle.  The value is
        marked MANUAL and persisted, and ``next_scheduled_backwash`` is
        projected from it.

        Last write wins, and the stored timestamps are never compared: an entry
        always applies, even when it moves the record backwards, because
        somebody typing a date in is correcting it on purpose.  Symmetrically,
        a scheduled cycle detected *after* this entry replaces it (see
        ``_record_window``) — by then the guess has been overtaken by the real
        thing.

        ``last_backwash`` is deliberately left alone: it means "we watched this
        happen", and a typed-in date has not been watched.
        """
        self._last_scheduled_backwash = moment
        self._last_scheduled_source = AsekoBackwashSource.MANUAL
        # a typed-in date is the user's correction: it replaces both the day
        # derived from the last cycle and a pending restart of the schedule
        self._last_scheduled_day = None
        self._restart_day = None
        _LOGGER.info(
            "Last scheduled backwash for serial=%s set manually to %s",
            self._serial,
            moment.isoformat(),
        )
        self._hass.async_create_task(self.async_save())

    @property
    def last_manual_backwash(self) -> datetime | None:
        """Return the most recent backwash that was started by hand."""
        return self._last_manual_backwash

    @property
    def last_trigger(self) -> AsekoBackwashTrigger | None:
        """Return how the most recent observed backwash was started."""
        return self._last_trigger

    def load_soon(self) -> Coroutine[Any, Any, None]:
        """Mark the tracker loading at once and return ``async_load()`` to run.

        For a caller that schedules the load as a task: the flag is set
        before the next frame can reach ``update``.
        """
        self._loading = True
        return self.async_load()

    async def async_load(self) -> None:
        """Load the persistent state from storage.  Call once at startup."""
        self._loading = True
        try:
            data = await self._store.async_load()
        finally:
            self._loading = False
        if not data:
            return

        self._last_backwash = self._parse_stored_datetime(data, "last_backwash")
        self._last_scheduled_backwash = self._parse_stored_datetime(
            data, "last_scheduled_backwash"
        )
        self._last_manual_backwash = self._parse_stored_datetime(
            data, "last_manual_backwash"
        )

        trigger = data.get("last_trigger")
        if trigger is not None:
            try:
                self._last_trigger = AsekoBackwashTrigger(trigger)
            except ValueError:
                _LOGGER.warning(
                    "Could not parse stored last_trigger for serial=%s: %r",
                    self._serial,
                    trigger,
                )

        source = data.get("last_scheduled_source")
        if source is not None:
            try:
                self._last_scheduled_source = AsekoBackwashSource(source)
            except ValueError:
                _LOGGER.warning(
                    "Could not parse stored last_scheduled_source for serial=%s: %r",
                    self._serial,
                    source,
                )
        elif self._last_scheduled_backwash is not None:
            # Written before provenance was tracked.  Anything already in the
            # store got there by observation — manual entry did not exist yet.
            self._last_scheduled_source = AsekoBackwashSource.OBSERVED

        self._last_scheduled_day = _parse_date(data.get("last_scheduled_day"))
        self._restart_day = _parse_date(data.get("restart_day"))
        schedule = data.get("schedule")
        try:
            if schedule is not None:
                self._schedule_seen = (
                    time.fromisoformat(schedule["time"]),
                    int(schedule["interval"]),
                )
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning(
                "Could not parse stored schedule for serial=%s: %r",
                self._serial,
                schedule,
            )
        offset = data.get("clock_offset_minutes")
        if isinstance(offset, int | float):
            self._clock_offset_minutes = float(offset)

    def _parse_stored_datetime(self, data: dict, key: str) -> datetime | None:
        """Return a stored ISO timestamp as a datetime, or None if absent/invalid."""
        raw = data.get(key)
        if raw is None:
            return None
        try:
            return datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Could not parse stored %s for serial=%s: %r", key, self._serial, raw
            )
            return None

    async def async_save(self) -> None:
        """Persist the current state to storage.

        Writes unconditionally, nulls included.  An earlier version skipped the
        write while nothing was recorded, which silently broke
        ``clear_last_scheduled_backwash``: clearing the only stored value left
        the old one on disk, and it came back on the next restart.  Every
        caller reaches this after a change, so there is nothing to save on.

        Skipped while the stored state is still loading (see ``_loading``).
        """
        if self._loading:
            _LOGGER.debug(
                "Backwash state for serial=%s not saved: still loading", self._serial
            )
            return
        await self._store.async_save(
            {
                "last_backwash": (
                    self._last_backwash.isoformat()
                    if self._last_backwash is not None
                    else None
                ),
                "last_scheduled_backwash": (
                    self._last_scheduled_backwash.isoformat()
                    if self._last_scheduled_backwash is not None
                    else None
                ),
                "last_scheduled_source": (
                    self._last_scheduled_source.value
                    if self._last_scheduled_source is not None
                    else None
                ),
                "last_manual_backwash": (
                    self._last_manual_backwash.isoformat()
                    if self._last_manual_backwash is not None
                    else None
                ),
                "last_trigger": (
                    self._last_trigger.value if self._last_trigger is not None else None
                ),
                "last_scheduled_day": _date_or_none(self._last_scheduled_day),
                "restart_day": _date_or_none(self._restart_day),
                "schedule": (
                    {
                        "time": self._schedule_seen[0].isoformat(),
                        "interval": self._schedule_seen[1],
                    }
                    if self._schedule_seen is not None
                    else None
                ),
                "clock_offset_minutes": self._clock_offset_minutes,
            }
        )

    def update(self, device: AsekoDevice, now: datetime) -> None:
        """Feed a fresh decoded device state into the tracker.

        Call this from the coordinator after every received frame.  No-op
        for devices that do not have a backwash valve (NET — where
        ``backwash_running`` is ``None``).
        """
        if device.backwash_running is None:
            # NET or unknown — nothing to track.
            return
        if self._loading:
            # the stored history is not in yet; a frame or two at start-up
            # is not worth overwriting it for
            return

        # stored with their zone, compared normalised: elapsed time is UTC
        now = dt_util.as_utc(now)
        offset = getattr(device, "clock_offset", None)
        if isinstance(offset, int | float):
            self._clock_offset_minutes = float(offset)
        self._note_schedule(device, now)
        self._backfill_split(device)

        # Step 1: detect a connection-loss gap and clear the in-progress
        # window.  We do this *before* the "relay on" branch below so the
        # subsequent "is None → start new window" code path can see the
        # cleared state and start fresh.
        if (
            self._relay_on_since is not None
            and self._last_frame_at is not None
            and now - self._last_frame_at > MAX_FRAME_GAP
        ):
            _LOGGER.debug(
                "Frame gap %s > MAX_FRAME_GAP %s for serial=%s; "
                "dropping in-progress backwash window",
                now - self._last_frame_at,
                MAX_FRAME_GAP,
                self._serial,
            )
            self._relay_on_since = None
            self._service_menu_in_window = False
        self._last_frame_at = now

        # Step 2: if the relay is on, start (or continue) a new window.
        if device.backwash_running:
            if self._relay_on_since is None:
                self._relay_on_since = now
                self._window_offset_minutes = self._offset_when_opened(device, now)
                self._service_menu_in_window = False
            self._service_menu_in_window |= _service_menu_open(device)
            return

        # Step 3: relay just went off.  Evaluate the previous "on" window.
        if self._relay_on_since is not None:
            self._record_window(
                device,
                self._relay_on_since,
                now,
                service_menu_observed=self._service_menu_in_window,
            )
            self._relay_on_since = None
            self._service_menu_in_window = False

    def _offset_when_opened(self, device: AsekoDevice, now: datetime) -> float | None:
        """Minutes the unit's clock is ahead in the frame that opened the valve.

        Taken from that frame's own clock, not from the published offset: that
        is the median of the last few frames, so right after the clock jumps
        (Home Assistant changing to summer / winter time, the unit's clock set
        by hand) it still holds the old value for a frame or two, and a cycle
        starting then would be compared an hour off.  A frame without the
        unit's clock falls back to the published offset.
        """
        unit_clock = getattr(device, "unit_clock", None)
        if isinstance(unit_clock, datetime | time):
            return offset_seconds(unit_clock, now) / 60
        return self._clock_offset_minutes

    def _on_unit_clock(
        self, moment: datetime, offset_minutes: _OffsetArg = CURRENT_OFFSET
    ) -> datetime:
        """``moment`` as the unit's clock shows it: local wall clock plus the offset.

        ``offset_minutes`` left out means the offset as it is now; ``None``
        means it was not known, and the moment stands as Home Assistant's own
        clock.  The wall clock is Home Assistant's local time, which is what
        the unit's clock is compared with.
        """
        offset = self._offset_or_current(offset_minutes)
        return dt_util.as_local(moment) + timedelta(minutes=offset or 0.0)

    def _offset_or_current(self, offset_minutes: _OffsetArg) -> float | None:
        """Resolve the sentinel; an explicit ``None`` stays not known."""
        if isinstance(offset_minutes, _CurrentOffset):
            return self._clock_offset_minutes
        return offset_minutes

    def _note_schedule(self, device: AsekoDevice, now: datetime) -> None:
        """Restart the schedule phase when the unit shows a changed schedule.

        The unit runs its next cycle the day after a change at the new time,
        and counts the interval from there; switching the schedule off and
        on again is a change too.  The first schedule a tracker sees (a new
        install, a store from before this) is taken as it is.
        """
        at = device.backwash_start_time
        interval = device.backwash_interval
        if not isinstance(at, time) or not isinstance(interval, int):
            return  # not in this frame
        seen = (time(at.hour, at.minute), interval)
        if seen == self._schedule_seen:
            return
        previous, self._schedule_seen = self._schedule_seen, seen
        if previous is not None:
            if interval > 0:
                today = dt_util.as_local(self._on_unit_clock(now)).date()
                self._restart_day = today + timedelta(days=1)
            else:
                self._restart_day = None
            _LOGGER.info(
                "Backwash schedule for serial=%s changed from %s to %s; "
                "next cycle expected on %s",
                self._serial,
                previous,
                seen,
                self._restart_day,
            )
        self._hass.async_create_task(self.async_save())

    def clear_last_scheduled_backwash(self) -> None:
        """Forget the last scheduled backwash, returning it to unknown.

        The undo for ``set_last_scheduled_backwash``: without it a mistyped
        date is permanent, because every other path only ever overwrites the
        value with another one.

        When the last cycle was the scheduled one and no manual cycle is on
        record, clearing also re-arms ``_backfill_split``: the next frame
        classifies that cycle again.  A newer manual or not attributed cycle
        keeps its verdict -- the clear is about the scheduled date only.
        """
        if self._last_scheduled_backwash is None:
            return
        self._last_scheduled_backwash = None
        self._last_scheduled_source = None
        self._last_scheduled_day = None
        if (
            self._last_trigger is AsekoBackwashTrigger.SCHEDULED
            and self._last_manual_backwash is None
        ):
            # the verdict on the stored cycle goes with it, so the backfill runs
            self._last_trigger = None
        _LOGGER.info("Last scheduled backwash cleared for serial=%s", self._serial)
        self._hass.async_create_task(self.async_save())

    def _backfill_split(self, device: AsekoDevice) -> None:
        """Classify a stored ``last_backwash`` that predates the split, once.

        Stores written before the scheduled/manual split existed hold only
        ``last_backwash``.  That cycle *was* one or the other, and the schedule
        needed to tell which is in every frame — so rather than leave both new
        sensors empty until the next cycle (up to a full interval away), work
        it out from the timestamp we already have.

        Runs from ``update`` rather than ``async_load`` because the schedule
        comes from the frame, not from storage.  It is a no-op once either
        bucket is filled, so a later real cycle is never second-guessed.
        """
        if self._last_backwash is None:
            return
        if (
            self._last_scheduled_backwash is not None
            or self._last_manual_backwash is not None
            or self._last_trigger is not None
        ):
            return
        if device.backwash_start_time is None:
            # No schedule in this frame — try again on the next one.
            return

        # The stored value is the midpoint of the relay window, while
        # classification wants its start.  The offset is half a cycle (~50 s on
        # a 100 s backwash), an order of magnitude inside the tolerance, so the
        # midpoint stands in for the start without changing any verdict.
        trigger = self._classify(device, self._last_backwash)
        if trigger is AsekoBackwashTrigger.SCHEDULED:
            slot = self._unit_slot(device, self._last_backwash)
            self._last_scheduled_backwash = slot
            self._last_scheduled_source = AsekoBackwashSource.OBSERVED
            self._last_scheduled_day = slot.date() if slot is not None else None
        elif trigger is AsekoBackwashTrigger.MANUAL:
            self._last_manual_backwash = self._last_backwash
        self._last_trigger = trigger

        _LOGGER.info(
            "Classified pre-existing backwash record for serial=%s as %s (%s)",
            self._serial,
            trigger.value,
            self._last_backwash.isoformat(),
        )
        self._hass.async_create_task(self.async_save())

    def _record_window(
        self,
        device: AsekoDevice,
        started_at: datetime,
        ended_at: datetime,
        *,
        service_menu_observed: bool = False,
    ) -> None:
        """Record a completed relay-on window if it is long enough to be real."""
        duration = ended_at - started_at
        if duration < MIN_BACKWASH_DURATION:
            return

        # Record the midpoint of the window as the backwash timestamp.
        # Better than the start (user might still see "now") or the end
        # (user has to wait until relay goes off to see anything).
        recorded_at = started_at + duration / 2
        if self._last_backwash is not None and recorded_at <= self._last_backwash:
            _LOGGER.debug(
                "Backwash event for serial=%s older than last record; "
                "skipping (%s <= %s)",
                self._serial,
                recorded_at,
                self._last_backwash,
            )
            return

        # Classify on the *start* of the window: that is the moment the unit
        # opened the valve, and therefore the moment to compare against the
        # configured schedule.  The midpoint is shifted by half the cycle
        # duration and would bias every comparison.
        offset = self._window_offset_minutes
        trigger = self._classify(
            device,
            started_at,
            service_menu_observed=service_menu_observed,
            offset_minutes=offset,
        )

        self._last_backwash = recorded_at
        self._last_trigger = trigger
        if trigger is AsekoBackwashTrigger.SCHEDULED:
            # Last write wins: this cycle was detected after whatever is
            # stored, so it is the more current answer — including when it
            # replaces a manual seed with an earlier timestamp.  The seed
            # covered the gap until a real cycle showed up; it has.
            # On the unit's clock: the slot the cycle ran in, e.g. 08:30.
            slot = self._unit_slot(device, started_at, offset)
            self._last_scheduled_backwash = slot
            self._last_scheduled_source = AsekoBackwashSource.OBSERVED
            self._last_scheduled_day = slot.date() if slot is not None else None
            if (
                self._restart_day is not None
                and self._last_scheduled_day is not None
                and self._last_scheduled_day >= self._restart_day
            ):
                # the restarted schedule has run: count from this cycle
                self._restart_day = None
        elif trigger is AsekoBackwashTrigger.MANUAL:
            self._last_manual_backwash = recorded_at
        # UNKNOWN: only last_backwash — neither bucket can claim it

        _LOGGER.info(
            "Backwash detected for serial=%s: %s (duration %s, trigger %s)",
            self._serial,
            recorded_at.isoformat(),
            duration,
            trigger.value,
        )
        # Fire-and-forget save; the coordinator will trigger the
        # next async_save explicitly when convenient.
        self._hass.async_create_task(self.async_save())

    def _unit_slot(
        self,
        device: AsekoDevice,
        moment: datetime,
        offset_minutes: _OffsetArg = CURRENT_OFFSET,
    ) -> datetime | None:
        """Return the schedule slot on the unit's clock that ``moment`` belongs to."""
        at = device.backwash_start_time
        if not isinstance(at, time):
            return None
        return _nearest_slot(self._on_unit_clock(moment, offset_minutes), at)

    def _classify(
        self,
        device: AsekoDevice,
        started_at: datetime,
        *,
        service_menu_observed: bool = False,
        offset_minutes: _OffsetArg = CURRENT_OFFSET,
    ) -> AsekoBackwashTrigger:
        """Return whether a cycle starting at ``started_at`` was scheduled.

        ``offset_minutes``: the clock offset the start is read with -- the
        one when the window opened, ``None`` when it was not known then (the
        wider window on Home Assistant's clock), the current one when the
        argument is left out.

        A cycle counts as scheduled when the unit could have started it
        itself: the schedule is configured and enabled, and the relay opened
        within ``OFFSET_MATCH_TOLERANCE`` of the configured time of day on the
        unit's clock (``_matches_schedule``: drift and summer / winter time
        taken out; ``SCHEDULED_MATCH_TOLERANCE`` on Home Assistant's clock
        before the offset is known) — whatever the menu did.  Outside that window ``service_menu_observed``
        decides: where the profile carries ``MENU_BIT_IS_PRESENCE_ONLY`` the
        unit reports somebody at its menu while the valve was open (see
        ``_service_menu_open``), so the cycle is manual; with the menu closed
        it is UNKNOWN there and, by elimination, manual on units without the
        flag.

        That part is a guess, not a fact.  The device reports that the valve
        opened, never why, so the start time is all there is to go on.  Known
        ways it gets the answer wrong:

        * A cycle started by hand within the tolerance window of the scheduled
          time is reported as scheduled.
        * Only the time of day is checked, not the day itself — a manual cycle
          at exactly ``backwash_start_time`` on a day the interval does not fall on
          still counts as scheduled.  Checking the day would need the schedule
          phase, which is precisely what we are trying to establish, and would
          break whenever the user changes the interval.
        * Before the unit's clock offset is known (``clock_offset``), a unit
          whose clock is more than the tolerance off Home Assistant's has its
          own scheduled cycles reported as manual.  With it known, the start
          is compared on the unit's clock within ``OFFSET_MATCH_TOLERANCE``.
        * A cycle the unit runs on its own for some other reason (e.g. after a
          fault) is reported as manual.

        Classification uses the schedule as it was in the frame at the time of
        the cycle, and is never revisited: changing ``backwash_start_time`` later
        does not reclassify history.
        """
        scheduled_time = device.backwash_start_time
        interval = device.backwash_interval
        if (
            scheduled_time is not None
            and interval is not None
            and interval > 0
            and self._matches_schedule(started_at, scheduled_time, offset_minutes)
        ):
            # In the schedule window the unit's own timer explains the cycle,
            # whether or not somebody had the menu open at the time.
            return AsekoBackwashTrigger.SCHEDULED

        if service_menu_observed:
            # Outside the window, a person at the menu started it.
            return AsekoBackwashTrigger.MANUAL

        # Neither the schedule nor the menu explains it.  A unit that reports
        # its menu (MENU_BIT_IS_PRESENCE_ONLY) had it closed: not attributed.  Units that do not
        # report it keep the elimination rule, or they could never show a
        # manual cycle at all.
        if AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY in device.flags:
            return AsekoBackwashTrigger.UNKNOWN
        return AsekoBackwashTrigger.MANUAL

    def _matches_schedule(
        self,
        started_at: datetime,
        at: time,
        offset_minutes: _OffsetArg = CURRENT_OFFSET,
    ) -> bool:
        """Whether a cycle starting at ``started_at`` fits the daily ``at`` slot."""
        offset_minutes = self._offset_or_current(offset_minutes)
        if offset_minutes is None:
            return _within_tolerance(started_at, at, SCHEDULED_MATCH_TOLERANCE)
        return _within_tolerance(
            self._on_unit_clock(started_at, offset_minutes), at, OFFSET_MATCH_TOLERANCE
        )

    def next_scheduled_backwash(
        self, device: AsekoDevice, now: datetime
    ) -> datetime | None:
        """Return the projected next automatic backwash, or None if unknown.

        The projection starts from the last *scheduled* cycle and steps forward
        in ``backwash_interval`` increments until it lands in the future,
        so a run of missed cycles (HA offline, unit powered down) does not
        leave the sensor stuck on a past date.  The result is snapped to the
        configured ``backwash_start_time`` rather than to the observed midpoint,
        because that is when the unit will actually fire.

        After a change of the schedule the projection starts from the day
        after the change instead (see the module docstring).

        The result is the unit's backwash time as it is set on the unit, on
        the unit's day, not moved by the clock offset (drift or a change of
        time); ``clock_offset`` says how far the unit's clock is off.  Missed
        slots are stepped over on the unit's clock too.

        Returns None while neither a scheduled cycle nor a schedule change is
        known: a manual backwash says nothing about the unit's schedule
        phase, and the device does not transmit it.
        """
        interval = device.backwash_interval
        scheduled_time = device.backwash_start_time
        if scheduled_time is None:
            return None
        if interval is None or interval <= 0:
            # Automatic backwash disabled — there is no next one.
            return None

        step = timedelta(days=interval)
        if self._restart_day is not None:
            next_at = _slot(self._restart_day, scheduled_time)
        elif self._last_scheduled_backwash is not None:
            # The unit-clock day the recorded cycle belongs to, fixed when it
            # was recorded; a store from before that (or a typed-in date)
            # takes the slot nearest to it, which may be the day before when
            # the recorded midpoint fell past midnight.  Built in Home
            # Assistant's time zone, so adding days keeps the wall-clock time
            # across a daylight-saving change.
            # the stored value is on the unit's clock already
            day = (
                self._last_scheduled_day
                or _nearest_slot(self._last_scheduled_backwash, scheduled_time).date()
            )
            next_at = _slot(day, scheduled_time) + step
        else:
            return None
        unit_now = self._on_unit_clock(now)
        while next_at <= unit_now:
            next_at += step
        return next_at


def _parse_date(raw: object) -> date | None:
    """Return a stored ISO date, or None when absent or unreadable."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _date_or_none(day: date | None) -> str | None:
    return day.isoformat() if day is not None else None


def _slot(day: date, at: time) -> datetime:
    """``day`` at the wall-clock time ``at``, in Home Assistant's time zone."""
    return datetime.combine(
        day, time(at.hour, at.minute), tzinfo=dt_util.get_default_time_zone()
    )


def _nearest_slot(moment: datetime, at: time) -> datetime:
    """Return the daily ``at`` slot closest to ``moment`` (day before, same day or after).

    ``moment`` may carry any offset -- a timestamp restored from storage keeps
    the fixed offset it was saved with, a typed-in one may be UTC -- so it is
    turned into local time before its calendar day is taken.
    """
    local = dt_util.as_local(moment)
    return min(
        (_slot(local.date() + timedelta(days=offset), at) for offset in (-1, 0, 1)),
        key=lambda slot: abs(slot - local),
    )


def _within_tolerance(moment: datetime, at: time, tolerance: timedelta) -> bool:
    """Return True if ``moment`` is within ``tolerance`` of the daily ``at`` time.

    Checks the previous and next day as well so a cycle scheduled near
    midnight still matches when the two land on different dates.
    """
    return abs(moment - _nearest_slot(moment, at)) <= tolerance
