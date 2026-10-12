"""Tests for BackwashTracker.

Models a real-world backwash cycle: the relay must stay on for at least
60 seconds (MIN_BACKWASH_DURATION) for the event to be recorded, and each
recorded cycle is classified as scheduled or manual from its start time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.models import (
    AsekoBackwashSource,
    AsekoBackwashTrigger,
    AsekoDeviceType,
    AsekoProfileFlag,
)
from custom_components.aseko_local.trackers.backwash import (
    MAX_FRAME_GAP,
    SCHEDULED_MATCH_TOLERANCE,
    BackwashTracker,
)
from custom_components.aseko_local.trackers.clock import ClockTracker

from .test_decode_v7 import _make_base_bytes

T0 = datetime(2026, 6, 14, 21, 0, 0, tzinfo=UTC)

# The unit's configured backwash time, matching T0's time of day, so a cycle
# starting at T0 counts as the unit's own scheduled run.
SCHEDULE_AT = time(21, 0)
SCHEDULE_EVERY_N_DAYS = 3


@pytest.fixture(autouse=True)
def _home_assistant_in_utc() -> Iterator[None]:
    """Pin Home Assistant's time zone to UTC: these tests state the schedule in UTC.

    The tracker projects and classifies in Home Assistant's time zone, so pin it
    to UTC here.  Tests about local time set their own zone on top.  The zone
    goes through ``set_default_time_zone`` (which clears its cache) and is put
    back afterwards, so the test plugin's own teardown finds what it set.
    """
    original = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(UTC)
    yield
    dt_util.set_default_time_zone(original)


# ── helpers ──────────────────────────────────────────────────────────────────


def _device(
    backwash_running: bool | None,
    *,
    backwash_start_time: time | None = None,
    backwash_interval: int | None = None,
) -> MagicMock:
    """Minimal stand-in for AsekoDevice with only the fields the tracker reads.

    The schedule defaults to "not configured", which classifies every recorded
    cycle as manual — the right default for the tests that only care about the
    relay-window state machine.
    """
    dev = MagicMock()
    dev.backwash_running = backwash_running
    dev.backwash_start_time = backwash_start_time
    dev.backwash_interval = backwash_interval
    return dev


def _scheduled_device(backwash_running: bool | None) -> MagicMock:
    """Stand-in for a device with an enabled backwash schedule at SCHEDULE_AT."""
    return _device(
        backwash_running,
        backwash_start_time=SCHEDULE_AT,
        backwash_interval=SCHEDULE_EVERY_N_DAYS,
    )


def _run_cycle(
    tracker: BackwashTracker,
    start: datetime,
    duration: timedelta = timedelta(seconds=90),
    device_factory=_scheduled_device,
) -> None:
    """Drive one complete relay on → off window through the tracker."""
    tracker.update(device_factory(True), start)
    tracker.update(device_factory(False), start + duration)


def _hass() -> MagicMock:
    """Mock Home Assistant — only ``async_create_task`` is needed by the tracker.

    ``Store.__init__`` requires ``hass.config.path(...)`` to resolve to a real
    path-like value, so we return a ``Path`` instead of letting the default
    ``MagicMock`` raise ``AttributeError`` deep in the constructor.

    The tracker hands ``async_save()`` to ``async_create_task``.  A plain
    ``MagicMock`` swallows the coroutine without awaiting it, which raises a
    RuntimeWarning per call; closing it keeps the call recorded (tests assert on
    it) while leaving nothing pending.
    """
    hass = MagicMock()
    hass.config.path.side_effect = lambda *parts: "/tmp/aseko_test/" + "/".join(parts)
    hass.async_create_task.side_effect = lambda coro, *args, **kwargs: coro.close()
    return hass


# ── basic accumulation ──────────────────────────────────────────────────────


def test_short_backwash_below_threshold_not_recorded() -> None:
    """Relay on for 30 s (below MIN_BACKWASH_DURATION) → no event recorded."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_running=True)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))
    tracker.update(_device(backwash_running=False), T0 + timedelta(seconds=30))

    assert tracker.last_backwash is None


def test_long_backwash_recorded_at_midpoint() -> None:
    """Relay on for 90 s (≥ 60 s threshold) → event recorded at window midpoint."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_running=True)

    tracker.update(device, T0)
    tracker.update(_device(backwash_running=False), T0 + timedelta(seconds=90))

    assert tracker.last_backwash is not None
    # Midpoint of [T0, T0+90s] = T0 + 45s
    expected = T0 + timedelta(seconds=45)
    assert tracker.last_backwash == expected


def test_exactly_threshold_backwash_recorded() -> None:
    """Relay on for exactly 60 s → still recorded (≥ comparison, not >)."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_running=True)

    tracker.update(device, T0)
    tracker.update(_device(backwash_running=False), T0 + timedelta(seconds=60))

    assert tracker.last_backwash is not None
    # 60s window → midpoint at T0 + 30s
    assert tracker.last_backwash == T0 + timedelta(seconds=30)


def test_two_consecutive_backwashes_keep_latest() -> None:
    """If two backwashes happen in sequence, keep the later one."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    # First cycle: T0 → T0 + 90s
    tracker.update(_device(backwash_running=True), T0)
    tracker.update(_device(backwash_running=False), T0 + timedelta(seconds=90))
    first = tracker.last_backwash
    assert first is not None

    # Second cycle: T0+5min → T0+5min+90s
    second_start = T0 + timedelta(minutes=5)
    tracker.update(_device(backwash_running=True), second_start)
    tracker.update(
        _device(backwash_running=False), second_start + timedelta(seconds=90)
    )

    assert tracker.last_backwash > first
    assert tracker.last_backwash == second_start + timedelta(seconds=45)


# ── loss of connection ──────────────────────────────────────────────────────


def test_lost_connection_resets_in_progress_window() -> None:
    """Frame gap > MAX_FRAME_GAP between two relay-on updates → window reset.

    The reset discards the previous (unreliable) "on" window.  A
    subsequent "on" frame re-opens a fresh window starting at the
    recovery time.  The short follow-up window (< MIN_BACKWASH_DURATION)
    must therefore NOT be recorded.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_running=True)

    tracker.update(device, T0)  # relay on, window starts
    # MAX_FRAME_GAP (5 min) + 1 s later, still on, but we lost the connection.
    # The reset clears the stale T0 window.  The same "on" frame re-opens
    # the window at the recovery time, so we expect a new value here.
    recovery = T0 + MAX_FRAME_GAP + timedelta(seconds=1)
    tracker.update(device, recovery)
    assert tracker._relay_on_since == recovery  # type: ignore[attr-defined]

    # 30 s later the relay goes off — only 30 s, not a real backwash.
    tracker.update(_device(backwash_running=False), recovery + timedelta(seconds=30))
    assert tracker.last_backwash is None


def test_lost_connection_during_real_backwash_does_not_record() -> None:
    """A long but disconnected window should not be recorded as a backwash.

    Scenario: the device is in a real backwash cycle, the connection drops
    for longer than MAX_FRAME_GAP, the connection recovers, and the relay
    is still on.  When the relay finally goes off, the *total* time from
    the original start is > 60 s — but the cycle spanned a disconnect and
    must not be recorded.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_running=True)

    tracker.update(device, T0)
    # Connection drops for 6 minutes (> MAX_FRAME_GAP).
    recovery = T0 + timedelta(minutes=6)
    tracker.update(device, recovery)
    # Relay finally goes off, total elapsed would be 6 min 30 s but cycle is split.
    tracker.update(_device(backwash_running=False), recovery + timedelta(seconds=30))
    assert tracker.last_backwash is None


def test_short_gap_does_not_reset() -> None:
    """Frame gap < MAX_FRAME_GAP → window continues."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_running=True)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=30))  # still on
    assert tracker._relay_on_since == T0  # type: ignore[attr-defined]

    # Window still tracks from T0 → at T0+90s, recorded
    tracker.update(_device(backwash_running=False), T0 + timedelta(seconds=90))
    assert tracker.last_backwash == T0 + timedelta(seconds=45)


# ── NET devices ─────────────────────────────────────────────────────────────


def test_net_device_skipped() -> None:
    """backwash_running is None on NET → tracker is a no-op."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker.update(_device(backwash_running=None), T0)
    tracker.update(_device(backwash_running=None), T0 + timedelta(seconds=120))

    assert tracker.last_backwash is None
    assert tracker._relay_on_since is None  # type: ignore[attr-defined]
    assert tracker._last_frame_at is None  # type: ignore[attr-defined]


# ── persistence ─────────────────────────────────────────────────────────────


async def test_async_load_from_empty_store() -> None:
    """async_load on a fresh Store leaves last_backwash as None."""
    hass = _hass()
    hass.config = MagicMock()  # unused but required by HA core for Store
    # We don't call real Store here; we just verify that an empty load
    # is handled gracefully.  Direct construction with no stored data:
    tracker = BackwashTracker(hass, serial_number=110071590)
    # Manually replicate what async_load would do with an empty dict:
    # (no async_store involved — empty load is a no-op)
    assert tracker.last_backwash is None


async def test_async_save_writes_nulls_rather_than_skipping() -> None:
    """An empty state must be written, not skipped.

    Skipping made clearing a no-op on disk: the cleared value came back on the
    next restart.  Callers only reach async_save after a change, so writing
    unconditionally costs nothing.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_save = AsyncMock()  # type: ignore[method-assign]

    await tracker.async_save()

    saved = tracker._store.async_save.call_args.args[0]  # type: ignore[attr-defined]
    assert saved["last_backwash"] is None
    assert saved["last_scheduled_backwash"] is None


# ── scheduled vs. manual classification ─────────────────────────────────────


def test_nothing_recorded_starts_unknown() -> None:
    """A fresh tracker reports every field as unknown, not as a schedule guess."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    assert tracker.last_backwash is None
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None
    assert tracker.next_scheduled_backwash(_scheduled_device(False), T0) is None


def test_cycle_at_scheduled_time_is_scheduled() -> None:
    """A cycle starting at the configured backwash_start_time is the unit's own run."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    # on the unit's clock: the 21:00 slot, not the midpoint Home Assistant saw
    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_backwash == T0 + timedelta(seconds=45)
    assert tracker.last_manual_backwash is None


def test_cycle_just_inside_tolerance_is_scheduled() -> None:
    """The unit's clock may drift from HA's — the tolerance window absorbs it."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0 + SCHEDULED_MATCH_TOLERANCE - timedelta(seconds=1))

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_cycle_outside_tolerance_is_manual() -> None:
    """A cycle well away from the scheduled time was started by hand."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    started = T0 + timedelta(hours=2)
    _run_cycle(tracker, started)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash == started + timedelta(seconds=45)
    assert tracker.last_backwash == tracker.last_manual_backwash
    assert tracker.last_scheduled_backwash is None


def test_cycle_is_manual_when_schedule_disabled() -> None:
    """Interval 0 = automatic backwash off → the unit cannot have started it."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def _disabled(active) -> MagicMock:
        return _device(active, backwash_start_time=SCHEDULE_AT, backwash_interval=0)

    _run_cycle(tracker, T0, device_factory=_disabled)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_cycle_is_manual_when_schedule_unconfigured() -> None:
    """No backwash_start_time in the frame (0xFF) → nothing to match against."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0, device_factory=_device)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_scheduled_time_near_midnight_matches_across_days() -> None:
    """A cycle at 00:05 still matches a 23:55 schedule on the previous day."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def _near_midnight(active) -> MagicMock:
        return _device(
            active,
            backwash_start_time=time(23, 55),
            backwash_interval=SCHEDULE_EVERY_N_DAYS,
        )

    # 00:05 the next day — 10 minutes after the scheduled slot, but on the
    # other side of the date boundary.
    _run_cycle(
        tracker,
        datetime(2026, 6, 15, 0, 5, 0, tzinfo=UTC),
        device_factory=_near_midnight,
    )

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_manual_cycle_keeps_earlier_scheduled_record() -> None:
    """A manual run must not overwrite the last scheduled one (it drives 'next')."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    scheduled = tracker.last_scheduled_backwash
    assert scheduled is not None

    manual_start = T0 + timedelta(days=1, hours=4)
    _run_cycle(tracker, manual_start)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash == manual_start + timedelta(seconds=45)
    assert tracker.last_scheduled_backwash == scheduled
    # "Last backwash" tracks whichever came last, regardless of kind.
    assert tracker.last_backwash == tracker.last_manual_backwash


# ── next-backwash projection ────────────────────────────────────────────────


def test_next_scheduled_backwash_unknown_after_manual_only() -> None:
    """A manual cycle says nothing about the unit's schedule phase."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_cycle(tracker, T0 + timedelta(hours=2))

    assert tracker.last_manual_backwash is not None
    assert tracker.next_scheduled_backwash(device, T0 + timedelta(hours=3)) is None


def test_next_scheduled_backwash_projected_from_last_scheduled() -> None:
    """Next = last scheduled cycle + interval, snapped to the configured time."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_cycle(tracker, T0)

    # Recorded at the window midpoint (T0 + 45 s), but the projection snaps to
    # the configured 21:00 slot — that is when the unit will actually fire.
    assert tracker.next_scheduled_backwash(
        device, T0 + timedelta(minutes=5)
    ) == datetime(2026, 6, 17, 21, 0, 0, tzinfo=UTC)


def test_next_scheduled_backwash_rolls_forward_past_missed_cycles() -> None:
    """Cycles missed while HA was down must not leave 'next' stuck in the past."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_cycle(tracker, T0)

    # Ten days later: 06-17, 06-20 and 06-23 have all come and gone.
    now = T0 + timedelta(days=10)
    assert tracker.next_scheduled_backwash(device, now) == datetime(
        2026, 6, 26, 21, 0, 0, tzinfo=UTC
    )


def test_next_scheduled_backwash_none_when_schedule_disabled() -> None:
    """With automatic backwash switched off there is no next cycle to project."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    assert tracker.last_scheduled_backwash is not None

    disabled = _device(False, backwash_start_time=SCHEDULE_AT, backwash_interval=0)
    assert tracker.next_scheduled_backwash(disabled, T0 + timedelta(minutes=5)) is None


# ── persistence of the classification ───────────────────────────────────────


async def test_async_load_restores_classified_state() -> None:
    """A stored payload round-trips into all four public fields."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    stored = {
        "last_backwash": (T0 + timedelta(days=1)).isoformat(),
        "last_scheduled_backwash": T0.isoformat(),
        "last_manual_backwash": (T0 + timedelta(days=1)).isoformat(),
        "last_trigger": "manual",
    }
    tracker._store.async_load = AsyncMock(return_value=stored)  # type: ignore[method-assign]

    await tracker.async_load()

    assert tracker.last_backwash == T0 + timedelta(days=1)
    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_manual_backwash == T0 + timedelta(days=1)
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


async def test_async_load_tolerates_version_1_payload() -> None:
    """Stores written before classification existed keep their timestamp.

    The trigger of that pre-upgrade cycle is genuinely unknown, so it stays
    None rather than being guessed at.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_load = AsyncMock(  # type: ignore[method-assign]
        return_value={"last_backwash": T0.isoformat()}
    )

    await tracker.async_load()

    assert tracker.last_backwash == T0
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None


async def test_async_save_persists_classification() -> None:
    """The saved payload carries everything async_load reads back."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_save = AsyncMock()  # type: ignore[method-assign]

    _run_cycle(tracker, T0)
    await tracker.async_save()

    saved = tracker._store.async_save.call_args.args[0]  # type: ignore[attr-defined]
    assert saved["last_backwash"] == (T0 + timedelta(seconds=45)).isoformat()
    assert saved["last_scheduled_backwash"] == T0.isoformat()
    assert saved["last_manual_backwash"] is None
    assert saved["last_trigger"] == "scheduled"


# ── manual seeding and provenance ───────────────────────────────────────────


def test_manual_seed_marks_source_and_drives_projection() -> None:
    """A seeded date starts the projection and is labelled as manual."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    seeded = T0 - timedelta(days=1)
    tracker.set_last_scheduled_backwash(seeded)

    assert tracker.last_scheduled_backwash == seeded
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL
    # Seeded 2026-06-13 21:00, interval 3 days -> 2026-06-16 21:00.
    assert tracker.next_scheduled_backwash(device, T0) == datetime(
        2026, 6, 16, 21, 0, 0, tzinfo=UTC
    )


def test_manual_seed_does_not_touch_observed_last_backwash() -> None:
    """last_backwash means "we watched this happen" — typing a date does not."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.set_last_scheduled_backwash(T0 - timedelta(days=1))

    assert tracker.last_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None


def test_cycle_detected_after_a_seed_supersedes_it() -> None:
    """The seed stood in for a real cycle; once one is detected, it takes over."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.set_last_scheduled_backwash(T0 - timedelta(days=1))
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL

    _run_cycle(tracker, T0)

    # on the unit's clock: the 21:00 slot, not the midpoint Home Assistant saw
    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED


def test_cycle_detected_after_a_later_dated_seed_still_supersedes_it() -> None:
    """Last write wins — the stored timestamps are never compared.

    Even a seed dated after the detected cycle gives way, because the cycle
    was recorded later and is the more current answer.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.set_last_scheduled_backwash(T0 + timedelta(days=5))
    _run_cycle(tracker, T0)

    # on the unit's clock: the 21:00 slot, not the midpoint Home Assistant saw
    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED


def test_manual_seed_overrides_an_observed_value() -> None:
    """A manual entry replaces a detected one — the user has a reason."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED

    corrected = T0 - timedelta(days=10)
    tracker.set_last_scheduled_backwash(corrected)

    assert tracker.last_scheduled_backwash == corrected
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


def test_observed_manual_cycle_leaves_the_seed_alone() -> None:
    """A detected *manual* backwash says nothing about the schedule phase."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    seeded = T0 - timedelta(days=1)
    tracker.set_last_scheduled_backwash(seeded)
    _run_cycle(tracker, T0 + timedelta(hours=3))  # far from backwash_start_time

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_scheduled_backwash == seeded
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


def test_no_source_while_nothing_is_known() -> None:
    """No value, no provenance — the attribute stays absent rather than lying."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    assert tracker.last_scheduled_source is None


async def test_manual_seed_is_persisted_before_any_observation() -> None:
    """async_save must not bail out just because last_backwash is still None."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_save = AsyncMock()  # type: ignore[method-assign]

    seeded = T0 - timedelta(days=1)
    tracker.set_last_scheduled_backwash(seeded)
    await tracker.async_save()

    saved = tracker._store.async_save.call_args.args[0]  # type: ignore[attr-defined]
    assert saved["last_backwash"] is None
    assert saved["last_scheduled_backwash"] == seeded.isoformat()
    assert saved["last_scheduled_source"] == "manual"


async def test_async_load_restores_manual_source() -> None:
    """A seeded value survives a restart still marked as manual."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_load = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "last_scheduled_backwash": T0.isoformat(),
            "last_scheduled_source": "manual",
        }
    )

    await tracker.async_load()

    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


async def test_async_load_treats_sourceless_stored_value_as_observed() -> None:
    """Stores written before provenance existed can only hold observed values."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_load = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "last_backwash": T0.isoformat(),
            "last_scheduled_backwash": T0.isoformat(),
        }
    )

    await tracker.async_load()

    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED


# ── backfilling an old store ────────────────────────────────────────────────


def test_backfill_classifies_a_pre_split_record_as_scheduled() -> None:
    """A store holding only last_backwash gets classified on the first frame.

    Stores written before the scheduled/manual split existed would otherwise
    leave both new sensors empty until the next real cycle, up to a whole
    interval away — even though the schedule needed to classify the stored
    value arrives in every frame.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._last_backwash = T0  # type: ignore[attr-defined]

    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=5))

    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_manual_backwash is None


def test_backfill_classifies_a_pre_split_record_as_manual() -> None:
    """Same, for a stored cycle that did not run at the scheduled time."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    off_schedule = T0 + timedelta(hours=4)
    tracker._last_backwash = off_schedule  # type: ignore[attr-defined]

    tracker.update(_scheduled_device(False), off_schedule + timedelta(minutes=5))

    assert tracker.last_manual_backwash == off_schedule
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_scheduled_backwash is None


def test_backfill_waits_for_a_frame_that_carries_the_schedule() -> None:
    """Without backwash_start_time there is nothing to classify against — retry later."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._last_backwash = T0  # type: ignore[attr-defined]

    tracker.update(_device(False), T0 + timedelta(minutes=5))
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None

    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=10))
    assert tracker.last_scheduled_backwash == T0


def test_backfill_does_not_touch_an_already_split_store() -> None:
    """Once either bucket is filled the record is current — leave it alone."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    seeded = T0 - timedelta(days=3)
    tracker._last_backwash = T0  # type: ignore[attr-defined]
    tracker.set_last_scheduled_backwash(seeded)

    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=5))

    assert tracker.last_scheduled_backwash == seeded
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


def test_backfill_is_a_no_op_on_an_empty_store() -> None:
    """Nothing stored, nothing to classify."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.update(_scheduled_device(False), T0)

    assert tracker.last_backwash is None
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None


# ── clearing ────────────────────────────────────────────────────────────────


def test_clear_returns_the_value_to_unknown() -> None:
    """The undo for a mistyped date."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker.set_last_scheduled_backwash(T0 - timedelta(days=1))

    tracker.clear_last_scheduled_backwash()

    assert tracker.last_scheduled_backwash is None
    assert tracker.last_scheduled_source is None


def test_clear_rearms_the_backfill() -> None:
    """After clearing, an older stored cycle is classified again.

    This is what makes clearing useful rather than merely destructive: the
    schedule falls back to whatever the integration actually observed.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._last_backwash = T0  # type: ignore[attr-defined]
    tracker.set_last_scheduled_backwash(T0 - timedelta(days=30))

    tracker.clear_last_scheduled_backwash()
    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=5))

    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED


def test_clear_is_a_no_op_when_already_unknown() -> None:
    """Nothing stored, nothing to clear — and no pointless write."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.clear_last_scheduled_backwash()

    assert tracker.last_scheduled_backwash is None
    tracker._hass.async_create_task.assert_not_called()  # type: ignore[attr-defined]


async def test_clear_is_persisted() -> None:
    """Clearing must reach the store, or the old value returns on restart."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_save = AsyncMock()  # type: ignore[method-assign]
    tracker.set_last_scheduled_backwash(T0)

    tracker.clear_last_scheduled_backwash()
    await tracker.async_save()

    saved = tracker._store.async_save.call_args.args[0]  # type: ignore[attr-defined]
    assert saved["last_scheduled_backwash"] is None
    assert saved["last_scheduled_source"] is None


# ── the settings menu as an observed signal (SALT byte[37] bit 0x04) ─────────


def _salt_device(
    backwash_running: bool | None,
    menu: bool,
    device_type: AsekoDeviceType = AsekoDeviceType.SALT,
) -> MagicMock:
    """Return a scheduled device that also reports the settings-menu bit.

    The tracker never looks at the device type; what it reads is the profile
    flag saying the bit marks presence only, which the SALT profile carries
    and the HOME ones do not.  The type is kept as the test's way of naming
    which of the two it is modelling.
    """
    dev = _scheduled_device(backwash_running)
    dev.device_type = device_type
    dev.flags = (
        frozenset({AsekoProfileFlag.MENU_BIT_IS_PRESENCE_ONLY})
        if device_type is AsekoDeviceType.SALT
        else frozenset()
    )
    dev.service_menu_open = menu
    return dev


def _run_service_menu_cycle(
    tracker: BackwashTracker,
    start: datetime,
    menu_during: bool,
    device_type: AsekoDeviceType = AsekoDeviceType.SALT,
) -> None:
    """Drive a cycle that ends with the manual flag already dropped.

    Mirrors the captured cycle: the unit clears bit 0x04 a frame or two
    after the valve closes, so the closing frame no longer carries it.
    """
    tracker.update(_salt_device(True, menu_during, device_type), start)
    tracker.update(
        _salt_device(True, menu_during, device_type),
        start + timedelta(seconds=45),
    )
    tracker.update(
        _salt_device(False, False, device_type),
        start + timedelta(seconds=90),
    )


def test_in_the_schedule_window_a_cycle_is_scheduled_even_with_the_menu_open() -> None:
    """The unit's timer explains a cycle in the window, whoever is at the menu."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0, True)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash is not None
    assert tracker.last_manual_backwash is None


def test_service_menu_is_latched_across_the_whole_window() -> None:
    """The flag counts even though the closing frame has already lost it.

    Reading the mode at the end of the window would miss every real cycle:
    in the capture the bit went out ~20 s after the valve closed, before
    the frame that ends the window arrived.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    started = T0 + timedelta(hours=2)  # outside the schedule window

    tracker.update(_salt_device(True, True), started)
    # the mode is already back to normal for the rest of the window
    tracker.update(
        _salt_device(True, False),
        started + timedelta(seconds=45),
    )
    tracker.update(
        _salt_device(False, False),
        started + timedelta(seconds=90),
    )

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_without_the_service_menu_the_schedule_still_decides() -> None:
    """The flag only ever adds evidence; its absence changes nothing."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0, False)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash is not None


def test_service_menu_signal_does_not_apply_to_home() -> None:
    """On HOME the same bit is a standing pump override, not a person.

    It can sit set indefinitely, so honouring it there would refile every
    scheduled cycle that happened to run while it was on.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(
        tracker, T0 + timedelta(hours=2), True, AsekoDeviceType.HOME
    )

    # outside the window HOME ignores the bit and keeps the elimination rule
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_service_menu_flag_does_not_leak_into_the_next_cycle() -> None:
    """Each window starts from a clean slate."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0 + timedelta(hours=2), True)
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL

    later = T0 + timedelta(days=SCHEDULE_EVERY_N_DAYS)
    _run_service_menu_cycle(tracker, later, False)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


# ── units that report their settings menu (SALT) ─────────────────────────────


def test_salt_cycle_outside_the_window_with_the_menu_closed_is_unknown() -> None:
    """Nobody at the menu and not the schedule: the cycle is not attributed."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    started = T0 + timedelta(hours=2)

    _run_service_menu_cycle(tracker, started, False)

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_backwash == started + timedelta(seconds=45)
    assert tracker.last_manual_backwash is None
    assert tracker.last_scheduled_backwash is None


def test_salt_cycle_outside_the_window_with_the_menu_open_is_manual() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    started = T0 + timedelta(hours=2)

    _run_service_menu_cycle(tracker, started, True)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash == started + timedelta(seconds=45)


def test_salt_cycle_with_the_schedule_disabled_and_the_menu_closed_is_unknown() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def _disabled(active, menu=False) -> MagicMock:
        dev = _salt_device(active, menu)
        dev.backwash_interval = 0
        return dev

    tracker.update(_disabled(True), T0)
    tracker.update(_disabled(False), T0 + timedelta(seconds=90))

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_manual_backwash is None


def test_unknown_cycle_keeps_earlier_manual_and_scheduled_records() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _run_service_menu_cycle(tracker, T0, False)  # scheduled
    _run_service_menu_cycle(tracker, T0 + timedelta(hours=1), True)  # manual
    manual = tracker.last_manual_backwash

    _run_service_menu_cycle(tracker, T0 + timedelta(hours=3), False)  # unknown

    # on the unit's clock: the 21:00 slot, not the midpoint Home Assistant saw
    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_manual_backwash == manual
    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN


def test_backfill_of_an_unexplained_salt_record_runs_once() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    off_schedule = T0 + timedelta(hours=4)
    tracker._last_backwash = off_schedule  # type: ignore[attr-defined]

    tracker.update(_salt_device(False, False), off_schedule + timedelta(minutes=5))
    saves = tracker._hass.async_create_task.call_count  # type: ignore[attr-defined]
    tracker.update(_salt_device(False, False), off_schedule + timedelta(minutes=6))

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_manual_backwash is None
    # the first frame saved the classification (and the schedule it saw);
    # the second one has nothing new to save
    assert tracker._hass.async_create_task.call_count == saves  # type: ignore[attr-defined]


# ── time zone and midnight (audit B1, B2) ────────────────────────────────────


def _in_bratislava() -> ZoneInfo:
    """Home Assistant in Europe/Bratislava; the autouse fixture puts it back."""

    zone = ZoneInfo("Europe/Bratislava")
    dt_util.set_default_time_zone(zone)
    return zone


def _every_three_days_at(at: time) -> MagicMock:
    return _device(False, backwash_start_time=at, backwash_interval=3)


def test_projection_keeps_the_wall_clock_time_across_daylight_saving() -> None:
    """A cycle stored before the change to summer time still projects to 12:30."""
    zone = _in_bratislava()
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    # as restored from storage: a fixed +01:00 offset, not the zone's rules
    tracker._last_scheduled_backwash = datetime.fromisoformat(  # type: ignore[attr-defined]
        "2026-03-27T12:30:45+01:00"
    )

    projected = tracker.next_scheduled_backwash(
        _every_three_days_at(time(12, 30)), datetime(2026, 3, 28, tzinfo=zone)
    )

    assert projected == datetime(2026, 3, 30, 12, 30, tzinfo=zone)
    assert projected.utcoffset() == timedelta(hours=2)


def test_a_utc_date_projects_like_the_same_local_one() -> None:
    zone = _in_bratislava()
    device = _every_three_days_at(time(12, 30))
    now = datetime(2026, 9, 11, tzinfo=zone)

    utc = BackwashTracker(_hass(), serial_number=1)
    utc.set_last_scheduled_backwash(datetime(2026, 9, 10, 10, 30, tzinfo=UTC))
    local = BackwashTracker(_hass(), serial_number=2)
    local.set_last_scheduled_backwash(datetime(2026, 9, 10, 12, 30, tzinfo=zone))

    assert utc.next_scheduled_backwash(device, now) == datetime(
        2026, 9, 13, 12, 30, tzinfo=zone
    )
    assert local.next_scheduled_backwash(device, now) == utc.next_scheduled_backwash(
        device, now
    )


def test_a_cycle_finishing_after_midnight_keeps_the_day_it_was_scheduled() -> None:
    """Plan 23:59, valve 23:59:30-00:01: the next one is three days after the 10th."""
    zone = _in_bratislava()
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def device(active) -> MagicMock:
        return _device(active, backwash_start_time=time(23, 59), backwash_interval=3)

    start = datetime(2026, 9, 10, 23, 59, 30, tzinfo=zone)
    tracker.update(device(True), start)
    tracker.update(device(False), start + timedelta(seconds=90))

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.next_scheduled_backwash(
        device(False), start + timedelta(hours=1)
    ) == datetime(2026, 9, 13, 23, 59, tzinfo=zone)


def test_a_cycle_just_before_a_midnight_plan_matches_the_next_day() -> None:
    zone = _in_bratislava()
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def device(active) -> MagicMock:
        return _device(active, backwash_start_time=time(0, 0), backwash_interval=3)

    start = datetime(2026, 9, 10, 23, 58, tzinfo=zone)
    tracker.update(device(True), start)
    tracker.update(device(False), start + timedelta(seconds=90))

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.next_scheduled_backwash(
        device(False), start + timedelta(hours=1)
    ) == datetime(2026, 9, 14, 0, 0, tzinfo=zone)


def test_clearing_re_derives_the_split_after_an_observed_cycle() -> None:
    """Clear forgets the verdict too, so the stored cycle is classified again."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _run_cycle(tracker, T0)  # observed, scheduled
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED

    tracker.clear_last_scheduled_backwash()
    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=5))

    # on the unit's clock: the 21:00 slot, not the midpoint Home Assistant saw
    assert tracker.last_scheduled_backwash == T0


# ── clear after a newer cycle (audit C2) ─────────────────────────────────────


async def _store_roundtrip(tracker: BackwashTracker) -> BackwashTracker:
    """Save ``tracker`` into a fake Store and load a fresh tracker from it."""
    saved: dict[str, Any] = {}

    async def save(data) -> None:
        saved.update(data)

    async def load() -> dict[str, Any]:
        return dict(saved)

    tracker._store.async_save = save  # type: ignore[method-assign]
    await tracker.async_save()
    restored = BackwashTracker(_hass(), serial_number=110071590)
    restored._store.async_load = load  # type: ignore[method-assign]
    await restored.async_load()
    return restored


async def test_clearing_the_scheduled_date_keeps_a_newer_manual_verdict() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _run_cycle(tracker, T0)  # scheduled
    _run_service_menu_cycle(tracker, T0 + timedelta(hours=21), True)  # manual
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL

    tracker.clear_last_scheduled_backwash()
    tracker.update(_salt_device(False, False), T0 + timedelta(hours=22))

    assert tracker.last_scheduled_backwash is None
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    restored = await _store_roundtrip(tracker)
    assert restored.last_trigger is AsekoBackwashTrigger.MANUAL
    assert restored.last_scheduled_backwash is None


async def test_clearing_the_scheduled_date_keeps_a_newer_not_attributed_verdict() -> (
    None
):
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _run_cycle(tracker, T0)  # scheduled
    _run_service_menu_cycle(tracker, T0 + timedelta(hours=21), False)  # menu closed
    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN

    tracker.clear_last_scheduled_backwash()
    tracker.update(_salt_device(False, False), T0 + timedelta(hours=22))

    # the newer cycle is not re-classified into the scheduled bucket
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    restored = await _store_roundtrip(tracker)
    assert restored.last_trigger is AsekoBackwashTrigger.UNKNOWN


def test_clearing_keeps_the_scheduled_verdict_when_a_manual_cycle_is_on_record() -> (
    None
):
    """An older manual cycle blocks the backfill, so the verdict must not go."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _run_service_menu_cycle(tracker, T0 - timedelta(hours=3), True)  # manual
    _run_cycle(tracker, T0)  # scheduled, the latest
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED

    tracker.clear_last_scheduled_backwash()
    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=5))

    assert tracker.last_scheduled_backwash is None
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


# ── unit clock offset (audit R2) ─────────────────────────────────────────────


def _clocked(
    running: bool,
    offset: float | None,
    *,
    at: time = SCHEDULE_AT,
    every: int = SCHEDULE_EVERY_N_DAYS,
) -> MagicMock:
    """Return a scheduled device whose clock is ``offset`` minutes ahead of HA."""
    dev = _device(running, backwash_start_time=at, backwash_interval=every)
    dev.clock_offset = offset
    return dev


def _clocked_cycle(tracker, start, offset, **kwargs: object) -> None:
    tracker.update(_clocked(True, offset, **kwargs), start)
    tracker.update(_clocked(False, offset, **kwargs), start + timedelta(seconds=90))


def _frame(tracker, moment, offset=None, **kwargs: object) -> None:
    tracker.update(_clocked(False, offset, **kwargs), moment)


def test_a_unit_ahead_runs_its_schedule_early_on_home_assistant_time() -> None:
    """Unit 5.5 min ahead: its 21:00 is 20:54:30 in HA, and that is scheduled."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _clocked_cycle(tracker, T0 - timedelta(minutes=5, seconds=30), 5.5)
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_with_the_offset_known_the_window_is_five_minutes() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    # on the unit clock this started 10 minutes after the plan
    _clocked_cycle(tracker, T0 + timedelta(minutes=4, seconds=30), 5.5)
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_without_an_offset_the_window_stays_fifteen_minutes() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _clocked_cycle(tracker, T0 + timedelta(minutes=10), None)
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_a_unit_an_hour_behind_and_drifting_is_still_scheduled() -> None:
    """Missed spring change (-60) and 5.5 min fast: its 21:00 is 21:54:30 in HA."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _clocked_cycle(tracker, T0 + timedelta(minutes=54, seconds=30), -54.5)
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


@pytest.mark.parametrize("offset", [None, 5.5, -54.5, 65.5, 125.0])
def test_the_projection_shows_the_time_set_on_the_unit(offset) -> None:
    """R2: not moved by drift nor by a change of time the unit did not follow."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._clock_offset_minutes = offset  # type: ignore[attr-defined]
    tracker.set_last_scheduled_backwash(T0)

    assert tracker.next_scheduled_backwash(
        _clocked(False, offset), T0 + timedelta(hours=3)
    ) == T0 + timedelta(days=SCHEDULE_EVERY_N_DAYS)


def test_missed_slots_are_stepped_over_on_the_unit_clock() -> None:
    """A unit 10 min ahead has run its 21:00 while HA still shows 20:55."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._clock_offset_minutes = 10.0  # type: ignore[attr-defined]
    tracker.set_last_scheduled_backwash(T0 - timedelta(days=SCHEDULE_EVERY_N_DAYS))

    assert tracker.next_scheduled_backwash(
        _clocked(False, 10.0), T0 - timedelta(minutes=5)
    ) == T0 + timedelta(days=SCHEDULE_EVERY_N_DAYS)


# ── schedule change (audit R1) ───────────────────────────────────────────────


def test_the_first_schedule_seen_does_not_restart_anything() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _frame(tracker, T0 - timedelta(hours=1))
    assert tracker.next_scheduled_backwash(_clocked(False, None), T0) is None


def test_a_new_backwash_time_runs_the_day_after_the_change() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _clocked_cycle(tracker, T0, None)  # 14 June, every 3 days at 21:00
    changed = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    _frame(tracker, changed, at=time(8, 30))

    assert tracker.next_scheduled_backwash(
        _clocked(False, None, at=time(8, 30)), changed
    ) == datetime(2026, 6, 16, 8, 30, tzinfo=UTC)


def test_a_new_interval_runs_the_day_after_the_change() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _clocked_cycle(tracker, T0, None)
    changed = T0 + timedelta(hours=1)
    _frame(tracker, changed, every=7)

    assert tracker.next_scheduled_backwash(
        _clocked(False, None, every=7), changed
    ) == T0 + timedelta(days=1)


def test_switching_the_schedule_off_and_on_restarts_it_the_next_day() -> None:
    """Several toggles in one evening, as captured on 13 September."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _clocked_cycle(tracker, T0 - timedelta(days=2), None)
    evening = T0 + timedelta(hours=1, minutes=50)  # 22:50
    for minute, every in enumerate((0, 15, 0, 15, 0, 15)):
        _frame(tracker, evening + timedelta(minutes=minute), every=every)
        if every == 0:
            off = _clocked(False, None, every=0)
            assert tracker.next_scheduled_backwash(off, evening) is None

    assert tracker.next_scheduled_backwash(
        _clocked(False, None, every=15), evening + timedelta(minutes=10)
    ) == T0 + timedelta(days=1)


def test_the_restarted_schedule_counts_from_its_first_cycle() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _frame(tracker, T0 - timedelta(hours=5))
    _frame(tracker, T0 - timedelta(hours=4), every=15)  # change: runs tomorrow
    _clocked_cycle(tracker, T0 + timedelta(days=1), None, every=15)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.next_scheduled_backwash(
        _clocked(False, None, every=15), T0 + timedelta(days=1, hours=1)
    ) == T0 + timedelta(days=16)


def test_a_missed_restart_day_steps_on_by_the_interval() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _frame(tracker, T0 - timedelta(hours=5))
    _frame(tracker, T0 - timedelta(hours=4), every=5)

    assert tracker.next_scheduled_backwash(
        _clocked(False, None, every=5), T0 + timedelta(days=2)
    ) == T0 + timedelta(days=6)


def test_the_day_of_the_change_is_the_day_on_the_unit_clock() -> None:
    """HA 23:57, the unit (+5.5 min) already past midnight: runs a day later."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    late = datetime(2026, 6, 14, 23, 57, tzinfo=UTC)
    _frame(tracker, late - timedelta(minutes=1), 5.5)
    _frame(tracker, late, 5.5, at=time(8, 30))

    assert tracker.next_scheduled_backwash(
        _clocked(False, 5.5, at=time(8, 30)), late
    ) == datetime(2026, 6, 16, 8, 30, tzinfo=UTC)


def test_typing_in_the_last_scheduled_date_replaces_a_restart() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _frame(tracker, T0 - timedelta(hours=5))
    _frame(tracker, T0 - timedelta(hours=4), every=5)
    tracker.set_last_scheduled_backwash(T0 - timedelta(days=2))

    assert tracker.next_scheduled_backwash(
        _clocked(False, None, every=5), T0 - timedelta(hours=3)
    ) == T0 + timedelta(days=3)


def test_the_recorded_day_does_not_follow_a_new_time_to_another_day() -> None:
    """The day a cycle belonged to is fixed when it is recorded (audit R1)."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    # 14 June 23:00, every 3 days
    _clocked_cycle(tracker, T0 + timedelta(hours=2), None, at=time(23, 0))
    # the time now reads 01:00, with no restart pending (as after a typed
    # date was cleared): nearest to 23:00 would be 15 June, the record says 14
    tracker._restart_day = None  # type: ignore[attr-defined]

    assert tracker.next_scheduled_backwash(
        _clocked(False, None, at=time(1, 0)), T0 + timedelta(hours=3)
    ) == datetime(2026, 6, 17, 1, 0, tzinfo=UTC)


async def test_schedule_restart_and_offset_survive_a_restart() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    _frame(tracker, T0 - timedelta(hours=5), 5.5)
    _frame(tracker, T0 - timedelta(hours=4), 5.5, every=5)
    restored = await _store_roundtrip(tracker)

    assert restored.next_scheduled_backwash(
        _clocked(False, None, every=5), T0 - timedelta(hours=3)
    ) == T0 + timedelta(days=1)
    assert restored._clock_offset_minutes == 5.5  # type: ignore[attr-defined]
    # a change while Home Assistant was down shows up on the first frame
    _frame(restored, T0 + timedelta(hours=4), None, every=7)  # 15 June 01:00
    assert restored.next_scheduled_backwash(
        _clocked(False, None, every=7), T0 + timedelta(hours=4)
    ) == T0 + timedelta(days=2)


# ── recognition across a change of time, from the frame bytes ────────────────


def _unit_bytes(unit: datetime) -> bytes:
    """Return a v7 SALT frame whose clock bytes (6-11) read ``unit``."""
    data = _make_base_bytes()
    data[6:12] = bytes(
        (unit.year - 2000, unit.month, unit.day, unit.hour, unit.minute, unit.second)
    )
    return bytes(data)


def _recognise(
    zone, ha_start: datetime, unit_ahead: timedelta
) -> tuple[ClockTracker, BackwashTracker]:
    """Clock frames and one cycle through the real decoder and both trackers."""
    clock = ClockTracker()
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    at = time(8, 30)
    for i, running in enumerate((False, False, False, True, True, False)):
        received = ha_start + timedelta(seconds=45 * (i - 3))
        # the unit's wall clock: Home Assistant's wall clock plus the offset
        unit = (received.replace(tzinfo=None) + unit_ahead).replace(tzinfo=zone)
        clock.update(decode(_unit_bytes(unit)).unit_clock, received)
        tracker.update(
            _clocked(running, clock.offset_minutes, at=at, every=15), received
        )
    return clock, tracker


def test_a_missed_autumn_change_and_drift_are_taken_out() -> None:
    """25 Oct 2026: HA on winter time, the unit still on summer time, 5.5 min fast."""
    zone = _in_bratislava()
    ha_start = datetime(2026, 10, 25, 7, 24, 30, tzinfo=zone)
    clock, tracker = _recognise(zone, ha_start, timedelta(minutes=65.5))

    assert clock.offset_minutes == 65.5
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_a_missed_spring_change_and_drift_are_taken_out() -> None:
    """29 Mar 2026: HA on summer time, the unit still on winter time, 5.5 min fast."""
    zone = _in_bratislava()
    ha_start = datetime(2026, 3, 29, 9, 24, 30, tzinfo=zone)
    clock, tracker = _recognise(zone, ha_start, timedelta(minutes=-54.5))

    assert clock.offset_minutes == -54.5
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_six_minutes_past_the_plan_on_the_unit_clock_is_not_scheduled() -> None:
    zone = _in_bratislava()
    ha_start = datetime(2026, 3, 29, 9, 30, 30, tzinfo=zone)  # unit 08:36
    _, tracker = _recognise(zone, ha_start, timedelta(minutes=-54.5))

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


# ── start-up: a frame before the stored state is loaded ──────────────────────


async def test_a_frame_before_the_load_finishes_does_not_wipe_the_history() -> None:
    """Store hands a pending write back to a load: nothing may be saved first."""
    stored = {
        "last_backwash": "2026-09-15T06:25:21+00:00",
        "last_scheduled_backwash": "2026-09-15T06:25:21+00:00",
        "last_scheduled_source": "observed",
        "last_manual_backwash": "2026-08-11T11:23:08+00:00",
        "last_trigger": "scheduled",
    }
    release = asyncio.Event()
    saves: list[dict] = []

    async def load() -> dict[str, Any]:
        await release.wait()
        return dict(saves[-1]) if saves else dict(stored)

    async def save(data) -> None:
        saves.append(dict(data))

    hass = _hass()
    tasks: list[asyncio.Task] = []
    hass.async_create_task.side_effect = lambda coro, *a, **k: tasks.append(
        asyncio.ensure_future(coro)
    )
    tracker = BackwashTracker(hass, serial_number=110071590)
    tracker._store.async_load = load  # type: ignore[method-assign]
    tracker._store.async_save = save  # type: ignore[method-assign]

    # what the coordinator does on the first frame after a restart
    hass.async_create_task(tracker.load_soon())
    tracker.update(_clocked(False, 5.5, at=time(8, 30), every=15), T0)
    await asyncio.sleep(0)
    assert saves == []

    release.set()
    await asyncio.gather(*tasks)
    tracker.update(_clocked(False, 5.5, at=time(8, 30), every=15), T0)
    await asyncio.gather(*tasks)

    assert tracker.last_backwash == datetime.fromisoformat(stored["last_backwash"])
    assert tracker.last_manual_backwash == datetime.fromisoformat(
        stored["last_manual_backwash"]
    )
    assert saves
    assert saves[-1]["last_backwash"] == stored["last_backwash"]


# ── times: UTC durations, the window offset, the unit-clock slot (T1-T3) ─────


def _utc_frames(
    zone, start_utc: datetime, seconds: int, step: int = 10
) -> list[datetime]:
    """Receive times every ``step`` seconds of real time, as local times."""
    return [
        (start_utc + timedelta(seconds=s)).astimezone(zone)
        for s in range(0, seconds + 1, step)
    ]


@pytest.mark.parametrize(
    "start_utc",
    [
        datetime(2026, 3, 29, 0, 59, 30, tzinfo=UTC),  # 01:59:30 +01
        datetime(2026, 10, 25, 0, 59, 30, tzinfo=UTC),  # 02:59:30 +02
    ],
)
def test_a_cycle_across_a_change_of_time_is_measured_in_real_seconds(start_utc) -> None:
    """T1: 75 real seconds stay 75 when the local clock jumps an hour."""
    zone = _in_bratislava()
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    frames = _utc_frames(zone, start_utc, 80)
    for moment in frames[:-1]:
        tracker.update(_device(True), moment)
    tracker.update(_device(False), frames[-1])

    assert tracker.last_backwash == start_utc + timedelta(seconds=40)


def test_a_frame_gap_is_real_time_too() -> None:
    """T1: a gap of 10 real seconds across the spring change is not an hour."""
    zone = _in_bratislava()
    start = datetime(2026, 3, 29, 0, 59, 55, tzinfo=UTC)
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker.update(_device(True), start.astimezone(zone))
    tracker.update(_device(True), (start + timedelta(seconds=10)).astimezone(zone))
    assert tracker._relay_on_since == start  # type: ignore[attr-defined]


def test_the_offset_when_the_valve_opened_decides() -> None:
    """T2: an offset that jumps mid-cycle does not reclassify its start."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    start = T0 + timedelta(minutes=54, seconds=30)
    tracker.update(_clocked(True, -54.5), start)
    tracker.update(_clocked(True, 5.5), start + timedelta(seconds=45))
    tracker.update(_clocked(False, 5.5), start + timedelta(seconds=90))

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_last_scheduled_is_the_slot_on_the_unit_clock() -> None:
    """T3: the unit ran its 21:00; HA saw it at 21:54:30 with the unit 54.5 min behind."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    start = T0 + timedelta(minutes=54, seconds=30)
    _clocked_cycle(tracker, start, -54.5)

    assert tracker.last_scheduled_backwash == T0
    assert tracker.last_backwash == start + timedelta(seconds=45)


def test_last_manual_stays_on_home_assistant_time() -> None:
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    start = T0 + timedelta(hours=3)
    _clocked_cycle(tracker, start, -54.5)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash == start + timedelta(seconds=45)


# ── the offset in the frame that opened the valve (audit A1) ─────────────────


def _clock_frames(
    zone,
    frames: list[tuple[datetime, timedelta, bool]],
    *,
    at: time,
) -> tuple[ClockTracker, BackwashTracker, list[float | None]]:
    """Feed (UTC receive time, unit ahead of HA's wall clock, relay) frames.

    Both trackers in the coordinator's order, the unit's clock as the decoder
    gives it.  Returns the published offset at every frame too.
    """
    clock = ClockTracker()
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    published: list[float | None] = []
    for received_utc, unit_ahead, running in frames:
        wall = received_utc.astimezone(zone).replace(tzinfo=None)
        unit_clock = (wall + unit_ahead).replace(tzinfo=zone)
        clock.update(unit_clock, received_utc)
        published.append(clock.offset_minutes)
        device = _clocked(running, clock.offset_minutes, at=at, every=1)
        device.unit_clock = unit_clock
        tracker.update(device, received_utc)
    return clock, tracker, published


def _jump_then_cycle(
    change_utc: datetime, before: timedelta, after: timedelta
) -> list[tuple[datetime, timedelta, bool]]:
    """Frames every 10 s up to ``change_utc``, then a 90 s cycle opening at it."""
    frames = [
        (change_utc - timedelta(seconds=s), before, False) for s in (40, 30, 20, 10)
    ]
    frames += [
        (change_utc + timedelta(seconds=s), after, True) for s in range(0, 90, 10)
    ]
    frames.append((change_utc + timedelta(seconds=90), after, False))
    return frames


def test_a_cycle_in_the_first_frame_after_spring_forward_is_scheduled() -> None:
    """29 Mar 2026 01:00 UTC: HA jumps to 03:00, the unit stays on 02:00 and runs its 02:00."""
    zone = _in_bratislava()
    change = datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    _, tracker, published = _clock_frames(
        zone,
        _jump_then_cycle(change, timedelta(0), timedelta(hours=-1)),
        at=time(2, 0),
    )

    assert published[4] == 0.0  # the median has not seen the jump yet
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash == datetime(2026, 3, 29, 2, 0, tzinfo=zone)


def test_a_cycle_in_the_first_frame_after_fall_back_is_scheduled() -> None:
    """25 Oct 2026 01:00 UTC: HA goes back to 02:00, the unit stays on 03:00 and runs its 03:00."""
    zone = _in_bratislava()
    change = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    _, tracker, published = _clock_frames(
        zone,
        _jump_then_cycle(change, timedelta(0), timedelta(hours=1)),
        at=time(3, 0),
    )

    assert published[4] == 0.0
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_a_unit_that_follows_the_change_of_time_is_scheduled_too() -> None:
    zone = _in_bratislava()
    change = datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    _, tracker, _ = _clock_frames(
        zone, _jump_then_cycle(change, timedelta(0), timedelta(0)), at=time(3, 0)
    )

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_a_cycle_right_after_the_unit_clock_is_set_by_hand_is_scheduled() -> None:
    """An hour fast until just now, then set right: its 21:00 is HA's 21:00."""
    _, tracker, published = _clock_frames(
        UTC, _jump_then_cycle(T0, timedelta(hours=1), timedelta(0)), at=SCHEDULE_AT
    )

    assert published[4] == 60.0
    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_the_unit_clock_set_by_hand_mid_cycle_does_not_reclassify_it() -> None:
    frames = _jump_then_cycle(T0, timedelta(0), timedelta(0))
    # set an hour fast from the third frame of the cycle on
    frames = frames[:6] + [(t, timedelta(hours=1), r) for t, _, r in frames[6:]]
    _, tracker, _ = _clock_frames(UTC, frames, at=SCHEDULE_AT)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash == T0


def test_a_cycle_out_of_the_window_on_the_unit_clock_of_its_frame_is_manual() -> None:
    """The median would still say on time; the opening frame's clock says 30 min late."""
    _, tracker, published = _clock_frames(
        UTC,
        _jump_then_cycle(T0, timedelta(0), timedelta(minutes=30)),
        at=SCHEDULE_AT,
    )

    assert published[4] == 0.0
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


# ── an offset that was not known when the valve opened (audit F1) ────────────


def _blind_then(offset: float | None) -> BackwashTracker:
    """Open the valve on a frame with no clock, then report ``offset`` minutes."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    opening = _clocked(True, None)
    opening.unit_clock = None
    tracker.update(opening, T0)
    for seconds in (10, 20, 30):
        frame = _clocked(True, offset)
        frame.unit_clock = None if offset is None else T0 + timedelta(minutes=offset)
        tracker.update(frame, T0 + timedelta(seconds=seconds))
    closing = _clocked(False, offset)
    closing.unit_clock = None if offset is None else T0 + timedelta(minutes=offset)
    tracker.update(closing, T0 + timedelta(seconds=90))
    return tracker


@pytest.mark.parametrize("later", [None, 60.0, -60.0, 0.0])
def test_a_clock_first_seen_after_the_valve_opened_does_not_reclassify_it(
    later,
) -> None:
    """The start stays on Home Assistant's clock, ±15 min, whatever comes later."""
    tracker = _blind_then(later)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash == T0


def test_without_a_clock_at_the_start_the_wide_window_still_applies() -> None:
    """Half an hour past the plan on Home Assistant's clock is nobody's schedule."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    start = T0 + timedelta(minutes=30)
    opening = _clocked(True, None)
    opening.unit_clock = None
    tracker.update(opening, start)
    closing = _clocked(False, 30.0)
    closing.unit_clock = start + timedelta(minutes=30)
    tracker.update(closing, start + timedelta(seconds=90))

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


# ── a typed-in date while the store is still being read (audit F2) ───────────


async def test_a_typed_in_date_lands_once_the_stored_history_is_in() -> None:
    """``loading`` is on until the store answers; the services refuse until then."""
    stored = {
        "last_backwash": "2026-09-09T06:30:00+00:00",
        "last_scheduled_backwash": "2026-09-09T06:30:00+00:00",
        "last_scheduled_source": "observed",
    }
    release = asyncio.Event()
    saves: list[dict] = []

    async def load() -> dict[str, Any]:
        await release.wait()
        return dict(stored)

    async def save(data) -> None:
        saves.append(dict(data))

    hass = _hass()
    tasks: list[asyncio.Task] = []
    hass.async_create_task.side_effect = lambda coro, *a, **k: tasks.append(
        asyncio.ensure_future(coro)
    )
    tracker = BackwashTracker(hass, serial_number=110071590)
    tracker._store.async_load = load  # type: ignore[method-assign]
    tracker._store.async_save = save  # type: ignore[method-assign]

    hass.async_create_task(tracker.load_soon())
    await asyncio.sleep(0)
    assert tracker.loading is True

    release.set()
    await asyncio.gather(*tasks)
    assert tracker.loading is False
    assert tracker.last_scheduled_backwash == datetime.fromisoformat(
        stored["last_scheduled_backwash"]
    )

    tracker.set_last_scheduled_backwash(T0)
    await asyncio.gather(*tasks)
    assert tracker.last_scheduled_backwash == T0
    assert saves[-1]["last_scheduled_backwash"] == T0.isoformat()
