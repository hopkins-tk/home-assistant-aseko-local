"""Chemical consumption tracker for Aseko pool devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .aseko_data import AsekoDevice
from .const import READ_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# All chemical pump types tracked
PUMP_KEYS = ("cl", "ph_minus", "ph_plus", "algicide", "floc", "oxy")

# Maximum credible ON→ON interval to prevent runaway accumulation after connection loss
MAX_PUMP_INTERVAL = timedelta(seconds=READ_TIMEOUT)


@dataclass
class _PumpCounters:
    total: float = 0.0
    canister: float = 0.0


@dataclass
class AsekoConsumptionTracker:
    """Tracks chemical consumption (ml) per pump type for one device.

    Two independent counters per pump type:
    - total:   ever-growing, intended as base for HA Utility Meter (daily/weekly slices)
    - canister: reset by the user whenever a chemical container is refilled

    Both counters are updated simultaneously on every ON→ON update.

    Connection-loss safety: if the gap between two ON packets exceeds
    MAX_PUMP_INTERVAL (= READ_TIMEOUT = 30 s), only MAX_PUMP_INTERVAL
    is credited. This prevents hours of phantom consumption after a
    HA restart or TCP disconnect while a pump was running.
    """

    _counters: dict[str, _PumpCounters] = field(
        default_factory=lambda: {k: _PumpCounters() for k in PUMP_KEYS}
    )
    _last_on: dict[str, datetime | None] = field(
        default_factory=lambda: {k: None for k in PUMP_KEYS}
    )
    _last_flowrate: dict[str, int | None] = field(
        default_factory=lambda: {k: None for k in PUMP_KEYS}
    )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update(self, device: AsekoDevice, now: datetime) -> None:
        """Accumulate consumption from a new device packet.

        Called on every incoming packet from the Aseko unit.
        For each pump key the current state (on/off) is derived from the
        device and the elapsed time since the last ON packet is credited.
        """
        pump_states: dict[str, tuple[bool | None, int | None]] = {
            "cl": (device.cl_pump_running, device.flowrate_chlor),
            "ph_minus": (device.ph_minus_pump_running, device.flowrate_ph_minus),
            "ph_plus": (device.ph_plus_pump_running, device.flowrate_ph_plus),
            "algicide": (device.algicide_pump_running, device.flowrate_algicide),
            "floc": (device.floc_pump_running, device.flowrate_floc),
            "oxy": (device.oxy_pump_running, device.flowrate_oxy),
        }

        for key, (is_on, flowrate_per_min) in pump_states.items():
            if is_on is None:
                # Pump not present on this device type – skip silently
                self._last_on[key] = None
                self._last_flowrate[key] = None
                continue

            if is_on and flowrate_per_min:
                last = self._last_on[key]
                if last is not None:
                    raw_delta = now - last
                    # Cap delta to prevent phantom consumption after outages
                    effective_delta = min(raw_delta, MAX_PUMP_INTERVAL)
                    ml = (effective_delta.total_seconds() / 60.0) * flowrate_per_min
                    self._counters[key].total += ml
                    self._counters[key].canister += ml
                    _LOGGER.debug(
                        "Tracker[%s]: +%.1f mL (dt=%.1fs capped=%.1fs flowrate=%d mL/min)",
                        key,
                        ml,
                        raw_delta.total_seconds(),
                        effective_delta.total_seconds(),
                        flowrate_per_min,
                    )
                self._last_on[key] = now
                self._last_flowrate[key] = flowrate_per_min
            else:
                # Pump just turned OFF – credit the final ON→OFF interval
                last = self._last_on[key]
                saved_flowrate = self._last_flowrate[key]
                if last is not None and saved_flowrate:
                    raw_delta = now - last
                    effective_delta = min(raw_delta, MAX_PUMP_INTERVAL)
                    ml = (effective_delta.total_seconds() / 60.0) * saved_flowrate
                    self._counters[key].total += ml
                    self._counters[key].canister += ml
                    _LOGGER.debug(
                        "Tracker[%s] OFF: +%.1f mL (dt=%.1fs capped=%.1fs flowrate=%d mL/min)",
                        key,
                        ml,
                        raw_delta.total_seconds(),
                        effective_delta.total_seconds(),
                        saved_flowrate,
                    )
                self._last_on[key] = None
                self._last_flowrate[key] = None

    def get(self, pump_key: str, counter: str) -> float:
        """Return the current value (ml) for *pump_key* and *counter* ("total"|"canister")."""
        if pump_key not in self._counters:
            raise ValueError(f"Unknown pump key: {pump_key!r}")
        if counter not in ("total", "canister"):
            raise ValueError(f"counter must be 'total' or 'canister', got {counter!r}")
        return getattr(self._counters[pump_key], counter)

    def reset(
        self,
        pump_key: str | None = None,
        counter: str = "canister",
    ) -> None:
        """Reset consumption counter(s).

        Args:
            pump_key: which pump to reset, or None / "all" to reset all pumps.
            counter:  "total", "canister", or "all" – defaults to "canister".
        """
        if counter not in ("total", "canister", "all"):
            raise ValueError(
                f"counter must be 'total', 'canister', or 'all', got {counter!r}"
            )
        keys = list(PUMP_KEYS) if pump_key is None or pump_key == "all" else [pump_key]
        counters = ("total", "canister") if counter == "all" else (counter,)

        for k in keys:
            if k not in self._counters:
                _LOGGER.warning("reset: unknown pump key %r – skipping", k)
                continue
            for c in counters:
                setattr(self._counters[k], c, 0.0)
                _LOGGER.debug("Tracker reset: %s.%s → 0", k, c)

    def seed(self, pump_key: str, total_ml: float, canister_ml: float) -> None:
        """Restore persisted values after HA restart.

        Called from the RestoreSensor's async_added_to_hass once the
        previously stored state has been retrieved.
        """
        if pump_key not in self._counters:
            _LOGGER.warning("seed: unknown pump key %r – skipping", pump_key)
            return
        self._counters[pump_key].total = total_ml
        self._counters[pump_key].canister = canister_ml
        _LOGGER.debug(
            "Tracker seeded: %s total=%.1f canister=%.1f",
            pump_key,
            total_ml,
            canister_ml,
        )

    def seed_counter(self, pump_key: str, counter: str, value: float) -> None:
        """Restore a single persisted counter value after HA restart.

        Unlike seed(), which sets both counters at once, this updates only
        the named counter. Each AsekoConsumptionSensorEntity calls this
        independently from async_added_to_hass().
        """
        if pump_key not in self._counters:
            _LOGGER.warning("seed_counter: unknown pump key %r – skipping", pump_key)
            return
        if counter not in ("total", "canister"):
            raise ValueError(f"counter must be 'total' or 'canister', got {counter!r}")
        setattr(self._counters[pump_key], counter, value)
        _LOGGER.debug("Tracker seeded: %s.%s = %.1f", pump_key, counter, value)
