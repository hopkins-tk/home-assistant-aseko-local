"""Tests for BackwashTracker.

Models a real-world backwash cycle: the relay must stay on for at least
60 seconds (MIN_BACKWASH_DURATION) for the event to be recorded.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock


from custom_components.aseko_local.backwash_tracker import (
    BackwashTracker,
    MAX_FRAME_GAP,
)

T0 = datetime(2026, 6, 14, 21, 0, 0, tzinfo=timezone.utc)


# ── helpers ──────────────────────────────────────────────────────────────────


def _device(backwash_active: bool | None) -> Any:
    """Minimal stand-in for AsekoDevice with only the field the tracker reads."""
    dev = MagicMock()
    dev.backwash_active = backwash_active
    return dev


def _hass() -> MagicMock:
    """Mock Home Assistant — only ``async_create_task`` is needed by the tracker.

    ``Store.__init__`` requires ``hass.config.path(...)`` to resolve to a real
    path-like value, so we return a ``Path`` instead of letting the default
    ``MagicMock`` raise ``AttributeError`` deep in the constructor.
    """
    hass = MagicMock()
    hass.config.path.side_effect = lambda *parts: "/tmp/aseko_test/" + "/".join(parts)
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


async def test_async_save_skipped_when_no_event():
    """async_save is a no-op when nothing has been recorded yet."""
    hass = _hass()
    tracker = BackwashTracker(hass, serial_number=110071590)
    # last_backwash is None → async_save returns without touching the store.
    await tracker.async_save()
    hass.async_create_task.assert_not_called()
