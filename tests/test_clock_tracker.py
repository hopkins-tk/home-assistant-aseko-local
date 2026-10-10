"""The unit's clock against Home Assistant's: offset and the out-of-sync alert."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.aseko_local.coordinator import (
    AsekoLocalDataUpdateCoordinator,
)
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.trackers.clock import (
    DEFAULT_ALERT_MINUTES,
    SAMPLES,
    ClockTracker,
    offset_seconds,
)

from .test_decode_v7 import _make_base_bytes
from .test_decode_v8 import REFERENCE_FRAME

T0 = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _home_assistant_in_utc() -> Iterator[None]:
    """Compare the v8 reading in UTC here; it has no zone of its own."""
    original = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(UTC)
    yield
    dt_util.set_default_time_zone(original)


def _feed(tracker: ClockTracker, offsets_minutes, start: datetime = T0) -> None:
    """Frames ten seconds apart whose unit clock is ``offset`` minutes off."""
    for i, minutes in enumerate(offsets_minutes):
        received = start + timedelta(seconds=10 * i)
        tracker.update(received + timedelta(minutes=minutes), received)


# ── decoding ─────────────────────────────────────────────────────────────────


def test_v7_unit_clock_is_what_the_unit_sent() -> None:
    device = decode(bytes(_make_base_bytes()))
    assert device.unit_clock == datetime(2024, 6, 15, 12, 34, 56, tzinfo=UTC)
    assert "unit_clock" in device.features


def test_v7_unit_clock_is_none_when_the_bytes_are_unset() -> None:
    data = _make_base_bytes()
    data[6:12] = b"\xff" * 6
    device = decode(bytes(data))
    assert device.unit_clock is None
    # timestamp still falls back to Home Assistant's clock; the unit clock does not
    assert device.timestamp is not None


def test_v7_net_does_not_have_a_unit_clock() -> None:
    data = _make_base_bytes()
    data[4] = 0x09  # NET, CLF probe
    data[6:12] = b"\xff" * 6
    device = decode(bytes(data))
    assert "unit_clock" not in device.possible_features


def test_v8_unit_clock_is_hour_and_minute() -> None:
    device = decode(REFERENCE_FRAME)
    assert device.unit_clock == time(22, 27)


# ── offset ───────────────────────────────────────────────────────────────────


def test_offset_of_a_unit_ahead_is_positive_and_behind_negative() -> None:
    assert offset_seconds(T0 + timedelta(minutes=5, seconds=30), T0) == 330
    assert offset_seconds(T0 - timedelta(minutes=12), T0) == -720


def test_v8_offset_takes_the_middle_of_the_minute_and_crosses_midnight() -> None:
    received = datetime(2026, 9, 14, 23, 58, 30, tzinfo=UTC)
    assert offset_seconds(time(23, 58), received) == 0
    # the unit already shows 00:03 of the next day: five minutes ahead
    assert offset_seconds(time(0, 3), received) == 300
    # and one still before midnight while HA is past it: behind
    assert offset_seconds(time(23, 50), received + timedelta(minutes=5)) == -780


def test_offset_is_the_median_so_one_odd_frame_does_not_move_it() -> None:
    tracker = ClockTracker()
    _feed(tracker, [5.5, 42.0, 5.4])
    assert tracker.offset_minutes == 5.5


def test_nothing_is_decided_before_enough_frames() -> None:
    tracker = ClockTracker()
    _feed(tracker, [30.0] * (SAMPLES - 1))
    assert tracker.offset_minutes == 30.0
    assert tracker.out_of_sync is None


def test_frames_without_a_clock_change_nothing() -> None:
    tracker = ClockTracker()
    _feed(tracker, [5.0] * SAMPLES)
    tracker.update(None, T0 + timedelta(hours=1))
    assert tracker.offset_minutes == 5.0
    assert tracker.out_of_sync is False


# ── alert ────────────────────────────────────────────────────────────────────


def test_default_limit_is_fifteen_minutes() -> None:
    assert DEFAULT_ALERT_MINUTES == 15
    assert ClockTracker().alert_minutes == 15


def test_a_small_drift_does_not_alert() -> None:
    tracker = ClockTracker()
    _feed(tracker, [5.1, 5.3, 5.5])
    assert tracker.out_of_sync is False


@pytest.mark.parametrize("minutes", [15.0, -15.0, 60.0, -61.0])
def test_past_the_limit_either_way_alerts(minutes) -> None:
    tracker = ClockTracker()
    _feed(tracker, [minutes] * SAMPLES)
    assert tracker.out_of_sync is True


def test_one_late_frame_does_not_alert() -> None:
    tracker = ClockTracker()
    _feed(tracker, [1.0, 1.0, 1.0, 20.0, 1.0])
    assert tracker.out_of_sync is False


def test_it_clears_only_below_the_hysteresis() -> None:
    tracker = ClockTracker()
    _feed(tracker, [20.0] * SAMPLES)
    assert tracker.out_of_sync is True

    _feed(tracker, [13.0] * SAMPLES, T0 + timedelta(minutes=5))  # under 15, over 12
    assert tracker.out_of_sync is True

    _feed(tracker, [11.0] * SAMPLES, T0 + timedelta(minutes=10))
    assert tracker.out_of_sync is False


@pytest.mark.parametrize("readings", [[20, 20, 0], [0, 20, 20], [-20, 0, -20]])
def test_turning_on_takes_three_readings_even_at_the_start(readings) -> None:
    """Audit K2: two readings past the limit out of three are not enough."""
    tracker = ClockTracker()
    _feed(tracker, readings)
    assert tracker.out_of_sync is False


def test_a_first_window_inside_the_band_is_off() -> None:
    tracker = ClockTracker()
    _feed(tracker, [13.0, 16.0, 13.5])
    assert tracker.out_of_sync is False


@pytest.mark.parametrize(
    ("limit", "clears_below"),
    [(1, 48), (2, 96), (10, 480), (15, 720), (180, 10620)],
)
def test_every_limit_can_clear(limit, clears_below) -> None:
    """Audit K1: the hysteresis is a fifth of the limit, at most 3 min."""
    tracker = ClockTracker(alert_minutes=limit)
    _feed(tracker, [limit * 2] * SAMPLES)
    assert tracker.out_of_sync is True

    # exactly on the line still counts as off the limit
    _feed(tracker, [clears_below / 60] * SAMPLES, T0 + timedelta(minutes=5))
    assert tracker.out_of_sync is True

    _feed(tracker, [0.0] * SAMPLES, T0 + timedelta(minutes=10))
    assert tracker.out_of_sync is False


def test_the_limit_can_be_set_lower() -> None:
    tracker = ClockTracker(alert_minutes=5)
    _feed(tracker, [5.1, 5.3, 5.5])
    assert tracker.out_of_sync is True
    # a fifth of the limit: off again below 4 minutes
    _feed(tracker, [4.5] * SAMPLES, T0 + timedelta(minutes=5))
    assert tracker.out_of_sync is True
    _feed(tracker, [3.9] * SAMPLES, T0 + timedelta(minutes=10))
    assert tracker.out_of_sync is False


def test_two_units_are_tracked_apart() -> None:
    ahead, fine = ClockTracker(), ClockTracker()
    _feed(ahead, [30.0] * SAMPLES)
    _feed(fine, [0.5] * SAMPLES)
    assert (ahead.out_of_sync, fine.out_of_sync) == (True, False)


# ── offset from a UTC receive time across a change of time (audit B1) ────────


@pytest.mark.parametrize(
    ("received_utc", "unit_wall", "offset"),
    [
        # 25 Oct 2026: 01:30 UTC is the second 02:30 (+01); the unit shows 02:30
        (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), datetime(2026, 10, 25, 2, 30), 0.0),
        # the first 02:30 (+02), 00:30 UTC; the unit in step
        (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 25, 2, 30), 0.0),
        # 29 Mar 2026: 01:30 UTC is 03:30 (+02); the unit stayed on winter time
        (datetime(2026, 3, 29, 1, 30, tzinfo=UTC), datetime(2026, 3, 29, 2, 30), -60.0),
        # 25 Oct after the change, the unit still on summer time
        (
            datetime(2026, 10, 25, 7, 0, tzinfo=UTC),
            datetime(2026, 10, 25, 9, 5, 30),
            65.5,
        ),
    ],
)
def test_offset_compares_wall_clocks_from_a_utc_receive_time(
    received_utc, unit_wall, offset
) -> None:
    """What the server hands over (UTC) through the real v7 decoder."""

    zone = ZoneInfo("Europe/Bratislava")
    dt_util.set_default_time_zone(zone)
    data = _make_base_bytes()
    data[6:12] = bytes(
        (
            unit_wall.year - 2000,
            unit_wall.month,
            unit_wall.day,
            unit_wall.hour,
            unit_wall.minute,
            unit_wall.second,
        )
    )
    tracker = ClockTracker()
    for i in range(SAMPLES):
        received = received_utc + timedelta(seconds=10 * i)
        unit = decode(bytes(data)).unit_clock + timedelta(seconds=10 * i)
        tracker.update(unit, received)

    assert tracker.offset_minutes == offset
    assert tracker.out_of_sync is (abs(offset) >= DEFAULT_ALERT_MINUTES)


# ── "in the future" on the unit's clock (audit B2) ───────────────────────────


def test_unit_clock_now_is_signed_and_the_earliest_of_the_units(monkeypatch) -> None:

    now = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "now", lambda: now)
    coordinator = object.__new__(AsekoLocalDataUpdateCoordinator)
    devices = [
        SimpleNamespace(serial_number=1, clock_offset=-60.0),  # an hour behind
        SimpleNamespace(serial_number=2, clock_offset=5.5),
        SimpleNamespace(serial_number=3, clock_offset=None),  # not measured
        SimpleNamespace(serial_number=4, clock_offset=30.0),  # no backwash valve
    ]
    coordinator.get_devices = lambda: devices
    coordinator._backwash_trackers = {1: None, 2: None, 3: None}

    assert coordinator.unit_clock_now(1) == now - timedelta(hours=1)
    assert coordinator.unit_clock_now(2) == now + timedelta(minutes=5.5)
    assert coordinator.unit_clock_now(3) == now
    assert coordinator.unit_clock_now(4) is None
    # for every unit at once: in the past for each of them
    assert coordinator.unit_clock_now() == now - timedelta(hours=1)
