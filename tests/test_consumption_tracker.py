"""Tests for AsekoConsumptionTracker."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.aseko_local.aseko_data import AsekoDevice
from custom_components.aseko_local.consumption_tracker import (
    MAX_PUMP_INTERVAL,
    AsekoConsumptionTracker,
    PUMP_KEYS,
)

T0 = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _device(**kwargs) -> AsekoDevice:
    """Create a minimal AsekoDevice with given pump states."""
    return AsekoDevice(**kwargs)


# ---------------------------------------------------------------------------
# Basic accumulation
# ---------------------------------------------------------------------------


def test_first_on_packet_does_not_accumulate() -> None:
    """First ON packet only sets the timestamp – nothing is credited yet."""
    tracker = AsekoConsumptionTracker()
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)

    assert tracker.get("cl", "total") == 0.0
    assert tracker.get("cl", "canister") == 0.0


def test_second_on_packet_accumulates() -> None:
    """Second consecutive ON packet credits elapsed time × flowrate."""
    tracker = AsekoConsumptionTracker()
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))

    # 10s / 60 * 60 ml/min = 10 ml
    assert tracker.get("cl", "total") == pytest.approx(10.0)
    assert tracker.get("cl", "canister") == pytest.approx(10.0)


def test_pump_off_credits_final_interval_and_resets() -> None:
    """OFF packet credits the final ON→OFF interval; next ON starts fresh."""
    tracker = AsekoConsumptionTracker()
    on_dev = _device(cl_pump_running=True, flowrate_chlor=60)
    off_dev = _device(cl_pump_running=False, flowrate_chlor=60)

    tracker.update(on_dev, T0)  # sets timestamp
    tracker.update(off_dev, T0 + timedelta(seconds=10))  # credits 10 s
    tracker.update(on_dev, T0 + timedelta(seconds=20))  # fresh start
    tracker.update(on_dev, T0 + timedelta(seconds=30))  # credits another 10 s

    # 10 ml from ON→OFF  +  10 ml from ON→ON  =  20 ml
    assert tracker.get("cl", "total") == pytest.approx(20.0)


def test_multiple_pump_types_independent() -> None:
    """Each pump type is tracked independently."""
    tracker = AsekoConsumptionTracker()
    t1 = T0 + timedelta(seconds=10)

    d0 = _device(
        cl_pump_running=True,
        flowrate_chlor=60,
        ph_minus_pump_running=True,
        flowrate_ph_minus=30,
    )
    d1 = _device(
        cl_pump_running=True,
        flowrate_chlor=60,
        ph_minus_pump_running=False,
        flowrate_ph_minus=30,
    )

    tracker.update(d0, T0)
    tracker.update(d1, t1)

    # CL: 10 s × 60 mL/min = 10 mL; ph_minus OFF at T0+10s → 10 s × 30 mL/min = 5 mL credited
    assert tracker.get("cl", "total") == pytest.approx(10.0)
    assert tracker.get("ph_minus", "total") == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Connection-loss protection (cap to MAX_PUMP_INTERVAL)
# ---------------------------------------------------------------------------


def test_long_gap_is_capped() -> None:
    """A gap longer than MAX_PUMP_INTERVAL is capped; no phantom consumption."""
    tracker = AsekoConsumptionTracker()
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)
    # Simulate 30-minute outage
    tracker.update(device, T0 + timedelta(minutes=30))

    # Should be capped to MAX_PUMP_INTERVAL (30 s) not 30 min
    max_ml = (MAX_PUMP_INTERVAL.total_seconds() / 60.0) * 60
    assert tracker.get("cl", "total") == pytest.approx(max_ml)


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def test_reset_canister_only() -> None:
    """reset(counter='canister') zeroes canister but keeps total."""
    tracker = AsekoConsumptionTracker()
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))  # +10 ml each

    tracker.reset("cl", counter="canister")

    assert tracker.get("cl", "total") == pytest.approx(10.0)
    assert tracker.get("cl", "canister") == 0.0


def test_reset_total_only() -> None:
    """reset(counter='total') zeroes total but keeps canister."""
    tracker = AsekoConsumptionTracker()
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))  # +10 ml

    tracker.reset("cl", counter="total")

    assert tracker.get("cl", "total") == 0.0
    assert tracker.get("cl", "canister") == pytest.approx(10.0)


def test_reset_all_pumps() -> None:
    """reset(pump_key=None) resets canister for all pumps."""
    tracker = AsekoConsumptionTracker()
    device = _device(
        cl_pump_running=True,
        flowrate_chlor=60,
        ph_minus_pump_running=True,
        flowrate_ph_minus=30,
    )

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=60))

    tracker.reset(pump_key=None, counter="canister")

    for key in ("cl", "ph_minus"):
        assert tracker.get(key, "canister") == 0.0


def test_reset_all_counters() -> None:
    """reset(counter='all') zeroes both total and canister."""
    tracker = AsekoConsumptionTracker()
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=60))

    tracker.reset("cl", counter="all")

    assert tracker.get("cl", "total") == 0.0
    assert tracker.get("cl", "canister") == 0.0


# ---------------------------------------------------------------------------
# Seed (restore after restart)
# ---------------------------------------------------------------------------


def test_seed_restores_values() -> None:
    """seed() pre-populates counters; subsequent updates add on top."""
    tracker = AsekoConsumptionTracker()
    tracker.seed("cl", total_ml=5000.0, canister_ml=320.0)

    assert tracker.get("cl", "total") == pytest.approx(5000.0)
    assert tracker.get("cl", "canister") == pytest.approx(320.0)


def test_seed_then_update() -> None:
    """After seed, accumulation adds to the restored base values."""
    tracker = AsekoConsumptionTracker()
    tracker.seed("ph_minus", total_ml=1000.0, canister_ml=80.0)

    device = _device(ph_minus_pump_running=True, flowrate_ph_minus=60)
    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))  # +10 ml

    assert tracker.get("ph_minus", "total") == pytest.approx(1010.0)
    assert tracker.get("ph_minus", "canister") == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# None pump (pump not present on this device type)
# ---------------------------------------------------------------------------


def test_single_on_off_cycle_credits_interval() -> None:
    """A lone ON→OFF cycle (no second ON) is fully credited at OFF."""
    tracker = AsekoConsumptionTracker()
    on_dev = _device(cl_pump_running=True, flowrate_chlor=60)
    off_dev = _device(cl_pump_running=False, flowrate_chlor=60)

    tracker.update(on_dev, T0)
    tracker.update(off_dev, T0 + timedelta(seconds=3))  # 3 s pump run

    # 3 s / 60 * 60 mL/min = 3 mL
    assert tracker.get("cl", "total") == pytest.approx(3.0)


def test_none_pump_state_is_ignored() -> None:
    """Pumps with None state (not present on device) are silently skipped."""
    tracker = AsekoConsumptionTracker()
    # algicide_pump_running is None (not set on NET)
    device = _device(cl_pump_running=True, flowrate_chlor=60)

    tracker.update(device, T0)
    tracker.update(device, T0 + timedelta(seconds=10))

    assert tracker.get("algicide", "total") == 0.0
    assert tracker.get("cl", "total") == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------


def test_get_invalid_pump_key_raises() -> None:
    tracker = AsekoConsumptionTracker()
    with pytest.raises(ValueError, match="Unknown pump key"):
        tracker.get("invalid", "total")


def test_get_invalid_counter_raises() -> None:
    tracker = AsekoConsumptionTracker()
    with pytest.raises(ValueError, match="counter must be"):
        tracker.get("cl", "weekly")
