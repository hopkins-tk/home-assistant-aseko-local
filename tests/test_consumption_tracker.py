"""Tests for AsekoConsumptionTracker."""

from datetime import datetime, timedelta

import pytest

from custom_components.aseko_local.aseko_data import AsekoDevice
from custom_components.aseko_local.consumption_tracker import (
    AsekoConsumptionTracker,
    MAX_PUMP_INTERVAL,
)


# ── helpers ────────────────────────────────────────────────────────────────────

T0 = datetime(2024, 1, 1, 12, 0, 0)


def _device(
    cl_on: bool | None = None,
    cl_rate: int | None = None,
    ph_minus_on: bool | None = None,
    ph_minus_rate: int | None = None,
) -> AsekoDevice:
    """Make a minimal AsekoDevice with only the fields the tracker uses."""
    d = AsekoDevice()
    d.cl_pump_running = cl_on
    d.flowrate_chlor = cl_rate
    d.ph_minus_pump_running = ph_minus_on
    d.flowrate_ph_minus = ph_minus_rate
    # leave all other pump fields as None (not present on this device type)
    return d


# ── update: basic accumulation ─────────────────────────────────────────────────


def test_first_on_packet_does_not_accumulate():
    """First ON packet only records the timestamp – no volume yet."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)

    assert tracker.get("cl", "total") == 0.0
    assert tracker.get("cl", "canister") == 0.0


def test_second_on_packet_accumulates():
    """ON → ON 30 s later at 60 mL/min should credit 30 mL."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=30))

    assert tracker.get("cl", "total") == pytest.approx(30.0)
    assert tracker.get("cl", "canister") == pytest.approx(30.0)


def test_both_counters_updated_together():
    """Total and canister always increment together (gap capped at 30 s)."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=120), T0)
    # 60 s gap > MAX_PUMP_INTERVAL (30 s) ➜ capped to 30 s × 120 mL/min = 60 mL
    tracker.update(_device(cl_on=True, cl_rate=120), T0 + timedelta(seconds=60))

    assert tracker.get("cl", "total") == pytest.approx(60.0)
    assert tracker.get("cl", "canister") == pytest.approx(60.0)


def test_multiple_consecutive_on_packets_accumulate():
    """Three ON packets 10 s apart should accumulate two deltas."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=10))
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=20))

    # 2 × (10s / 60s * 60 mL/min) = 2 × 10 = 20 mL
    assert tracker.get("cl", "total") == pytest.approx(20.0)


# ── update: on → off credits final interval ────────────────────────────────────


def test_off_packet_after_on_credits_interval():
    """ON then OFF 30 s later should credit 30 mL using saved flowrate."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    tracker.update(_device(cl_on=False, cl_rate=60), T0 + timedelta(seconds=30))

    assert tracker.get("cl", "total") == pytest.approx(30.0)
    assert tracker.get("cl", "canister") == pytest.approx(30.0)


def test_off_packet_resets_last_on():
    """After OFF the next ON starts a fresh accumulation window."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    # 60 s gap → capped at 30 s × 60 mL/min = 30 mL
    tracker.update(_device(cl_on=False, cl_rate=60), T0 + timedelta(seconds=60))
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=90))  # new window
    # 2nd ON is first of new window → no extra accumulation
    assert tracker.get("cl", "total") == pytest.approx(30.0)


def test_off_without_prior_on_does_nothing():
    """OFF packet without a preceding ON should not accumulate anything."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=False, cl_rate=60), T0)
    tracker.update(_device(cl_on=False, cl_rate=60), T0 + timedelta(seconds=30))

    assert tracker.get("cl", "total") == 0.0


# ── update: pump not present (None) ───────────────────────────────────────────


def test_pump_none_is_ignored():
    """Pump state None (not on this device type) silently does nothing."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=None, cl_rate=60), T0)
    tracker.update(_device(cl_on=None, cl_rate=60), T0 + timedelta(seconds=30))

    assert tracker.get("cl", "total") == 0.0


def test_pump_none_clears_previous_last_on():
    """Transitioning to None clears last_on so no phantom accumulation if it comes back."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    # Simulate device type change → pump becomes None
    tracker.update(_device(cl_on=None, cl_rate=60), T0 + timedelta(seconds=30))
    # Now ON again – should start fresh, not credit the gap
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=60))
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=70))

    # Only the last 10 s of fresh window should be credited
    assert tracker.get("cl", "total") == pytest.approx(10.0)


# ── update: outage capping ────────────────────────────────────────────────────


def test_long_gap_is_capped_at_max_pump_interval():
    """Gap longer than MAX_PUMP_INTERVAL (30 s) is capped."""
    tracker = AsekoConsumptionTracker()
    big_gap = MAX_PUMP_INTERVAL + timedelta(seconds=3600)  # 1 h gap

    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + big_gap)

    expected_ml = (MAX_PUMP_INTERVAL.total_seconds() / 60.0) * 60
    assert tracker.get("cl", "total") == pytest.approx(expected_ml)


def test_normal_gap_is_not_capped():
    """Gap shorter than MAX_PUMP_INTERVAL is credited in full."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=20))

    assert tracker.get("cl", "total") == pytest.approx(20.0)


# ── update: zero flowrate treated as off ──────────────────────────────────────


def test_on_with_zero_flowrate_does_not_accumulate():
    """is_on=True but flowrate=0 should not accumulate (falsy flowrate guard)."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=0), T0)
    tracker.update(_device(cl_on=True, cl_rate=0), T0 + timedelta(seconds=30))

    assert tracker.get("cl", "total") == 0.0


# ── update: independent pumps ─────────────────────────────────────────────────


def test_independent_pump_counters():
    """cl and ph_minus accumulators are independent (gap capped at 30 s)."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60, ph_minus_on=True, ph_minus_rate=30), T0)
    # 60 s gap → capped at 30 s
    tracker.update(
        _device(cl_on=True, cl_rate=60, ph_minus_on=True, ph_minus_rate=30),
        T0 + timedelta(seconds=60),
    )

    assert tracker.get("cl", "total") == pytest.approx(30.0)      # 30 s × 60 mL/min
    assert tracker.get("ph_minus", "total") == pytest.approx(15.0)  # 30 s × 30 mL/min


# ── reset ─────────────────────────────────────────────────────────────────────


def test_reset_canister_leaves_total():
    """reset(counter='canister') zeros canister but keeps total."""
    tracker = AsekoConsumptionTracker()
    tracker.update(_device(cl_on=True, cl_rate=60), T0)
    # 30 s × 60 mL/min = 30 mL (within MAX_PUMP_INTERVAL, no cap)
    tracker.update(_device(cl_on=True, cl_rate=60), T0 + timedelta(seconds=30))

    tracker.reset(pump_key="cl", counter="canister")

    assert tracker.get("cl", "canister") == 0.0
    assert tracker.get("cl", "total") == pytest.approx(30.0)


def test_reset_all_pumps_single_counter():
    """reset(pump_key='all') resets all pumps for the given counter."""
    tracker = AsekoConsumptionTracker()
    for key in ("cl", "ph_minus"):
        tracker._counters[key].canister = 100.0
        tracker._counters[key].total = 200.0

    tracker.reset(pump_key="all", counter="canister")

    assert tracker.get("cl", "canister") == 0.0
    assert tracker.get("ph_minus", "canister") == 0.0
    # totals untouched
    assert tracker.get("cl", "total") == pytest.approx(200.0)


def test_reset_single_pump_all_counters():
    """reset(counter='all') zeros both total and canister for the given pump."""
    tracker = AsekoConsumptionTracker()
    tracker._counters["cl"].total = 99.0
    tracker._counters["cl"].canister = 55.0

    tracker.reset(pump_key="cl", counter="all")

    assert tracker.get("cl", "total") == 0.0
    assert tracker.get("cl", "canister") == 0.0


def test_reset_none_pump_key_resets_all():
    """reset(pump_key=None) behaves like pump_key='all'."""
    tracker = AsekoConsumptionTracker()
    for key in ("cl", "ph_minus", "floc"):
        tracker._counters[key].canister = 10.0

    tracker.reset(pump_key=None, counter="canister")

    for key in ("cl", "ph_minus", "floc"):
        assert tracker.get(key, "canister") == 0.0


def test_reset_unknown_pump_key_does_not_raise(caplog):
    """reset with an unknown pump key logs a warning and continues without crashing."""
    tracker = AsekoConsumptionTracker()
    tracker.reset(pump_key="unknown_pump", counter="canister")  # must not raise


def test_reset_invalid_counter_raises():
    """reset with an invalid counter string raises ValueError."""
    tracker = AsekoConsumptionTracker()
    with pytest.raises(ValueError, match="counter must be"):
        tracker.reset(pump_key="cl", counter="bad_counter")


# ── get ───────────────────────────────────────────────────────────────────────


def test_get_invalid_pump_raises():
    tracker = AsekoConsumptionTracker()
    with pytest.raises(ValueError, match="Unknown pump key"):
        tracker.get("nonexistent", "total")


def test_get_invalid_counter_raises():
    tracker = AsekoConsumptionTracker()
    with pytest.raises(ValueError, match="counter must be"):
        tracker.get("cl", "bad")


# ── seed ──────────────────────────────────────────────────────────────────────


def test_seed_sets_both_counters():
    tracker = AsekoConsumptionTracker()
    tracker.seed("cl", total_ml=500.0, canister_ml=123.5)

    assert tracker.get("cl", "total") == pytest.approx(500.0)
    assert tracker.get("cl", "canister") == pytest.approx(123.5)


def test_seed_unknown_key_does_not_raise():
    tracker = AsekoConsumptionTracker()
    tracker.seed("no_such_pump", total_ml=1.0, canister_ml=1.0)  # must not raise


# ── seed_counter ──────────────────────────────────────────────────────────────


def test_seed_counter_sets_single_counter():
    tracker = AsekoConsumptionTracker()
    tracker.seed_counter("ph_minus", "total", 77.7)

    assert tracker.get("ph_minus", "total") == pytest.approx(77.7)
    assert tracker.get("ph_minus", "canister") == 0.0  # untouched


def test_seed_counter_unknown_key_does_not_raise():
    tracker = AsekoConsumptionTracker()
    tracker.seed_counter("no_such_pump", "total", 1.0)  # must not raise


def test_seed_counter_invalid_counter_raises():
    tracker = AsekoConsumptionTracker()
    with pytest.raises(ValueError, match="counter must be"):
        tracker.seed_counter("cl", "whatever", 1.0)
