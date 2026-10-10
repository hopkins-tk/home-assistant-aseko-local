"""The data coordinator: devices, trackers, frame log and recording of one entry."""

import asyncio
import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from types import CoroutineType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLOCK_ALERT_MINUTES,
    MARK_DUMP_WAIT_TIMEOUT,
    MESSAGE_SIZE,
    SERIAL_NUMBER_LENGTH,
)
from .models import AsekoData, AsekoDevice
from .recording.frame_log import (
    KIND_PARTIAL,
    KIND_REJECTED,
    KIND_V7,
    KIND_V8,
    FrameLog,
)
from .trackers.backwash import BackwashTracker
from .trackers.clock import DEFAULT_ALERT_MINUTES, ClockTracker
from .trackers.consumption import AsekoConsumptionTracker

_LOGGER = logging.getLogger(__name__)

FRAME_LOG_STORAGE_VERSION = 1
CONSUMPTION_STORAGE_VERSION = 1
CONSUMPTION_STORAGE_KEY_PREFIX = "aseko_local_consumption_"
# pumps run for seconds at a time: save the exact millilitres at most once a minute
CONSUMPTION_SAVE_INTERVAL = timedelta(seconds=60)
FRAME_LOG_STORAGE_KEY_PREFIX = "aseko_local_frame_log_"
# How long after a request the frame log is written, and how often frames may
# request it: a crash loses at most a few minutes of frames.
FRAME_LOG_SAVE_DELAY = 60
# distinct warning reasons kept per unit; the rest are counted together
MAX_WARNING_REASONS = 50
OTHER_WARNING_REASONS = "other reasons (list full)"
FRAME_LOG_SAVE_INTERVAL = timedelta(minutes=10)


class RecordingOffError(Exception):
    """A marker was asked for while the frame log is off."""


class BackwashHistoryLoadingError(ServiceValidationError):
    """The backwash history of the named units is still being read.

    A ``ServiceValidationError`` so both the services and the datetime entity
    show the user what happened and that trying again works.
    """

    def __init__(self, serials: Iterable[int]) -> None:
        """Name the units whose history is not in yet."""
        names = ", ".join(str(serial) for serial in sorted(serials))
        super().__init__(
            f"The stored backwash history of {names} is still being read; "
            "try again in a moment"
        )


class AsekoLocalDataUpdateCoordinator(DataUpdateCoordinator[AsekoData]):
    """Aseko Local coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        cb_new_device: Callable[[AsekoDevice], CoroutineType[Any, Any, None]]
        | None = None,
    ) -> None:
        """Initialize coordinator."""
        self.host = config_entry.data[CONF_HOST]
        self.port = config_entry.data[CONF_PORT]
        self.cb_new_device = cb_new_device
        self.hass = hass

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{HOMEASSISTANT_DOMAIN} ({config_entry.unique_id})",
        )
        # One tracker per device serial number
        self._trackers: dict[int, AsekoConsumptionTracker] = {}
        # True once the entry's platforms are set up.  Until then every frame
        # asks for the set-up again, so one that failed is retried.
        self.platforms_ready = False
        # One backwash tracker per device serial number
        self._backwash_trackers: dict[int, BackwashTracker] = {}
        # One clock tracker per device serial number
        self._clock_trackers: dict[int, ClockTracker] = {}
        # Last raw frame per device serial number (for diagnostics)
        self._last_raw_frames: dict[int, bytes] = {}
        # Last partial (incomplete) raw frame per serial number
        self._last_partial_frames: dict[int, bytes] = {}
        # Last raw v8 text frame per device serial number (for diagnostics)
        self._last_v8_frames: dict[int, bytes] = {}
        # Last decoding of every unit whose type nobody has mapped, by serial
        # number -- kept for diagnostics only, never handed to the platforms
        self._unrecognised_devices: dict[int, AsekoDevice] = {}
        # Every frame received plus mark_dump markers, capped in compressed
        # bytes, for the diagnostics download; persisted across restarts
        self.frame_log = FrameLog()
        # Raised whenever recording stops or the recording is deleted: a mark
        # that started waiting under an older generation must not be written.
        self.recording_generation = 0
        self._frame_log_store: Store[dict[str, Any]] | None = None
        # exact consumption counters per serial number, saved across restarts
        self._consumption_store: Store[dict[str, Any]] | None = None
        self._consumption_saved_at: datetime | None = None
        self._frame_log_save_requested: datetime | None = None
        # When each unit's last frame arrived, and mark_dump calls waiting for
        # the next one
        self._last_frame_at: dict[int, datetime] = {}
        # (future, serial number or None for any unit) of mark_dump waits
        self._frame_waiters: list[tuple[asyncio.Future[None], int | None]] = []
        # Why the server found a unit's frames implausible, by serial number
        # and reason -- for diagnostics
        self._frame_warnings: dict[int, dict[str, dict[str, Any]]] = {}
        # Bytes that never became a frame (no serial number to file them
        # under), by reason -- for diagnostics
        self._rejected_frames: dict[str, dict[str, Any]] = {}
        # Unsubscribe handle for the periodic stale-check
        self._stale_check_unsub: Callable[[], None] | None = None
        # Per-platform listeners called whenever a brand-new device is discovered
        self._new_device_listeners: list[Callable[[AsekoDevice], None]] = []
        # Per-platform listeners called when a known device shows features it
        # has not shown before, with the names of those features
        self._new_features_listeners: list[
            Callable[[AsekoDevice, frozenset[str]], None]
        ] = []

    def _release_frame_waiters(self, serial: int | None) -> None:
        """End the waits a decoded frame from ``serial`` answers.

        Raw bytes are logged before they are decoded; only a frame the decoder
        accepted -- whole, parseable, from the unit being waited for -- says
        the unit's state has been sent.  A frame of a model nobody has mapped
        counts: it is exactly what a new model's test cases are made of.
        """
        if serial is None:
            return
        still_waiting = []
        for waiter, wanted in self._frame_waiters:
            if waiter.done():
                continue
            if wanted is None or wanted == serial:
                waiter.set_result(None)
            else:
                still_waiting.append((waiter, wanted))
        self._frame_waiters = still_waiting

    def knows_serial(self, serial_number: int) -> bool:
        """Return True once a frame from this unit reached this entry."""
        return serial_number in self._last_frame_at

    def devices_update_callback(self, device: AsekoDevice) -> None:
        """Receive callback with device update."""
        self._release_frame_waiters(getattr(device, "serial_number", None))

        if getattr(device, "device_type", None) is None:
            self._keep_unrecognised(device)
            return
        if device.serial_number is None:
            _LOGGER.error("❌ Received device without serial_number, not stored!")
            return  # abort, nothing to propagate

        _LOGGER.debug(
            "📡 devices_update_callback CALLED with device=%s (serial=%s)",
            device,
            device.serial_number,
        )
        new_data: AsekoData = AsekoData() if self.data is None else self.data
        # one moment for everything this frame updates: when the server had
        # the whole frame (UTC), or now for a device handed in directly
        received_at = getattr(device, "received_at", None) or dt_util.utcnow()
        is_new_device, grown = self._store_device(new_data, device, received_at)

        _LOGGER.debug(
            "⚠️ Calling async_set_updated_data() with %s devices",
            len(new_data.get_all()),
        )
        self.async_set_updated_data(new_data)

        if (is_new_device or not self.platforms_ready) and self.cb_new_device:
            # A set-up that failed is not lost: the next frame tries again.
            self.hass.loop.create_task(self.cb_new_device(device))
        if is_new_device:
            _LOGGER.debug("🆕 NEW DEVICE DISCOVERED: %s", device.serial_number)
            self._notify(self._new_device_listeners, device.serial_number, device)
        elif grown:
            # The unit has shown quantities it had not shown before -- the
            # shared pump port got configured, a setting was made, byte[37]
            # became readable.  Hand the platforms the stored device (the
            # object the existing entities read) so they can enable the
            # entities created disabled; Home Assistant reloads the entry to
            # add them.
            _LOGGER.debug(
                "🧩 Device %s shows new features: %s",
                device.serial_number,
                sorted(grown),
            )
            self._notify(
                self._new_features_listeners,
                device.serial_number,
                new_data.get(device.serial_number),
                grown,
            )

    def _keep_unrecognised(self, device: AsekoDevice) -> None:
        """Keep a frame from a unit type nobody has mapped, for diagnostics.

        It gets no entities -- nothing about it is verified -- but the
        diagnostics download shows its raw frame and the generic decoding,
        which is exactly what is needed to map it.
        """
        serial = getattr(device, "serial_number", None)
        if serial is None:
            return
        if serial not in self._unrecognised_devices:
            _LOGGER.warning(
                "❌ Received device with unknown type, not stored! serial=%s. "
                "Please share a diagnostics download at "
                "https://github.com/hopkins-tk/home-assistant-aseko-local/issues",
                serial,
            )
        self._unrecognised_devices[serial] = device

    def _store_device(
        self, new_data: AsekoData, device: AsekoDevice, received_at: datetime
    ) -> tuple[bool, frozenset[str]]:
        """Fill the trackers' fields, store the device; (is new, grown features)."""
        serial = device.serial_number
        existing = new_data.get(serial)
        is_new_device = existing is None
        _LOGGER.debug("➡️ Device %s is_new_device=%s", serial, is_new_device)
        grown = self._merge_features(device, existing)

        # Fill the observed-backwash fields *before* handing the device to
        # AsekoData.set(): for an already-known device, set() copies the
        # attributes off this object onto the stored one, and anything
        # written afterwards would never reach the entities.
        # the clock first: the backwash tracker reads its offset
        self._update_clock(device, received_at)
        self._update_backwash(device, received_at)

        new_data.set(serial, device)

        # Stamp server-side receive time (independent of device clock)
        stored = new_data.get(serial)
        if stored is not None:
            stored.last_seen = received_at

        # Update consumption tracker for this device
        tracker = self._trackers.get(serial)
        if tracker is None:
            tracker = self._trackers[serial] = AsekoConsumptionTracker()
        tracker.update(device, received_at)
        self._request_consumption_save()

        _LOGGER.debug(
            "✅ Stored device %s → known serials now: %s",
            serial,
            list(new_data.devices.keys()),
        )
        return is_new_device, grown

    @staticmethod
    def _notify(
        listeners: list[Callable[..., None]], serial: int, *args: object
    ) -> None:
        """Call every listener; one that raises does not stop the others."""
        for listener in list(listeners):
            try:
                listener(*args)
            except Exception:
                _LOGGER.exception(
                    "❌ Listener %r failed for device serial=%s", listener, serial
                )

    @staticmethod
    def _merge_features(
        device: AsekoDevice, existing: AsekoDevice | None
    ) -> frozenset[str]:
        """Make presence sticky and return what this frame added.

        Once a unit has shown a quantity it has it, whatever a later frame
        could or could not read (a shared port reconfigured, a probe briefly
        unreadable), so the stored device's feature set only ever grows.  The
        returned set is what the entity platforms have not been told about
        yet; empty for a device seen for the first time, whose whole feature
        set goes out through the new-device listeners instead.
        """
        if existing is None:
            return frozenset()
        grown = device.features - existing.features
        device.features = device.features | existing.features
        return grown

    def _update_backwash(self, device: AsekoDevice, now: datetime) -> None:
        """Feed the frame to the device's BackwashTracker and publish its state.

        The device transmits only the backwash *configuration* and the live
        relay bit, never its history, so every observed-backwash field on
        ``AsekoDevice`` comes from the tracker.  They stay None until a real
        cycle has been seen, which is what makes the sensors read "unknown"
        rather than showing a schedule-derived guess.

        Lazy-load persisted state on the first frame after a restart so the
        saved timestamps survive reloads.  Doing it here (rather than in
        ``async_setup_backwash_trackers``) avoids a race where the tracker is
        created on the first frame *before* the setup hook has had a chance to
        load its persisted state.
        """
        serial = device.serial_number
        if serial is None:
            return

        if not self._has_backwash(device):
            # no backwash valve on this model (NET, the v8 profiles): no
            # history to keep, and no target for the backwash services
            return

        if serial not in self._backwash_trackers:
            new_tracker = BackwashTracker(self.hass, serial)
            self._backwash_trackers[serial] = new_tracker
            self.hass.async_create_task(new_tracker.load_soon())

        tracker = self._backwash_trackers[serial]
        tracker.update(device, now)
        self._publish_backwash(device, tracker, now)

    @staticmethod
    def _has_backwash(device: AsekoDevice) -> bool:
        """Whether the unit's profile reads a backwash valve.

        The profile says so, not one frame: a unit with the valve keeps its
        tracker through a frame whose relay bit is unknown.
        """
        return "backwash_running" in device.possible_features

    def _update_clock(self, device: AsekoDevice, received_at: datetime) -> None:
        """Compare the unit's clock with Home Assistant's; publish the result."""
        serial = device.serial_number
        if serial is None:
            return
        tracker = self._clock_trackers.get(serial)
        if tracker is None:
            tracker = ClockTracker(
                self.config_entry.options.get(
                    CONF_CLOCK_ALERT_MINUTES, DEFAULT_ALERT_MINUTES
                )
            )
            self._clock_trackers[serial] = tracker
        tracker.update(device.unit_clock, received_at)
        device.clock_offset = tracker.offset_minutes
        device.clock_out_of_sync = tracker.out_of_sync

    @staticmethod
    def _publish_backwash(
        device: AsekoDevice, tracker: BackwashTracker, now: datetime
    ) -> None:
        """Copy the tracker's state onto the device object the entities read."""
        device.last_backwash = tracker.last_backwash
        device.last_scheduled_backwash = tracker.last_scheduled_backwash
        device.last_scheduled_backwash_source = tracker.last_scheduled_source
        device.last_manual_backwash = tracker.last_manual_backwash
        device.last_backwash_trigger = tracker.last_trigger
        device.next_scheduled_backwash = tracker.next_scheduled_backwash(device, now)

    def unit_clock_now(self, serial_number: int | None = None) -> datetime | None:
        """Now on the clock of the units a backwash date is typed in for.

        A typed-in last scheduled backwash is on the unit's clock, so "in the
        future" is judged there: a unit ahead of Home Assistant has already
        run a cycle Home Assistant has not reached, one behind has not.  With
        several units (no ``serial_number``) the earliest of them counts, so
        the value is in the past for every unit it is written to.  A unit
        whose clock is not measured counts as Home Assistant's clock.  Only
        units with a backwash valve count (``_has_backwash``: they are the ones
        with a tracker).  None when this entry has no such unit.
        """
        now = dt_util.now()
        times = [
            now + timedelta(minutes=device.clock_offset or 0.0)
            for device in self.get_devices()
            if device.serial_number in self._backwash_trackers
            and (serial_number is None or device.serial_number == serial_number)
        ]
        return min(times, default=None)

    def set_last_scheduled_backwash(
        self, moment: datetime, serial_number: int | None = None
    ) -> bool:
        """Seed the last scheduled backwash for one device, or for all of them."""
        return self._apply_to_backwash_trackers(
            lambda tracker: tracker.set_last_scheduled_backwash(moment),
            serial_number,
        )

    def clear_last_scheduled_backwash(self, serial_number: int | None = None) -> bool:
        """Forget the last scheduled backwash for one device, or for all of them."""
        return self._apply_to_backwash_trackers(
            lambda tracker: tracker.clear_last_scheduled_backwash(),
            serial_number,
        )

    def _apply_to_backwash_trackers(
        self,
        action: Callable[[BackwashTracker], None],
        serial_number: int | None,
    ) -> bool:
        """Run ``action`` on the matching trackers and republish their state.

        Backs the ``aseko_local.*_last_scheduled_backwash`` services.  Returns
        True if at least one tracker matched, so the service can tell the user
        when a serial number matched nothing.

        The stored device objects are updated in place and listeners notified,
        so the entities reflect the change straight away instead of waiting for
        the next frame.
        """
        if serial_number is not None:
            trackers = {
                serial: tracker
                for serial, tracker in self._backwash_trackers.items()
                if serial == serial_number
            }
        else:
            trackers = dict(self._backwash_trackers)

        if not trackers:
            return False

        # Every target is checked before the first one is written: a tracker
        # whose stored history is still on its way in would have the entry
        # replaced by the stored state, and could not save it either.  Refused
        # as a whole rather than applied to some of the units.  A service
        # spanning several entries asks every one of them first, through
        # ``loading_backwash_serials``, before any of them writes.
        loading = self.loading_backwash_serials(serial_number)
        if loading:
            raise BackwashHistoryLoadingError(loading)

        for serial, tracker in trackers.items():
            action(tracker)
            device = self.get_device(serial)
            if device is not None:
                self._publish_backwash(device, tracker, dt_util.now())

        self.async_update_listeners()
        return True

    def loading_backwash_serials(self, serial_number: int | None = None) -> list[int]:
        """Return the matching units of this entry whose history is not in yet."""
        return sorted(
            serial
            for serial, tracker in self._backwash_trackers.items()
            if (serial_number is None or serial == serial_number) and tracker.loading
        )

    def async_add_new_device_listener(
        self, listener: Callable[[AsekoDevice], None]
    ) -> Callable[[], None]:
        """Register a callback invoked whenever a brand-new device is discovered.

        Returns an unsubscribe callable that removes the listener.
        Platforms call this in async_setup_entry and pass the result to
        config_entry.async_on_unload() so the listener is removed on unload.
        """
        self._new_device_listeners.append(listener)

        def _unsub() -> None:
            self._new_device_listeners.remove(listener)

        return _unsub

    def async_add_new_features_listener(
        self, listener: Callable[[AsekoDevice, frozenset[str]], None]
    ) -> Callable[[], None]:
        """Register a callback for a known device that shows new features.

        Called with the stored device and the names of the AsekoDevice fields
        that were not in its feature set before this frame.  Platforms build
        just the entities for those fields, so a quantity that only becomes
        present after the device was first seen still gets its entity.
        Returns an unsubscribe callable, like ``async_add_new_device_listener``.
        """
        self._new_features_listeners.append(listener)

        def _unsub() -> None:
            self._new_features_listeners.remove(listener)

        return _unsub

    def store_raw_frame(self, raw_frame: bytes) -> None:
        """Cache the last raw frame, keyed by serial number (bytes 0-3).

        Frames shorter than MESSAGE_SIZE are stored as partial frames so users
        with unknown device variants can share the raw data via the Diagnostics
        download without needing to enable debug logging.
        """
        if len(raw_frame) < SERIAL_NUMBER_LENGTH:
            return
        serial = int.from_bytes(raw_frame[:SERIAL_NUMBER_LENGTH], "big")

        if len(raw_frame) < MESSAGE_SIZE:
            self._last_partial_frames[serial] = bytes(raw_frame)
            self._log_frame(KIND_PARTIAL, raw_frame, serial)
        else:
            self._last_raw_frames[serial] = bytes(raw_frame)
            self._log_frame(KIND_V7, raw_frame, serial)

    def store_frame_warning(self, serial_number: int, reason: str) -> None:
        """Count one implausible frame from a unit, by reason, for diagnostics."""
        now = dt_util.utcnow().isoformat()
        reasons = self._frame_warnings.setdefault(serial_number, {})
        if reason not in reasons and len(reasons) >= MAX_WARNING_REASONS - 1:
            # the register stays small whatever a unit sends
            reason = OTHER_WARNING_REASONS
        entry = reasons.setdefault(reason, {"count": 0, "first_seen": now})
        entry["count"] += 1
        entry["last_seen"] = now

    def store_rejected_frame(self, raw_frame: bytes, reason: str) -> None:
        """Log bytes the server could not align into a frame, and count the reason."""
        received = dt_util.utcnow()
        entry = self._rejected_frames.setdefault(
            reason, {"count": 0, "first_seen": received.isoformat()}
        )
        entry["count"] += 1
        entry["last_seen"] = received.isoformat()
        if self.frame_log.enabled:
            self.frame_log.append_frame(received, KIND_REJECTED, raw_frame, reason)
            self._request_frame_log_save()

    def get_rejected_frames(self) -> dict[str, dict[str, Any]]:
        """Why the server rejected bytes it could not align, for diagnostics."""
        return self._rejected_frames

    def get_frame_warnings(self, serial_number: int) -> dict[str, dict[str, Any]]:
        """Return the implausible-frame reasons recorded for a serial number."""
        return self._frame_warnings.get(serial_number, {})

    def get_raw_frame(self, serial_number: int) -> bytes | None:
        """Return the last full raw frame for a given device serial number."""
        return self._last_raw_frames.get(serial_number)

    def get_partial_frame(self, serial_number: int) -> bytes | None:
        """Return the last partial (incomplete) raw frame, if any."""
        return self._last_partial_frames.get(serial_number)

    def store_v8_frame(self, raw_frame: bytes) -> None:
        """Cache the last v8 text frame, keyed by the serial number in the frame text."""
        try:
            text = raw_frame.decode("ascii", errors="replace").strip()
            # Frame starts with "{v1 <serial> ..."
            serial: int | None = int(text.lstrip("{").split()[1])
            self._last_v8_frames[serial] = bytes(raw_frame)
        except (ValueError, IndexError):
            serial = None
        self._log_frame(KIND_V8, raw_frame, serial)

    # -- frame log -----------------------------------------------------------

    async def async_load_frame_log(self) -> None:
        """Restore the frame log saved before the last restart."""
        self._frame_log_store = Store(
            self.hass,
            FRAME_LOG_STORAGE_VERSION,
            f"{FRAME_LOG_STORAGE_KEY_PREFIX}{self.config_entry.entry_id}",
        )
        data = await self._frame_log_store.async_load()
        if data:
            self.frame_log.load_store(data)

    async def async_save_frame_log(self) -> None:
        """Write the frame log now (on unload)."""
        if self._frame_log_store is not None:
            await self._frame_log_store.async_save(self.frame_log.to_store())

    def _log_frame(self, kind: str, raw_frame: bytes, serial: int | None) -> None:
        received = dt_util.utcnow()
        if self.frame_log.enabled:
            self.frame_log.append_frame(received, kind, raw_frame)
        if serial is not None:
            self._last_frame_at[serial] = received
        if self.frame_log.enabled:
            self._request_frame_log_save()

    async def async_wait_for_frame(
        self, seconds: float, serial_number: int | None = None
    ) -> bool:
        """Wait for the next whole frame; False if none came in time.

        With ``serial_number`` only a frame from that unit counts; without it,
        a frame from any unit of this entry.
        """
        waiter: asyncio.Future[None] = self.hass.loop.create_future()
        item = (waiter, serial_number)
        self._frame_waiters.append(item)
        try:
            await asyncio.wait_for(waiter, seconds)
        except TimeoutError:
            return False
        finally:
            if item in self._frame_waiters:
                self._frame_waiters.remove(item)
        return True

    def seconds_since_last_frame(self, now: datetime) -> dict[int, float]:
        """How long ago each unit's last frame arrived, by serial number."""
        return {
            serial: round((now - received).total_seconds(), 1)
            for serial, received in self._last_frame_at.items()
        }

    def _request_frame_log_save(self, delay: float = FRAME_LOG_SAVE_DELAY) -> None:
        """Save the log soon, but at most once per interval while frames flow.

        Store.async_delay_save restarts its timer on every call, so calling it
        for every frame would postpone the write forever.  The store also
        writes the latest state when Home Assistant stops.
        """
        if self._frame_log_store is None:
            return
        now = dt_util.utcnow()
        if (
            delay >= FRAME_LOG_SAVE_DELAY
            and self._frame_log_save_requested is not None
            and now - self._frame_log_save_requested < FRAME_LOG_SAVE_INTERVAL
        ):
            return
        self._frame_log_save_requested = now
        self._frame_log_store.async_delay_save(self.frame_log.to_store, delay)

    async def async_mark_after_frame(
        self,
        note: str | None,
        extra: dict[str, Any],
        *,
        wait: bool,
        serial_number: int | None,
        generation: int,
    ) -> dict[str, Any] | None:
        """Wait for the next frame when asked, then write a marker.

        Shared by ``mark_dump`` and the photo upload.  Returns the marker with
        ``waited_for_frame``, or None when recording was stopped or deleted
        while waiting (the generation moved on).
        """
        waited = None
        if wait:
            waited = await self.async_wait_for_frame(
                MARK_DUMP_WAIT_TIMEOUT, serial_number
            )
        try:
            marker = self.mark_dump(
                note,
                {**extra, "serial_number": serial_number, "waited_for_frame": waited},
                generation=generation,
            )
        except RecordingOffError:
            return None
        return {**marker, "waited_for_frame": waited}

    def mark_dump(
        self,
        note: str | None = None,
        extra: dict[str, Any] | None = None,
        generation: int | None = None,
    ) -> dict[str, Any]:
        """Write a numbered marker into the frame log and describe it.

        The marker records how many seconds ago each unit's last frame
        arrived, so a reader can tell whether the change it marks could
        already be in that frame.  Raises ``RecordingOffError`` while the frame log
        is off: a marker with no frames around it says nothing.

        ``generation`` is ``recording_generation`` from before a wait: when
        recording was stopped or deleted since, the mark raises
        ``RecordingOffError`` instead of landing in a different recording.
        """
        if not self.frame_log.enabled or (
            generation is not None and generation != self.recording_generation
        ):
            raise RecordingOffError
        received = dt_util.utcnow()
        since = self.seconds_since_last_frame(received)
        number = self.frame_log.append_marker(
            received,
            note,
            {str(serial): age for serial, age in since.items()},
            extra,
        )
        _LOGGER.info(
            "Aseko frame log marker %s at %s %s (last frame %s s ago)",
            number,
            received,
            note or "",
            since,
        )
        self._request_frame_log_save(delay=5)
        return {
            "marker": number,
            "time": received,
            "seconds_since_last_frame": since,
        }

    def mark_exported(self, through: int) -> None:
        """Record that markers up to ``through`` were downloaded, and save."""
        self.frame_log.mark_exported(through)
        self._request_frame_log_save(delay=5)

    def set_recording(self, *, enabled: bool) -> None:
        """Turn the frame log on or off; what it holds stays."""
        if not enabled:
            self.recording_generation += 1
        self.frame_log.enabled = enabled
        _LOGGER.info("Aseko frame log recording %s", "on" if enabled else "off")
        self._request_frame_log_save(delay=5)

    def clear_recording(self) -> None:
        """Delete every recorded frame and case of this entry."""
        self.recording_generation += 1
        self.frame_log.clear()
        self._request_frame_log_save(delay=5)

    def forget_markers(self) -> None:
        """Clear the list of cases shown on the test cases card, and save."""
        self.frame_log.forget_markers()
        self._request_frame_log_save(delay=5)

    def get_v8_frame(self, serial_number: int) -> bytes | None:
        """Return the last raw v8 text frame for a given device serial number."""
        return self._last_v8_frames.get(serial_number)

    def get_unrecognised_devices(self) -> list[AsekoDevice]:
        """Return the units whose type nobody has mapped, as last decoded."""
        return list(self._unrecognised_devices.values())

    def get_tracker(self, serial_number: int) -> AsekoConsumptionTracker | None:
        """Return the consumption tracker for a given device serial number."""
        return self._trackers.get(serial_number)

    def reset_consumption(
        self, pump_key: str, counter: str, serial_number: int | None = None
    ) -> None:
        """Reset consumption counters of one unit, or of every unit without a serial."""
        for serial, tracker in self._trackers.items():
            if serial_number is None or serial == serial_number:
                tracker.reset(pump_key=pump_key, counter=counter)
        self._request_consumption_save(now=True)
        self.async_update_listeners()

    # -- consumption store ---------------------------------------------------

    async def async_load_consumption(self) -> None:
        """Restore the exact consumption counters saved before the last restart.

        The sensors restore only rounded litres; with this store they are not
        needed, and a tracker loaded from it ignores them.
        """
        self._consumption_store = Store(
            self.hass,
            CONSUMPTION_STORAGE_VERSION,
            f"{CONSUMPTION_STORAGE_KEY_PREFIX}{self.config_entry.entry_id}",
        )
        data = await self._consumption_store.async_load()
        if not isinstance(data, dict):
            return
        for serial, counters in data.items():
            try:
                serial_number = int(serial)
            except (TypeError, ValueError):
                continue
            if not isinstance(counters, dict):
                continue
            tracker = self._trackers.setdefault(
                serial_number, AsekoConsumptionTracker()
            )
            tracker.load_store(counters)

    def _consumption_data(self) -> dict[str, Any]:
        return {str(serial): t.to_store() for serial, t in self._trackers.items()}

    def _request_consumption_save(self, *, now: bool = False) -> None:
        """Save the counters soon; at most once a minute while pumps run."""
        if self._consumption_store is None:
            return
        stamp = dt_util.utcnow()
        if (
            not now
            and self._consumption_saved_at is not None
            and stamp - self._consumption_saved_at < CONSUMPTION_SAVE_INTERVAL
        ):
            return
        self._consumption_saved_at = stamp
        self._consumption_store.async_delay_save(
            self._consumption_data, 1 if now else 30
        )

    async def async_save_consumption(self) -> None:
        """Write the counters now (on unload)."""
        if self._consumption_store is not None:
            await self._consumption_store.async_save(self._consumption_data())

    def get_device(self, serial_number: int) -> AsekoDevice | None:
        """Return the stored device of one serial number, or None."""
        _LOGGER.debug("get_device(%s) called", serial_number)
        return self.data.get(serial_number) if self.data is not None else None

    def get_devices(self) -> list[AsekoDevice]:
        """Return every stored device of this entry."""
        devices = self.data.get_all() if self.data is not None else []
        _LOGGER.debug(
            "get_devices() → %s devices: %s",
            len(devices),
            [d.serial_number for d in devices],
        )
        return devices

    async def async_setup_backwash_trackers(self) -> None:
        """Pre-load persisted backwash timestamps from storage.

        This is a best-effort warm-up: trackers are also created
        lazily on the first received frame in
        :meth:`devices_update_callback`, which is the only path that
        matters because the integration does not know device serials
        before any frame arrives.  This method just gives already-known
        devices a head start on loading from disk.
        """
        if self.data is None:
            return
        for device in self.data.get_all():
            serial = device.serial_number
            if (
                serial is None
                or serial in self._backwash_trackers
                or not self._has_backwash(device)
            ):
                continue
            tracker = BackwashTracker(self.hass, serial)
            self._backwash_trackers[serial] = tracker
            await tracker.load_soon()

    def async_start_stale_check(self) -> None:
        """Start a periodic task that pushes updates so entities detect offline state."""
        self._stale_check_unsub = async_track_time_interval(
            self.hass,
            self._async_check_stale,
            timedelta(seconds=30),
        )

    @callback
    def _async_check_stale(self, _now: object) -> None:
        """Re-push current data so entities re-evaluate device.online()."""
        if self.data is not None:
            self.async_set_updated_data(self.data)

    def async_stop_stale_check(self) -> None:
        """Stop the periodic stale check."""
        if self._stale_check_unsub is not None:
            self._stale_check_unsub()
            self._stale_check_unsub = None
