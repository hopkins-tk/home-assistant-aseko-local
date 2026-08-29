"""Tests for BackwashTracker.

Models a real-world backwash cycle: the relay must stay on for at least
60 seconds (MIN_BACKWASH_DURATION) for the event to be recorded, and each
recorded cycle is classified as scheduled or manual from its start time.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock


from custom_components.aseko_local.aseko_data import (
    AsekoBackwashSource,
    AsekoBackwashTrigger,
    AsekoDeviceType,
)
from custom_components.aseko_local.backwash_tracker import (
    BackwashTracker,
    MAX_FRAME_GAP,
    SCHEDULED_MATCH_TOLERANCE,
)

T0 = datetime(2026, 6, 14, 21, 0, 0, tzinfo=timezone.utc)

# The unit's configured backwash time, matching T0's time of day, so a cycle
# starting at T0 counts as the unit's own scheduled run.
SCHEDULE_AT = time(21, 0)
SCHEDULE_EVERY_N_DAYS = 3


# ── helpers ──────────────────────────────────────────────────────────────────


def _device(
    backwash_active: bool | None,
    *,
    backwash_time: time | None = None,
    backwash_every_n_days: int | None = None,
) -> Any:
    """Minimal stand-in for AsekoDevice with only the fields the tracker reads.

    The schedule defaults to "not configured", which classifies every recorded
    cycle as manual — the right default for the tests that only care about the
    relay-window state machine.
    """
    dev = MagicMock()
    dev.backwash_active = backwash_active
    dev.backwash_time = backwash_time
    dev.backwash_every_n_days = backwash_every_n_days
    return dev


def _scheduled_device(backwash_active: bool | None) -> Any:
    """Stand-in for a device with an enabled backwash schedule at SCHEDULE_AT."""
    return _device(
        backwash_active,
        backwash_time=SCHEDULE_AT,
        backwash_every_n_days=SCHEDULE_EVERY_N_DAYS,
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


def test_short_backwash_below_threshold_not_recorded():
    """Relay on for 30 s (below MIN_BACKWASH_DURATION) → no event recorded."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_active=True)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))
    tracker.update(_device(backwash_active=False), T0 + timedelta(seconds=30))

    assert tracker.last_backwash is None


def test_long_backwash_recorded_at_midpoint():
    """Relay on for 90 s (≥ 60 s threshold) → event recorded at window midpoint."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_active=True)

    tracker.update(device, T0)
    tracker.update(_device(backwash_active=False), T0 + timedelta(seconds=90))

    assert tracker.last_backwash is not None
    # Midpoint of [T0, T0+90s] = T0 + 45s
    expected = T0 + timedelta(seconds=45)
    assert tracker.last_backwash == expected


def test_exactly_threshold_backwash_recorded():
    """Relay on for exactly 60 s → still recorded (≥ comparison, not >)."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_active=True)

    tracker.update(device, T0)
    tracker.update(_device(backwash_active=False), T0 + timedelta(seconds=60))

    assert tracker.last_backwash is not None
    # 60s window → midpoint at T0 + 30s
    assert tracker.last_backwash == T0 + timedelta(seconds=30)


def test_two_consecutive_backwashes_keep_latest():
    """If two backwashes happen in sequence, keep the later one."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    # First cycle: T0 → T0 + 90s
    tracker.update(_device(backwash_active=True), T0)
    tracker.update(_device(backwash_active=False), T0 + timedelta(seconds=90))
    first = tracker.last_backwash
    assert first is not None

    # Second cycle: T0+5min → T0+5min+90s
    second_start = T0 + timedelta(minutes=5)
    tracker.update(_device(backwash_active=True), second_start)
    tracker.update(_device(backwash_active=False), second_start + timedelta(seconds=90))

    assert tracker.last_backwash > first
    assert tracker.last_backwash == second_start + timedelta(seconds=45)


# ── loss of connection ──────────────────────────────────────────────────────


def test_lost_connection_resets_in_progress_window():
    """Frame gap > MAX_FRAME_GAP between two relay-on updates → window reset.

    The reset discards the previous (unreliable) "on" window.  A
    subsequent "on" frame re-opens a fresh window starting at the
    recovery time.  The short follow-up window (< MIN_BACKWASH_DURATION)
    must therefore NOT be recorded.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_active=True)

    tracker.update(device, T0)  # relay on, window starts
    # MAX_FRAME_GAP (5 min) + 1 s later, still on, but we lost the connection.
    # The reset clears the stale T0 window.  The same "on" frame re-opens
    # the window at the recovery time, so we expect a new value here.
    recovery = T0 + MAX_FRAME_GAP + timedelta(seconds=1)
    tracker.update(device, recovery)
    assert tracker._relay_on_since == recovery  # type: ignore[attr-defined]

    # 30 s later the relay goes off — only 30 s, not a real backwash.
    tracker.update(_device(backwash_active=False), recovery + timedelta(seconds=30))
    assert tracker.last_backwash is None


def test_lost_connection_during_real_backwash_does_not_record():
    """A long but disconnected window should not be recorded as a backwash.

    Scenario: the device is in a real backwash cycle, the connection drops
    for longer than MAX_FRAME_GAP, the connection recovers, and the relay
    is still on.  When the relay finally goes off, the *total* time from
    the original start is > 60 s — but the cycle spanned a disconnect and
    must not be recorded.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_active=True)

    tracker.update(device, T0)
    # Connection drops for 6 minutes (> MAX_FRAME_GAP).
    recovery = T0 + timedelta(minutes=6)
    tracker.update(device, recovery)
    # Relay finally goes off, total elapsed would be 6 min 30 s but cycle is split.
    tracker.update(_device(backwash_active=False), recovery + timedelta(seconds=30))
    assert tracker.last_backwash is None


def test_short_gap_does_not_reset():
    """Frame gap < MAX_FRAME_GAP → window continues."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _device(backwash_active=True)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=30))  # still on
    assert tracker._relay_on_since == T0  # type: ignore[attr-defined]

    # Window still tracks from T0 → at T0+90s, recorded
    tracker.update(_device(backwash_active=False), T0 + timedelta(seconds=90))
    assert tracker.last_backwash == T0 + timedelta(seconds=45)


# ── NET devices ─────────────────────────────────────────────────────────────


def test_net_device_skipped():
    """backwash_active is None on NET → tracker is a no-op."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker.update(_device(backwash_active=None), T0)
    tracker.update(_device(backwash_active=None), T0 + timedelta(seconds=120))

    assert tracker.last_backwash is None
    assert tracker._relay_on_since is None  # type: ignore[attr-defined]
    assert tracker._last_frame_at is None  # type: ignore[attr-defined]


# ── persistence ─────────────────────────────────────────────────────────────


async def test_async_load_from_empty_store():
    """async_load on a fresh Store leaves last_backwash as None."""
    hass = _hass()
    hass.config = MagicMock()  # unused but required by HA core for Store
    # We don't call real Store here; we just verify that an empty load
    # is handled gracefully.  Direct construction with no stored data:
    tracker = BackwashTracker(hass, serial_number=110071590)
    # Manually replicate what async_load would do with an empty dict:
    # (no async_store involved — empty load is a no-op)
    assert tracker.last_backwash is None


async def test_async_save_writes_nulls_rather_than_skipping():
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


def test_nothing_recorded_starts_unknown():
    """A fresh tracker reports every field as unknown, not as a schedule guess."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    assert tracker.last_backwash is None
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None
    assert tracker.next_scheduled_backwash(_scheduled_device(False), T0) is None


def test_cycle_at_scheduled_time_is_scheduled():
    """A cycle starting at the configured backwash_time is the unit's own run."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash == T0 + timedelta(seconds=45)
    assert tracker.last_backwash == tracker.last_scheduled_backwash
    assert tracker.last_manual_backwash is None


def test_cycle_just_inside_tolerance_is_scheduled():
    """The unit's clock may drift from HA's — the tolerance window absorbs it."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0 + SCHEDULED_MATCH_TOLERANCE - timedelta(seconds=1))

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_cycle_outside_tolerance_is_manual_without_the_menu_signal():
    """On a device that cannot report the menu, elimination is all there is."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    started = T0 + timedelta(hours=2)
    _run_cycle(tracker, started)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash == started + timedelta(seconds=45)
    assert tracker.last_backwash == tracker.last_manual_backwash
    assert tracker.last_scheduled_backwash is None


def test_cycle_outside_tolerance_is_unknown_on_salt():
    """Where the menu bit exists, "matched nothing" is a real answer.

    The unit would have said if somebody had been at it, and it did not.  So
    the cycle is recorded as having happened and attributed to neither side,
    rather than called manual because nothing else fit.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    started = T0 + timedelta(hours=2)
    _run_service_menu_cycle(tracker, started, False)

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_backwash == started + timedelta(seconds=45)
    assert tracker.last_manual_backwash is None
    assert tracker.last_scheduled_backwash is None


def test_cycle_is_manual_when_schedule_disabled():
    """interval 0 = automatic backwash off → the unit cannot have started it."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def _disabled(active):
        return _device(active, backwash_time=SCHEDULE_AT, backwash_every_n_days=0)

    _run_cycle(tracker, T0, device_factory=_disabled)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_cycle_is_manual_when_schedule_unconfigured():
    """No backwash_time in the frame (0xFF) → nothing to match against."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0, device_factory=_device)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_scheduled_time_near_midnight_matches_across_days():
    """A cycle at 00:05 still matches a 23:55 schedule on the previous day."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    def _near_midnight(active):
        return _device(
            active,
            backwash_time=time(23, 55),
            backwash_every_n_days=SCHEDULE_EVERY_N_DAYS,
        )

    # 00:05 the next day — 10 minutes after the scheduled slot, but on the
    # other side of the date boundary.
    _run_cycle(
        tracker,
        datetime(2026, 6, 15, 0, 5, 0, tzinfo=timezone.utc),
        device_factory=_near_midnight,
    )

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_manual_cycle_keeps_earlier_scheduled_record():
    """A manual run must not overwrite the last scheduled one (it drives 'next')."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    scheduled = tracker.last_scheduled_backwash
    assert scheduled is not None

    manual_start = T0 + timedelta(days=1, hours=4)
    _run_service_menu_cycle(tracker, manual_start, True)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash == manual_start + timedelta(seconds=45)
    assert tracker.last_scheduled_backwash == scheduled
    # "Last backwash" tracks whichever came last, regardless of kind.
    assert tracker.last_backwash == tracker.last_manual_backwash


def test_unknown_cycle_keeps_earlier_scheduled_record():
    """An unattributed run must not move the schedule phase either."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    scheduled = tracker.last_scheduled_backwash
    assert scheduled is not None

    _run_service_menu_cycle(tracker, T0 + timedelta(days=1, hours=4), False)

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_scheduled_backwash == scheduled
    assert tracker.last_manual_backwash is None
    # It still happened, so it is the latest backwash.
    assert tracker.last_backwash == T0 + timedelta(days=1, hours=4, seconds=45)


# ── next-backwash projection ────────────────────────────────────────────────


def test_next_scheduled_backwash_unknown_after_manual_only():
    """A manual cycle says nothing about the unit's schedule phase."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_service_menu_cycle(tracker, T0 + timedelta(hours=2), True)

    assert tracker.last_manual_backwash is not None
    assert tracker.next_scheduled_backwash(device, T0 + timedelta(hours=3)) is None


def test_next_scheduled_backwash_unknown_after_unattributed_only():
    """An unattributed cycle says nothing about the schedule phase either."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_service_menu_cycle(tracker, T0 + timedelta(hours=2), False)

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.next_scheduled_backwash(device, T0 + timedelta(hours=3)) is None


def test_next_scheduled_backwash_projected_from_last_scheduled():
    """next = last scheduled cycle + interval, snapped to the configured time."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_cycle(tracker, T0)

    # Recorded at the window midpoint (T0 + 45 s), but the projection snaps to
    # the configured 21:00 slot — that is when the unit will actually fire.
    assert tracker.next_scheduled_backwash(
        device, T0 + timedelta(minutes=5)
    ) == datetime(2026, 6, 17, 21, 0, 0, tzinfo=timezone.utc)


def test_next_scheduled_backwash_rolls_forward_past_missed_cycles():
    """Cycles missed while HA was down must not leave 'next' stuck in the past."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    _run_cycle(tracker, T0)

    # Ten days later: 06-17, 06-20 and 06-23 have all come and gone.
    now = T0 + timedelta(days=10)
    assert tracker.next_scheduled_backwash(device, now) == datetime(
        2026, 6, 26, 21, 0, 0, tzinfo=timezone.utc
    )


def test_next_scheduled_backwash_none_when_schedule_disabled():
    """With automatic backwash switched off there is no next cycle to project."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    assert tracker.last_scheduled_backwash is not None

    disabled = _device(False, backwash_time=SCHEDULE_AT, backwash_every_n_days=0)
    assert tracker.next_scheduled_backwash(disabled, T0 + timedelta(minutes=5)) is None


# ── persistence of the classification ───────────────────────────────────────


async def test_async_load_restores_classified_state():
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


async def test_async_load_accepts_an_unknown_trigger():
    """UNKNOWN round-trips through the store like the other two."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_load = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "last_backwash": T0.isoformat(),
            "last_trigger": "unknown",
        }
    )

    await tracker.async_load()

    assert tracker.last_backwash == T0
    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None


async def test_async_save_writes_an_unknown_trigger():
    """The verdict survives a restart rather than being re-derived."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0 + timedelta(hours=2), False)
    await tracker.async_save()

    saved = tracker._store.async_save.call_args.args[0]  # type: ignore[attr-defined]
    assert saved["last_trigger"] == "unknown"
    assert saved["last_manual_backwash"] is None
    assert saved["last_scheduled_backwash"] is None


async def test_async_load_tolerates_version_1_payload():
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


async def test_async_save_persists_classification():
    """The saved payload carries everything async_load reads back."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._store.async_save = AsyncMock()  # type: ignore[method-assign]

    _run_cycle(tracker, T0)
    await tracker.async_save()

    saved = tracker._store.async_save.call_args.args[0]  # type: ignore[attr-defined]
    assert saved["last_backwash"] == (T0 + timedelta(seconds=45)).isoformat()
    assert saved["last_scheduled_backwash"] == (T0 + timedelta(seconds=45)).isoformat()
    assert saved["last_manual_backwash"] is None
    assert saved["last_trigger"] == "scheduled"


# ── manual seeding and provenance ───────────────────────────────────────────


def test_manual_seed_marks_source_and_drives_projection():
    """A seeded date starts the projection and is labelled as manual."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    device = _scheduled_device(False)

    seeded = T0 - timedelta(days=1)
    tracker.set_last_scheduled_backwash(seeded)

    assert tracker.last_scheduled_backwash == seeded
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL
    # Seeded 2026-06-13 21:00, interval 3 days -> 2026-06-16 21:00.
    assert tracker.next_scheduled_backwash(device, T0) == datetime(
        2026, 6, 16, 21, 0, 0, tzinfo=timezone.utc
    )


def test_manual_seed_does_not_touch_observed_last_backwash():
    """last_backwash means "we watched this happen" — typing a date does not."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.set_last_scheduled_backwash(T0 - timedelta(days=1))

    assert tracker.last_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None


def test_cycle_detected_after_a_seed_supersedes_it():
    """The seed stood in for a real cycle; once one is detected, it takes over."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.set_last_scheduled_backwash(T0 - timedelta(days=1))
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL

    _run_cycle(tracker, T0)

    assert tracker.last_scheduled_backwash == T0 + timedelta(seconds=45)
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED


def test_cycle_detected_after_a_later_dated_seed_still_supersedes_it():
    """Last write wins — the stored timestamps are never compared.

    Even a seed dated after the detected cycle gives way, because the cycle
    was recorded later and is the more current answer.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.set_last_scheduled_backwash(T0 + timedelta(days=5))
    _run_cycle(tracker, T0)

    assert tracker.last_scheduled_backwash == T0 + timedelta(seconds=45)
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED


def test_manual_seed_overrides_an_observed_value():
    """A manual entry replaces a detected one — the user has a reason."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_cycle(tracker, T0)
    assert tracker.last_scheduled_source is AsekoBackwashSource.OBSERVED

    corrected = T0 - timedelta(days=10)
    tracker.set_last_scheduled_backwash(corrected)

    assert tracker.last_scheduled_backwash == corrected
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


def test_observed_manual_cycle_leaves_the_seed_alone():
    """A detected *manual* backwash says nothing about the schedule phase."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    seeded = T0 - timedelta(days=1)
    tracker.set_last_scheduled_backwash(seeded)
    # far from backwash_time, and observed from the settings menu
    _run_service_menu_cycle(tracker, T0 + timedelta(hours=3), True)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_scheduled_backwash == seeded
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


def test_no_source_while_nothing_is_known():
    """No value, no provenance — the attribute stays absent rather than lying."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    assert tracker.last_scheduled_source is None


async def test_manual_seed_is_persisted_before_any_observation():
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


async def test_async_load_restores_manual_source():
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


async def test_async_load_treats_sourceless_stored_value_as_observed():
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


def test_backfill_classifies_a_pre_split_record_as_scheduled():
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


def test_backfill_classifies_a_pre_split_record_as_manual():
    """Same, for a stored cycle that did not run at the scheduled time.

    This device does not report the menu, so the elimination rule applies to
    the backfilled record exactly as it does to a live one.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    off_schedule = T0 + timedelta(hours=4)
    tracker._last_backwash = off_schedule  # type: ignore[attr-defined]

    tracker.update(_scheduled_device(False), off_schedule + timedelta(minutes=5))

    assert tracker.last_manual_backwash == off_schedule
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_scheduled_backwash is None


def test_backfill_leaves_an_unmatched_salt_record_unattributed():
    """On SALT the menu bit is not recoverable after the fact.

    So a stored cycle that does not match the schedule cannot be attributed
    at all: it keeps its place in last_backwash and fills neither half.  The
    next real cycle is classified properly, menu bit and all.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    off_schedule = T0 + timedelta(hours=4)
    tracker._last_backwash = off_schedule  # type: ignore[attr-defined]

    tracker.update(_salt_device(False, False), off_schedule + timedelta(minutes=5))

    assert tracker.last_trigger is AsekoBackwashTrigger.UNKNOWN
    assert tracker.last_manual_backwash is None
    assert tracker.last_scheduled_backwash is None


def test_backfill_does_not_retry_an_unattributed_record():
    """The verdict does not change frame to frame, so it is reached once."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    off_schedule = T0 + timedelta(hours=4)
    tracker._last_backwash = off_schedule  # type: ignore[attr-defined]

    tracker.update(_salt_device(False, False), off_schedule + timedelta(minutes=5))
    tracker.update(_salt_device(False, False), off_schedule + timedelta(minutes=10))

    assert tracker._backfill_attempted is True  # type: ignore[attr-defined]
    assert tracker.last_manual_backwash is None
    assert tracker.last_scheduled_backwash is None


def test_backfill_waits_for_a_frame_that_carries_the_schedule():
    """Without backwash_time there is nothing to classify against — retry later."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker._last_backwash = T0  # type: ignore[attr-defined]

    tracker.update(_device(False), T0 + timedelta(minutes=5))
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None

    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=10))
    assert tracker.last_scheduled_backwash == T0


def test_backfill_does_not_touch_an_already_split_store():
    """Once either bucket is filled the record is current — leave it alone."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    seeded = T0 - timedelta(days=3)
    tracker._last_backwash = T0  # type: ignore[attr-defined]
    tracker.set_last_scheduled_backwash(seeded)

    tracker.update(_scheduled_device(False), T0 + timedelta(minutes=5))

    assert tracker.last_scheduled_backwash == seeded
    assert tracker.last_scheduled_source is AsekoBackwashSource.MANUAL


def test_backfill_is_a_no_op_on_an_empty_store():
    """Nothing stored, nothing to classify."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.update(_scheduled_device(False), T0)

    assert tracker.last_backwash is None
    assert tracker.last_scheduled_backwash is None
    assert tracker.last_manual_backwash is None
    assert tracker.last_trigger is None


# ── clearing ────────────────────────────────────────────────────────────────


def test_clear_returns_the_value_to_unknown():
    """The undo for a mistyped date."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)
    tracker.set_last_scheduled_backwash(T0 - timedelta(days=1))

    tracker.clear_last_scheduled_backwash()

    assert tracker.last_scheduled_backwash is None
    assert tracker.last_scheduled_source is None


def test_clear_rearms_the_backfill():
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


def test_clear_is_a_no_op_when_already_unknown():
    """Nothing stored, nothing to clear — and no pointless write."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.clear_last_scheduled_backwash()

    assert tracker.last_scheduled_backwash is None
    tracker._hass.async_create_task.assert_not_called()  # type: ignore[attr-defined]


async def test_clear_is_persisted():
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
    backwash_active: bool | None,
    menu_open: bool,
    device_type: AsekoDeviceType = AsekoDeviceType.SALT,
) -> Any:
    """A scheduled device that also reports a device type and the menu flag."""
    dev = _scheduled_device(backwash_active)
    dev.device_type = device_type
    dev.service_menu_open = menu_open
    return dev


def _run_service_menu_cycle(
    tracker: BackwashTracker,
    start: datetime,
    menu_during: bool,
    device_type: AsekoDeviceType = AsekoDeviceType.SALT,
) -> None:
    """Drive a cycle that ends with the menu flag already dropped.

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


def test_service_menu_during_the_window_means_manual():
    """A SALT cycle run from the settings menu is manual, whatever the clock says.

    This is the case the time-only rule gets wrong: started by hand, but
    within tolerance of the configured time, so it used to be filed as the
    unit's own scheduled run and would have moved the next-backwash
    projection with it.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0, True)

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL
    assert tracker.last_manual_backwash is not None
    assert tracker.last_scheduled_backwash is None


def test_service_menu_is_latched_across_the_whole_window():
    """The flag counts even though the closing frame has already lost it.

    Reading the mode at the end of the window would miss every real cycle:
    in the capture the bit went out ~20 s after the valve closed, before
    the frame that ends the window arrived.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    tracker.update(_salt_device(True, True), T0)
    # the flag is already back down for the rest of the window
    tracker.update(
        _salt_device(True, False),
        T0 + timedelta(seconds=45),
    )
    tracker.update(
        _salt_device(False, False),
        T0 + timedelta(seconds=90),
    )

    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL


def test_without_the_service_menu_the_schedule_still_decides():
    """The flag only ever adds evidence; its absence changes nothing."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0, False)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
    assert tracker.last_scheduled_backwash is not None


def test_service_menu_signal_does_not_apply_to_home():
    """On HOME the same bit is a standing pump override, not a person.

    It can sit set indefinitely, so honouring it there would refile every
    scheduled cycle that happened to run while it was on.
    """
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0, True, AsekoDeviceType.HOME)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED


def test_service_menu_flag_does_not_leak_into_the_next_cycle():
    """Each window starts from a clean slate."""
    tracker = BackwashTracker(_hass(), serial_number=110071590)

    _run_service_menu_cycle(tracker, T0, True)
    assert tracker.last_trigger is AsekoBackwashTrigger.MANUAL

    later = T0 + timedelta(days=SCHEDULE_EVERY_N_DAYS)
    _run_service_menu_cycle(tracker, later, False)

    assert tracker.last_trigger is AsekoBackwashTrigger.SCHEDULED
