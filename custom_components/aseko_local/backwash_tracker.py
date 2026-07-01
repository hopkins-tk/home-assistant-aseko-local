"""Persistent tracker for the last successful filter backwash cycle.

A "successful" backwash is defined as the backwash relay (byte[29] bit 0x01)
remaining continuously active for at least 60 seconds.  Short relay
activations (e.g. menu navigation, output-test mode) are ignored.

The last detected backwash timestamp is stored persistently via the
Home Assistant ``Store`` API and survives:
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
    * ``tracker.last_backwash`` — read-only property; the value shown to HA
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
    from .aseko_data import AsekoDevice

_LOGGER = logging.getLogger(__name__)

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

# Home Assistant Store schema versioning — bump if the persisted shape changes.
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "aseko_local_backwash_"


class BackwashTracker:
    """Detects and persistently records filter backwash events.

    One instance per device (keyed by ``serial_number``).  Holds the relay
    state machine between frames and is responsible for saving the
    confirmed backwash timestamp to disk so it survives restarts.
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

        # Last frame timestamp we processed — used to detect dropped connections.
        self._last_frame_at: datetime | None = None

        # The recorded timestamp (loaded from / saved to storage).
        self._last_backwash: datetime | None = None

    @property
    def serial_number(self) -> int:
        """Return the device serial number this tracker belongs to."""
        return self._serial

    @property
    def last_backwash(self) -> datetime | None:
        """Return the most recent confirmed backwash timestamp, or None."""
        return self._last_backwash

    async def async_load(self) -> None:
        """Load the persistent state from storage.  Call once at startup."""
        data = await self._store.async_load()
        if not data or "last_backwash" not in data:
            return
        try:
            self._last_backwash = datetime.fromisoformat(data["last_backwash"])
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Could not parse stored last_backwash for serial=%s: %r",
                self._serial,
                data.get("last_backwash"),
            )

    async def async_save(self) -> None:
        """Persist the current state to storage.  No-op if no event recorded yet."""
        if self._last_backwash is None:
            return
        await self._store.async_save({"last_backwash": self._last_backwash.isoformat()})

    def update(self, device: "AsekoDevice", now: datetime) -> None:
        """Feed a fresh decoded device state into the tracker.

        Call this from the coordinator after every received frame.  No-op
        for devices that do not have a backwash valve (NET — where
        ``backwash_active`` is ``None``).
        """
        if device.backwash_active is None:
            # NET or unknown — nothing to track.
            return

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
        self._last_frame_at = now

        # Step 2: if the relay is on, start (or continue) a new window.
        if device.backwash_active:
            if self._relay_on_since is None:
                self._relay_on_since = now
            return

        # Step 3: relay just went off.  Evaluate the previous "on" window.
        if self._relay_on_since is not None:
            duration = now - self._relay_on_since
            if duration >= MIN_BACKWASH_DURATION:
                # Record the midpoint of the window as the backwash timestamp.
                # Better than the start (user might still see "now") or the end
                # (user has to wait until relay goes off to see anything).
                recorded_at = self._relay_on_since + duration / 2
                if self._last_backwash is None or recorded_at > self._last_backwash:
                    self._last_backwash = recorded_at
                    _LOGGER.info(
                        "Backwash detected for serial=%s: %s (duration %s)",
                        self._serial,
                        recorded_at.isoformat(),
                        duration,
                    )
                    # Fire-and-forget save; the coordinator will trigger the
                    # next async_save explicitly when convenient.
                    self._hass.async_create_task(self.async_save())
                else:
                    _LOGGER.debug(
                        "Backwash event for serial=%s older than last record; "
                        "skipping (%s <= %s)",
                        self._serial,
                        recorded_at,
                        self._last_backwash,
                    )
            self._relay_on_since = None
