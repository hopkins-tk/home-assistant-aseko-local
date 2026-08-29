"""Persistent tracker for observed filter backwash cycles.

A "successful" backwash is defined as the backwash relay (byte[29] bit 0x01)
remaining continuously active for at least 60 seconds.  Short relay
activations (e.g. menu navigation, output-test mode) are ignored.

That much is observed fact.  Everything else here is derived from it.

Each recorded cycle is then *classified*, in this order:

    * the settings menu was open while the valve was  →  MANUAL
    * menu shut, and the relay opened within ±``SCHEDULED_MATCH_TOLERANCE``
      of the configured ``backwash_time`` on a unit whose schedule is
      enabled                                        →  SCHEDULED
    * anything else, on a device that reports the menu →  UNKNOWN
    * anything else, on a device that does not        →  MANUAL

The device does not transmit *why* the valve opened, nor when it last ran.
Only the first rule is an observation: on SALT, byte[37] bit 0x04 marks the
settings menu being open, and that is the menu a backwash is started by hand
from, so a cycle running while the bit is set was started by a person.  See
``_service_menu_open``.

The second rule is a comparison against a clock and can be wrong — the ways
are listed in ``_classify``.

What is left over depends on the device.  Where the menu bit is available the
answer is UNKNOWN: the valve opening is a fact, but a cycle that does not fit
the schedule is not thereby evidence that somebody started it, and calling it
manual would put a guess in the same field the menu bit fills with an
observation.  Where it is not available the older elimination rule stands and
the cycle is called MANUAL — no better, but the alternative there is an
answer that is always empty.

Consumers should treat ``last_backwash`` as reliable, ``last_manual_backwash``
as observed, and ``last_scheduled_backwash`` — with the
``next_scheduled_backwash`` projection built on it — as an estimate.

Nothing is guessed before the first observation, though: every value starts out
as ``None``: until a cycle has actually been seen, the honest answer is
"unknown" rather than a timestamp derived from the schedule.

The last scheduled cycle is what drives the "next backwash" projection — a
manual backwash does not reveal (nor, on the unit, reset) the schedule phase.

The recorded timestamps are stored persistently via the Home Assistant
``Store`` API and survive:
    * Home Assistant restarts
    * Integration reloads
    * Integration updates
    * Network interruptions (with a 60s grace period)

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
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .aseko_data import (
    AsekoBackwashSource,
    AsekoBackwashTrigger,
    AsekoDeviceType,
)

if TYPE_CHECKING:
    from .aseko_data import AsekoDevice

_LOGGER = logging.getLogger(__name__)


def _service_menu_open(device: "AsekoDevice") -> bool:
    """Return True if somebody has the unit's settings menu open.

    On SALT, byte[37] bit 0x04 marks that menu — the one filtration and
    backwash can be started by hand from.  It appears on entering, before
    anything is touched, so on its own it says only that a person is at the
    unit.  Paired with a running backwash it says more: a capture of a
    by-hand cycle has the bit set on every frame from ~30 s before the valve
    opened until ~20 s after it closed.  Somebody was standing at the menu
    the button lives on — observed, not inferred from the clock.

    Restricted to SALT because the same bit is documented differently on
    HOME firmware B (Issue #133): a standing manual override that forces the
    pump off and can stay set indefinitely.  Honouring it there would
    misclassify every scheduled cycle that ran while the override was on.

    The bit is only ever *additional* evidence.  It is never used to call a
    cycle scheduled: nobody being at the unit is no proof that the unit
    started the cycle itself.
    """
    return _service_menu_reported(device) and device.service_menu_open is True


def _service_menu_reported(device: "AsekoDevice") -> bool:
    """Return True if this device reports the settings menu usefully at all.

    Only SALT does.  NET has no filtration output and leaves the field None;
    on HOME firmware B the same bit is documented as a standing pump override
    (Issue #133) that can sit set indefinitely, so it says nothing about
    whether somebody was at the unit for any one cycle.

    This gates more than the MANUAL verdict — it decides whether a cycle that
    matches nothing can be left UNKNOWN.  Where the signal exists, "not
    observed and not on schedule" is a real answer.  Where it does not, there
    is nothing better to say than the pre-existing guess, so the elimination
    rule stands.  See ``_classify``.
    """
    return (
        device.device_type is AsekoDeviceType.SALT
        and device.service_menu_open is not None
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
# ``backwash_time`` and still count as the unit's own scheduled cycle.
# The unit fires on its own clock, which can be a few minutes off from HA's,
# and the frame that first reports the relay as on can lag the actual start
# by one transmit interval (~30 s).  15 minutes absorbs both while staying
# far below any plausible "user pressed the button around that time" overlap.
SCHEDULED_MATCH_TOLERANCE = timedelta(minutes=15)

# Home Assistant Store schema versioning — bump if the persisted shape changes.
# Version 1 held only ``last_backwash``; the classification keys added later are
# optional on load, so old stores keep working and simply report the trigger of
# the pre-upgrade cycle as unknown.
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "aseko_local_backwash_"


class BackwashTracker:
    """Detects, classifies and persistently records filter backwash events.

    One instance per device (keyed by ``serial_number``).  Holds the relay
    state machine between frames and is responsible for saving the
    confirmed backwash timestamps to disk so they survive restarts.
    """

    def __init__(self, hass: HomeAssistant, serial_number: int) -> None:
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

        # Last frame timestamp we processed — used to detect dropped connections.
        self._last_frame_at: datetime | None = None

        # Recorded timestamps (loaded from / saved to storage).
        self._last_backwash: datetime | None = None
        self._last_scheduled_backwash: datetime | None = None
        self._last_manual_backwash: datetime | None = None
        self._last_trigger: AsekoBackwashTrigger | None = None

        # _backfill_split runs at most once per session — see its docstring.
        self._backfill_attempted = False

        # Where _last_scheduled_backwash came from: OBSERVED (we watched the
        # valve run) or MANUAL (the user seeded it).  Drives the "source"
        # attribute on both the last- and next-scheduled sensors.
        self._last_scheduled_source: AsekoBackwashSource | None = None

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

    async def async_load(self) -> None:
        """Load the persistent state from storage.  Call once at startup."""
        data = await self._store.async_load()
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
        """
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
            }
        )

    def update(self, device: "AsekoDevice", now: datetime) -> None:
        """Feed a fresh decoded device state into the tracker.

        Call this from the coordinator after every received frame.  No-op
        for devices that do not have a backwash valve (NET — where
        ``backwash_active`` is ``None``).
        """
        if device.backwash_active is None:
            # NET or unknown — nothing to track.
            return

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
        if device.backwash_active:
            if self._relay_on_since is None:
                self._relay_on_since = now
                self._service_menu_in_window = False
            self._service_menu_in_window |= _service_menu_open(device)
            return

        # Step 3: relay just went off.  Evaluate the previous "on" window.
        if self._relay_on_since is not None:
            self._record_window(
                device, self._relay_on_since, now, self._service_menu_in_window
            )
            self._relay_on_since = None
            self._service_menu_in_window = False

    def clear_last_scheduled_backwash(self) -> None:
        """Forget the last scheduled backwash, returning it to unknown.

        The undo for ``set_last_scheduled_backwash``: without it a mistyped
        date is permanent, because every other path only ever overwrites the
        value with another one.

        Clearing it also re-arms ``_backfill_split``, so if a
        ``last_backwash`` is on record and no manual cycle has been observed,
        the next frame re-derives the split from it.
        """
        if self._last_scheduled_backwash is None:
            return
        self._last_scheduled_backwash = None
        self._last_scheduled_source = None
        _LOGGER.info("Last scheduled backwash cleared for serial=%s", self._serial)
        self._hass.async_create_task(self.async_save())

    def _backfill_split(self, device: "AsekoDevice") -> None:
        """Classify a stored ``last_backwash`` that predates the split, once.

        Stores written before the scheduled/manual split existed hold only
        ``last_backwash``.  That cycle *was* one or the other, and the schedule
        needed to tell which is in every frame — so rather than leave both new
        sensors empty until the next cycle (up to a full interval away), work
        it out from the timestamp we already have.

        The menu bit is not available retroactively, so this can only ever
        reach the schedule half of the answer: a stored cycle that does not
        match the schedule comes out ``UNKNOWN`` and fills neither bucket.

        Runs from ``update`` rather than ``async_load`` because the schedule
        comes from the frame, not from storage.  It is a no-op once either
        bucket is filled, so a later real cycle is never second-guessed, and
        runs at most once per session either way — an UNKNOWN verdict fills
        nothing, and re-deciding it on every frame would only re-log it.
        """
        if self._last_backwash is None:
            return
        if self._backfill_attempted:
            return
        if (
            self._last_scheduled_backwash is not None
            or self._last_manual_backwash is not None
        ):
            return
        if device.backwash_time is None:
            # No schedule in this frame — try again on the next one.
            return

        # The stored value is the midpoint of the relay window, while
        # classification wants its start.  The offset is half a cycle (~50 s on
        # a 100 s backwash), an order of magnitude inside the tolerance, so the
        # midpoint stands in for the start without changing any verdict.
        self._backfill_attempted = True
        trigger = self._classify(device, self._last_backwash)
        if self._last_trigger is None:
            self._last_trigger = trigger

        if trigger is AsekoBackwashTrigger.SCHEDULED:
            self._last_scheduled_backwash = self._last_backwash
            self._last_scheduled_source = AsekoBackwashSource.OBSERVED
        elif trigger is AsekoBackwashTrigger.MANUAL:
            # Only reachable on a device with no menu signal, where MANUAL is
            # the elimination verdict — the bit itself is not recoverable
            # after the fact, so a live MANUAL can never be backfilled.
            self._last_manual_backwash = self._last_backwash
        else:
            # UNKNOWN — the stored timestamp does not match the schedule, and
            # whether somebody was at the unit for it is not recoverable now.
            # It stays in last_backwash alone.
            _LOGGER.debug(
                "Pre-existing backwash record for serial=%s (%s) matches no "
                "schedule; leaving the split empty",
                self._serial,
                self._last_backwash.isoformat(),
            )
            return

        _LOGGER.info(
            "Classified pre-existing backwash record for serial=%s as %s (%s)",
            self._serial,
            trigger.value,
            self._last_backwash.isoformat(),
        )
        self._hass.async_create_task(self.async_save())

    def _record_window(
        self,
        device: "AsekoDevice",
        started_at: datetime,
        ended_at: datetime,
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
        trigger = self._classify(device, started_at, service_menu_observed)

        self._last_backwash = recorded_at
        self._last_trigger = trigger
        if trigger is AsekoBackwashTrigger.SCHEDULED:
            # Last write wins: this cycle was detected after whatever is
            # stored, so it is the more current answer — including when it
            # replaces a manual seed with an earlier timestamp.  The seed
            # covered the gap until a real cycle showed up; it has.
            self._last_scheduled_backwash = recorded_at
            self._last_scheduled_source = AsekoBackwashSource.OBSERVED
        elif trigger is AsekoBackwashTrigger.MANUAL:
            self._last_manual_backwash = recorded_at
        # UNKNOWN updates neither split: last_backwash records that a cycle
        # happened, and that is all this frame supports.  Filing it under one
        # of the two would also drag next_scheduled_backwash with it.

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

    @staticmethod
    def _classify(
        device: "AsekoDevice",
        started_at: datetime,
        service_menu_observed: bool = False,
    ) -> AsekoBackwashTrigger:
        """Return whether a cycle starting at ``started_at`` was scheduled.

        ``service_menu_observed`` is the one hard signal available: on SALT the
        unit reports that somebody was operating it by hand while the valve
        was open (see ``_service_menu_open``), which settles the question.
        It is only ever raised, never lowered — its absence proves nothing.

        Without it, a cycle counts as scheduled only if the unit could have
        started it itself: the schedule must be configured and enabled, and
        the relay must have opened within ``SCHEDULED_MATCH_TOLERANCE`` of the
        configured time of day.

        What happens to a cycle that is neither depends on whether the device
        reports the menu at all (``_service_menu_reported``):

        * It does (SALT) — ``UNKNOWN``.  The valve opening is a fact; who
          opened it is not, and a cycle outside the schedule window is only
          evidence that the unit's own timer does not explain it, not evidence
          that a person does.  Calling it manual would put a guess in the same
          field the menu signal fills with an observation.
        * It does not (everything else) — ``MANUAL``, by elimination, as
          before this signal existed.  The guess is no better there, but it is
          all there is, and leaving those devices with a permanently empty
          ``last_manual_backwash`` would trade a rough answer for none at all.

        The schedule match itself is still a comparison against a clock, so it
        can be wrong in ways worth knowing:

        * A cycle started by hand within the tolerance window, on a unit whose
          menu bit is not available (anything but SALT), is reported as
          scheduled.
        * Only the time of day is checked, not the day itself — a cycle at
          exactly ``backwash_time`` on a day the interval does not fall on
          still counts as scheduled.  Checking the day would need the schedule
          phase, which is precisely what we are trying to establish, and would
          break whenever the user changes the interval.
        * If the unit's clock drifts more than the tolerance from Home
          Assistant's, its own scheduled cycles come out UNKNOWN.

        Classification uses the schedule as it was in the frame at the time of
        the cycle, and is never revisited: changing ``backwash_time`` later
        does not reclassify history.
        """
        if service_menu_observed:
            # Observed fact rather than inference: a person was at the unit.
            return AsekoBackwashTrigger.MANUAL

        scheduled_time = device.backwash_time
        interval = device.backwash_every_n_days
        if (
            scheduled_time is not None
            and interval is not None
            and interval > 0
            and _within_tolerance(started_at, scheduled_time, SCHEDULED_MATCH_TOLERANCE)
        ):
            return AsekoBackwashTrigger.SCHEDULED

        if _service_menu_reported(device):
            # The device would have told us if somebody had been at it, and it
            # did not — so this matched nothing, and that is the answer.
            return AsekoBackwashTrigger.UNKNOWN

        # No menu signal on this device type: fall back to the elimination
        # rule this integration has always used.
        return AsekoBackwashTrigger.MANUAL

    def next_scheduled_backwash(
        self, device: "AsekoDevice", now: datetime
    ) -> datetime | None:
        """Return the projected next automatic backwash, or None if unknown.

        The projection starts from the last *scheduled* cycle and steps forward
        in ``backwash_every_n_days`` increments until it lands in the future,
        so a run of missed cycles (HA offline, unit powered down) does not
        leave the sensor stuck on a past date.  The result is snapped to the
        configured ``backwash_time`` rather than to the observed midpoint,
        because that is when the unit will actually fire.

        Returns None while no scheduled cycle has been observed: a manual
        backwash says nothing about the unit's schedule phase, and the device
        does not transmit it.
        """
        last_scheduled = self._last_scheduled_backwash
        interval = device.backwash_every_n_days
        scheduled_time = device.backwash_time
        if last_scheduled is None or scheduled_time is None:
            return None
        if interval is None or interval <= 0:
            # Automatic backwash disabled — there is no next one.
            return None

        step = timedelta(days=interval)
        next_at = _at_time_of_day(last_scheduled, scheduled_time) + step
        while next_at <= now:
            next_at += step
        return next_at


def _at_time_of_day(moment: datetime, at: time) -> datetime:
    """Return ``moment``'s date at the given wall-clock time, same tz."""
    return moment.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)


def _within_tolerance(moment: datetime, at: time, tolerance: timedelta) -> bool:
    """Return True if ``moment`` is within ``tolerance`` of the daily ``at`` time.

    Checks the previous and next day as well so a cycle scheduled near
    midnight still matches when the two land on different dates.
    """
    same_day = _at_time_of_day(moment, at)
    return any(
        abs(moment - (same_day + timedelta(days=offset))) <= tolerance
        for offset in (-1, 0, 1)
    )
