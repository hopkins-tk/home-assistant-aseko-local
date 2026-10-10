"""The coordinator's edges: odd devices, backwash services, stores and the stale check.

Run with a mock ``hass`` like ``test_entity_growth``; Home Assistant's
``Store`` is replaced by an in-memory one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.aseko_local import coordinator as coordinator_module
from custom_components.aseko_local.const import UNIT_TYPE_HOME_CLF, UNIT_TYPE_NET
from custom_components.aseko_local.coordinator import (
    CONSUMPTION_SAVE_INTERVAL,
    FRAME_LOG_SAVE_INTERVAL,
    BackwashHistoryLoadingError,
)
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.models import AsekoDevice, AsekoDeviceType
from custom_components.aseko_local.trackers.consumption import AsekoConsumptionTracker

from .test_decode_v7 import _make_base_bytes
from .test_entity_growth import SERIAL, _coordinator, _loaded, _salt_frame

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class FakeStore:
    """In-memory stand-in for ``homeassistant.helpers.storage.Store``."""

    # what async_load returns, for every store created afterwards
    initial: object = None

    def __init__(self, hass: object, version: int, key: str) -> None:
        self.key = key
        self.data: object = self.initial
        self.saved: list[object] = []
        self.delayed: list[float] = []

    async def async_load(self) -> object:
        return self.data

    async def async_save(self, data: object) -> None:
        self.saved.append(data)

    def async_delay_save(self, data_func, delay: float) -> None:
        self.delayed.append(delay)
        self.saved.append(data_func())


@pytest.fixture
def fake_store(monkeypatch) -> type[FakeStore]:
    monkeypatch.setattr(coordinator_module, "Store", FakeStore)
    monkeypatch.setattr(FakeStore, "initial", None)
    return FakeStore


def _coordinator_with_salt() -> coordinator_module.AsekoLocalDataUpdateCoordinator:
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    return _loaded(coordinator)


# -- odd devices and listeners ------------------------------------------------


def test_a_device_without_a_serial_number_is_not_stored() -> None:
    coordinator = _coordinator()
    device = AsekoDevice(device_type=AsekoDeviceType.SALT)  # no serial number

    coordinator.devices_update_callback(device)
    coordinator._keep_unrecognised(AsekoDevice())  # nor as an unrecognised unit
    coordinator._update_backwash(device, T0)
    coordinator._update_clock(device, T0)

    assert coordinator.data is None
    assert coordinator.get_unrecognised_devices() == []
    assert coordinator._backwash_trackers == {}
    assert coordinator._clock_trackers == {}


@pytest.mark.asyncio
async def test_a_wait_already_ended_is_skipped_and_other_units_keep_waiting() -> None:
    coordinator = _coordinator()
    loop = asyncio.get_running_loop()
    done = loop.create_future()
    done.set_result(None)
    other = loop.create_future()
    coordinator._frame_waiters = [(done, None), (other, 9999)]

    coordinator._release_frame_waiters(SERIAL)

    assert coordinator._frame_waiters == [(other, 9999)]
    assert not other.done()


def test_a_failing_listener_does_not_stop_the_others() -> None:
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    seen: list[int | None] = []

    def broken(device: AsekoDevice) -> None:
        msg = "listener bug"
        raise RuntimeError(msg)

    coordinator.async_add_new_device_listener(broken)
    unsub = coordinator.async_add_new_device_listener(
        lambda device: seen.append(device.serial_number)
    )
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    assert seen == [SERIAL]

    unsub()
    assert len(coordinator._new_device_listeners) == 1


def test_frames_too_short_or_with_an_unreadable_serial_are_not_filed() -> None:
    coordinator = _coordinator()
    coordinator.set_recording(enabled=True)

    coordinator.store_raw_frame(b"\x00\x01")  # not even a serial number
    coordinator.store_v8_frame(b"{v1 notanumber 804}\n")

    assert coordinator._last_raw_frames == {}
    assert coordinator._last_partial_frames == {}
    assert coordinator._last_v8_frames == {}
    assert [r["k"] for r in coordinator.frame_log.records()] == ["v8"]
    assert coordinator.seconds_since_last_frame(dt_util.utcnow()) == {}


# -- backwash services -----------------------------------------------------------


def test_backwash_services_report_when_no_unit_matches() -> None:
    coordinator = _coordinator()
    assert coordinator.set_last_scheduled_backwash(T0) is False
    assert coordinator.clear_last_scheduled_backwash() is False

    coordinator = _coordinator_with_salt()
    assert coordinator.set_last_scheduled_backwash(T0, serial_number=9999) is False
    assert coordinator.clear_last_scheduled_backwash(serial_number=9999) is False


def test_setting_the_last_scheduled_backwash_publishes_it_at_once() -> None:
    coordinator = _coordinator_with_salt()
    updates: list[None] = []
    coordinator.async_add_listener(lambda: updates.append(None))
    moment = dt_util.now() - timedelta(days=1)

    assert coordinator.set_last_scheduled_backwash(moment, serial_number=SERIAL)
    assert coordinator.get_device(SERIAL).last_scheduled_backwash == moment
    assert updates == [None]

    assert coordinator.clear_last_scheduled_backwash()  # every unit
    assert coordinator.get_device(SERIAL).last_scheduled_backwash is None
    assert updates == [None, None]


def test_a_tracker_without_a_stored_device_is_changed_but_not_published() -> None:
    coordinator = _coordinator_with_salt()
    coordinator.data.devices.clear()

    assert coordinator.set_last_scheduled_backwash(dt_util.now() - timedelta(days=1))
    assert coordinator._backwash_trackers[SERIAL].last_scheduled_backwash is not None


@pytest.mark.asyncio
async def test_backwash_trackers_are_warmed_up_for_known_devices(monkeypatch) -> None:
    coordinator = _coordinator()
    await coordinator.async_setup_backwash_trackers()  # nothing known yet
    assert coordinator._backwash_trackers == {}

    loaded: list[int] = []

    class FakeTracker:
        def __init__(self, hass: object, serial: int) -> None:
            self.serial = serial

        async def load_soon(self) -> None:
            loaded.append(self.serial)

    coordinator = _coordinator_with_salt()
    known = coordinator._backwash_trackers[SERIAL]
    coordinator.data.set(
        42,
        AsekoDevice(
            serial_number=42, possible_features=frozenset({"backwash_running"})
        ),
    )
    coordinator.data.set(43, AsekoDevice(serial_number=43))  # no valve
    coordinator.data.set(0, AsekoDevice())
    monkeypatch.setattr(coordinator_module, "BackwashTracker", FakeTracker)

    await coordinator.async_setup_backwash_trackers()

    assert loaded == [42]
    assert coordinator._backwash_trackers[SERIAL] is known


def test_a_history_still_being_read_refuses_the_service_and_keeps_its_state() -> None:
    """Audit F2: the finishing load would replace a typed-in date; refuse instead."""
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    tracker = coordinator._backwash_trackers[SERIAL]
    assert tracker.loading is True  # the mock hass never runs the load

    with pytest.raises(BackwashHistoryLoadingError, match=str(SERIAL)):
        coordinator.set_last_scheduled_backwash(T0)
    with pytest.raises(BackwashHistoryLoadingError):
        coordinator.clear_last_scheduled_backwash(serial_number=SERIAL)

    assert tracker.last_scheduled_backwash is None
    assert _loaded(coordinator).set_last_scheduled_backwash(T0) is True


def test_one_unit_still_reading_its_history_stops_the_whole_service() -> None:
    coordinator = _coordinator_with_salt()  # its tracker is loaded
    coordinator.devices_update_callback(_frame(UNIT_TYPE_HOME_CLF, 4321))
    assert coordinator._backwash_trackers[4321].loading is True

    with pytest.raises(BackwashHistoryLoadingError, match="4321"):
        coordinator.set_last_scheduled_backwash(T0)

    assert coordinator._backwash_trackers[SERIAL].last_scheduled_backwash is None


# -- units without a backwash valve (audit A2) ------------------------------------

NET_SERIAL = 5678
NET_CLF = UNIT_TYPE_NET + 1  # a NET with a CLF probe


def _frame(unit_type: int, serial: int) -> AsekoDevice:
    data = _make_base_bytes()
    data[0:4] = serial.to_bytes(4, "big")
    data[4] = unit_type
    return decode(bytes(data))


def test_a_net_gets_no_backwash_tracker_and_is_no_service_target() -> None:
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(_frame(NET_CLF, NET_SERIAL))

    assert coordinator._backwash_trackers == {}
    assert coordinator.unit_clock_now() is None
    assert (
        coordinator.set_last_scheduled_backwash(T0, serial_number=NET_SERIAL) is False
    )
    assert coordinator.clear_last_scheduled_backwash(serial_number=NET_SERIAL) is False
    assert coordinator.set_last_scheduled_backwash(T0) is False


def test_with_a_home_and_a_net_only_the_home_clock_counts(monkeypatch) -> None:
    now = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "now", lambda: now)
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(_frame(UNIT_TYPE_HOME_CLF, SERIAL))
    coordinator.devices_update_callback(_frame(NET_CLF, NET_SERIAL))
    _loaded(coordinator)
    coordinator.get_device(SERIAL).clock_offset = 60.0
    coordinator.get_device(NET_SERIAL).clock_offset = 0.0

    assert set(coordinator._backwash_trackers) == {SERIAL}
    assert coordinator.unit_clock_now() == now + timedelta(hours=1)
    assert coordinator.set_last_scheduled_backwash(now + timedelta(minutes=30))
    assert (
        coordinator.set_last_scheduled_backwash(now, serial_number=NET_SERIAL) is False
    )


def test_a_frame_with_an_unknown_relay_keeps_the_tracker() -> None:
    coordinator = _coordinator_with_salt()
    tracker = coordinator._backwash_trackers[SERIAL]
    device = decode(_salt_frame(0xD3))
    device.backwash_running = None

    coordinator.devices_update_callback(device)

    assert coordinator._backwash_trackers[SERIAL] is tracker


def test_a_known_unit_reuses_its_consumption_tracker(monkeypatch) -> None:
    coordinator = _coordinator_with_salt()
    built: list[None] = []

    class CountingTracker(AsekoConsumptionTracker):
        def __init__(self) -> None:
            built.append(None)
            super().__init__()

    monkeypatch.setattr(coordinator_module, "AsekoConsumptionTracker", CountingTracker)
    for _ in range(5):
        coordinator.devices_update_callback(decode(_salt_frame(0xD3)))

    assert built == []
    assert list(coordinator._trackers) == [SERIAL]


# -- frame log store ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_frame_log_is_restored_and_saved(fake_store) -> None:
    coordinator = _coordinator()
    await coordinator.async_save_frame_log()  # no store yet: nothing to do

    saved = _coordinator()
    saved.set_recording(enabled=True)
    saved.store_raw_frame(bytes(120))

    await coordinator.async_load_frame_log()
    store = coordinator._frame_log_store
    assert store.key.startswith("aseko_local_frame_log_")
    assert coordinator.frame_log.records() == []  # empty store: nothing restored

    fake_store.initial = saved.frame_log.to_store()
    await coordinator.async_load_frame_log()
    assert [r["k"] for r in coordinator.frame_log.records()] == ["v7"]

    await coordinator.async_save_frame_log()
    assert coordinator._frame_log_store.saved


@pytest.mark.asyncio
async def test_frame_log_saves_are_throttled_while_frames_flow(
    fake_store, monkeypatch
) -> None:
    coordinator = _coordinator()
    await coordinator.async_load_frame_log()
    store = coordinator._frame_log_store
    now = [T0]
    monkeypatch.setattr(dt_util, "utcnow", lambda: now[0])

    coordinator.set_recording(enabled=True)  # a user action: saved soon
    coordinator.store_raw_frame(bytes(120))  # within the interval: no new request
    coordinator.store_raw_frame(bytes(120))
    assert store.delayed == [5]

    now[0] = T0 + FRAME_LOG_SAVE_INTERVAL + timedelta(seconds=1)
    coordinator.store_raw_frame(bytes(120))
    coordinator.store_raw_frame(bytes(120))
    assert store.delayed == [5, 60]

    coordinator.mark_dump("marker")  # a marker never waits for the interval
    assert store.delayed == [5, 60, 5]


# -- consumption store --------------------------------------------------------------


@pytest.mark.asyncio
async def test_consumption_counters_are_restored_skipping_broken_entries(
    fake_store,
) -> None:
    stored = {
        str(SERIAL): {"ph_minus": {"total": 1500.0, "canister": 500.0}},
        "not a serial": {"ph_minus": {"total": 1.0}},
        "42": "not counters",
    }
    fake_store.initial = stored
    coordinator = _coordinator()

    await coordinator.async_load_consumption()

    assert coordinator._consumption_store.key.startswith("aseko_local_consumption_")
    assert set(coordinator._trackers) == {SERIAL}
    assert coordinator.get_tracker(SERIAL).get("ph_minus", "total") == 1500.0


@pytest.mark.asyncio
async def test_an_empty_consumption_store_restores_nothing(fake_store) -> None:
    coordinator = _coordinator()
    await coordinator.async_load_consumption()
    assert coordinator._trackers == {}


@pytest.mark.asyncio
async def test_consumption_saves_are_throttled_unless_reset(
    fake_store, monkeypatch
) -> None:
    coordinator = _coordinator()
    await coordinator.async_save_consumption()  # no store yet: nothing to do
    await coordinator.async_load_consumption()
    store = coordinator._consumption_store
    now = [T0]
    monkeypatch.setattr(dt_util, "utcnow", lambda: now[0])
    coordinator._trackers[SERIAL] = AsekoConsumptionTracker()

    coordinator._request_consumption_save()
    coordinator._request_consumption_save()  # pumps still running: throttled
    assert store.delayed == [30]

    now[0] = T0 + CONSUMPTION_SAVE_INTERVAL + timedelta(seconds=1)
    coordinator._request_consumption_save()
    assert store.delayed == [30, 30]

    coordinator.reset_consumption("ph_minus", "canister")  # a reset saves at once
    assert store.delayed == [30, 30, 1]

    await coordinator.async_save_consumption()
    assert store.saved[-1] == {str(SERIAL): coordinator.get_tracker(SERIAL).to_store()}


# -- stale check --------------------------------------------------------------------


def test_the_stale_check_repushes_data_until_stopped(monkeypatch) -> None:
    unsubscribed: list[None] = []
    scheduled: list[tuple[object, timedelta]] = []

    def track(hass, action, interval) -> Callable[[], None]:
        scheduled.append((action, interval))
        return lambda: unsubscribed.append(None)

    monkeypatch.setattr(coordinator_module, "async_track_time_interval", track)
    coordinator = _coordinator()
    updates: list[None] = []
    coordinator.async_add_listener(lambda: updates.append(None))

    coordinator.async_start_stale_check()
    assert scheduled[0][1] == timedelta(seconds=30)

    coordinator._async_check_stale(None)  # no data yet: nothing to push
    assert updates == []

    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    updates.clear()
    coordinator._async_check_stale(None)
    assert updates == [None]

    coordinator.async_stop_stale_check()
    coordinator.async_stop_stale_check()  # already stopped
    assert unsubscribed == [None]
