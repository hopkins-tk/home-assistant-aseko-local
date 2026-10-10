"""Test Aseko Local setup process."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from unittest.mock import AsyncMock, call, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aseko_local import (
    SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH,
    SERVICE_MARK_DUMP,
    SERVICE_RESET_CONSUMPTION,
    SERVICE_SET_LAST_SCHEDULED_BACKWASH,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.aseko_local.const import (
    CONF_FORWARDER_ENABLED,
    CONF_FORWARDER_HOST,
    DEFAULT_FORWARDER_PORT_V7,
    DEFAULT_FORWARDER_PORT_V8,
    DOMAIN,
)
from custom_components.aseko_local.coordinator import (
    AsekoLocalDataUpdateCoordinator,
)
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.forwarder import AsekoCloudMirror
from custom_components.aseko_local.models import AsekoDevice, AsekoDeviceType
from custom_components.aseko_local.server import (
    AsekoDeviceServer,
)
from custom_components.aseko_local.trackers.backwash import BackwashTracker

from .conftest import FakeListener
from .const import MOCK_CONFIG
from .test_decode_v7 import _make_base_bytes


# We can pass fixtures as defined in conftest.py to tell pytest to use the fixture
# for a given test. We can also leverage fixtures and mocks that are available in
# Home Assistant using the pytest_homeassistant_custom_component plugin.
# Assertions allow you to verify that the return value of whatever is on the left
# side of the assertion matches with the right side.
async def test_setup_unload_entry(hass, bypass_get_data, api_server_running) -> None:
    """Test entry setup and unload."""

    # Create a mock entry so we don't have to go through config flow
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="test", state=ConfigEntryState.LOADED
    )

    # Set up the entry and assert that the values set during setup are where we expect
    # them to be. Because we have patched the AsekoLocalDataUpdateCoordinator.async_get_data
    # call, no code from custom_components/aseko_local/server.py actually runs.
    assert await async_setup_entry(hass, config_entry)

    # Unload the entry so the coordinator's periodic stale-check timer is
    # stopped. pytest_homeassistant_custom_component fails any test that
    # leaves a lingering timer behind (async_track_time_interval started in
    # async_start_stale_check).
    assert await async_unload_entry(hass, config_entry)


# Hilfsfunktion: Hex-String zu Bytes
def hexstr_to_bytes(s: str) -> bytes:
    return bytes.fromhex(s.replace("\n", "").replace(" ", ""))


VALID_FRAME_HEX = (
    "069187240901ffffffffffff000402da0027ffff0095ff01400149ff000006640000000000ff006c"
    "069187240903ffffffffffff480a08ffffffffffffffffff027e0149ffffffffffffffffffffffea"
    "069187240902ffffffffffff0001003cffff003cffff010383ff00781e02581e28ffffffff0049a9"
)
VALID_FRAME = hexstr_to_bytes(VALID_FRAME_HEX[:240])  # MESSAGE_SIZE = 120


@pytest.mark.asyncio
async def test_device_recognition(monkeypatch) -> None:
    """Test: First frame creates new device, second frame is recognized as known."""

    await AsekoDeviceServer.remove_all()
    devices = {}

    async def on_data(device: AsekoDevice) -> None:
        # Save device by serial number
        devices[device.serial_number] = device

    class DummyWriter:
        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

        def get_extra_info(self, name: str) -> tuple[str, int] | None:
            if name == "peername":
                return ("127.0.0.1", 12345)
            return None

    class DummyServer:
        def is_serving(self) -> bool:
            return True

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    async def dummy_start_server(handler, host, port) -> DummyServer:
        reader = asyncio.StreamReader()
        writer = DummyWriter()
        # Send two valid frames
        reader.feed_data(VALID_FRAME)
        reader.feed_data(VALID_FRAME)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12345, on_data=on_data
    )
    assert server.running
    # It should have recognized one device
    assert len(devices) == 1
    assert 110200612 in devices  # Example serial number from frame
    await server.stop()


# ---------------------------------------------------------------------------
# Multi-device listener tests (fix for issue #99)
# ---------------------------------------------------------------------------


def _make_device(serial: int) -> AsekoDevice:
    """Return a minimal AsekoDevice with the given serial number."""
    device = AsekoDevice()
    device.serial_number = serial
    device.device_type = AsekoDeviceType.NET
    return device


@pytest.mark.asyncio
async def test_coordinator_new_device_listener_called_for_new_device(hass) -> None:
    """Listener is called exactly once when a brand-new device arrives."""

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test_listener")
    entry.add_to_hass(hass)

    coordinator = AsekoLocalDataUpdateCoordinator(hass, entry)
    discovered: list[AsekoDevice] = []

    unsub = coordinator.async_add_new_device_listener(discovered.append)

    device = _make_device(111)
    coordinator.devices_update_callback(device)

    assert len(discovered) == 1
    assert discovered[0].serial_number == 111

    # Second update for the SAME device must NOT trigger the listener again
    coordinator.devices_update_callback(device)
    assert len(discovered) == 1

    unsub()


@pytest.mark.asyncio
async def test_coordinator_new_device_listener_unsub(hass) -> None:
    """Unsubscribing the listener stops it from receiving future discoveries."""

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test_unsub")
    entry.add_to_hass(hass)

    coordinator = AsekoLocalDataUpdateCoordinator(hass, entry)
    discovered: list[AsekoDevice] = []

    unsub = coordinator.async_add_new_device_listener(discovered.append)
    unsub()  # unsubscribe immediately

    coordinator.devices_update_callback(_make_device(222))
    assert len(discovered) == 0


@pytest.mark.asyncio
async def test_coordinator_multiple_listeners(hass) -> None:
    """All registered listeners receive the new-device notification."""

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test_multi_cb")
    entry.add_to_hass(hass)

    coordinator = AsekoLocalDataUpdateCoordinator(hass, entry)
    bucket_a: list[int] = []
    bucket_b: list[int] = []

    unsub_a = coordinator.async_add_new_device_listener(
        lambda d: bucket_a.append(d.serial_number)
    )
    unsub_b = coordinator.async_add_new_device_listener(
        lambda d: bucket_b.append(d.serial_number)
    )

    coordinator.devices_update_callback(_make_device(333))
    coordinator.devices_update_callback(_make_device(444))

    assert bucket_a == [333, 444]
    assert bucket_b == [333, 444]

    unsub_a()
    unsub_b()


# ---------------------------------------------------------------------------
# set-up: server not listening, platform set-up retries, cloud mirrors
# ---------------------------------------------------------------------------


def _entry(
    hass, entry_id: str = "entry", port: int = 12410, options: dict | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"Aseko {entry_id}",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port},
        options=options or {},
        entry_id=entry_id,
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded_entry(hass, listeners) -> AsyncIterator[MockConfigEntry]:
    """Set up an entry whose platforms are never really forwarded."""
    await AsekoDeviceServer.remove_all()
    entry = _entry(hass)
    with patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    ) as forward:
        assert await async_setup_entry(hass, entry)
        entry.forward = forward
        yield entry
        await async_unload_entry(hass, entry)


def _salt_device(serial: int = 1234) -> AsekoDevice:
    data = _make_base_bytes()
    data[0:4] = serial.to_bytes(4, "big")
    return decode(bytes(data))


async def test_setup_is_retried_when_the_server_does_not_listen(
    hass, bypass_get_data, api_server_not_running
) -> None:
    await AsekoDeviceServer.remove_all()
    entry = _entry(hass, "not_listening")

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    await AsekoDeviceServer.remove_all()


async def test_setup_is_retried_when_the_port_cannot_be_bound(
    hass, monkeypatch
) -> None:
    """A port still held after a restart retries the set-up instead of failing it."""
    await AsekoDeviceServer.remove_all()
    busy = [True]

    async def start_server(handler, host, port) -> object:
        if busy[0]:
            msg = "address already in use"
            raise OSError(msg)
        return FakeListener()

    monkeypatch.setattr(asyncio, "start_server", start_server)
    entry = _entry(hass, "busy_port", 12413)

    with pytest.raises(ConfigEntryNotReady, match=r"127\.0\.0\.1:12413"):
        await async_setup_entry(hass, entry)
    assert AsekoDeviceServer.get("127.0.0.1", 12413) is None  # nothing left behind

    busy[0] = False  # the old socket is released: the retry listens
    assert await async_setup_entry(hass, entry)
    server = entry.runtime_data.server
    assert server.running
    assert server.on_data == entry.runtime_data.coordinator.devices_update_callback
    assert await async_unload_entry(hass, entry)


async def test_platforms_are_set_up_once_for_a_whole_first_device(
    hass, loaded_entry
) -> None:
    rd = loaded_entry.runtime_data
    new_device = rd.coordinator.cb_new_device

    await new_device(AsekoDevice(serial_number=1234))  # no model yet: wait
    assert loaded_entry.forward.await_count == 0
    assert rd.device_discovered is False

    await new_device(_salt_device())
    await new_device(_salt_device())  # already set up
    assert loaded_entry.forward.await_count == 1
    assert rd.device_discovered is True
    assert rd.coordinator.platforms_ready is True


async def test_a_failed_platform_setup_is_retried_and_logged_once_a_minute(
    hass, loaded_entry, caplog
) -> None:
    rd = loaded_entry.runtime_data
    loaded_entry.forward.side_effect = RuntimeError("platform bug")

    await rd.coordinator.cb_new_device(_salt_device())
    await rd.coordinator.cb_new_device(_salt_device())

    assert loaded_entry.forward.await_count == 2  # asked again on the next frame
    assert rd.device_discovered is False
    assert rd.coordinator.platforms_ready is False
    assert caplog.text.count("Setting up the Aseko Local entities failed") == 1


async def test_a_device_callback_before_the_runtime_data_is_ignored(
    hass, loaded_entry
) -> None:
    rd = loaded_entry.runtime_data
    loaded_entry.runtime_data = None
    try:
        await rd.coordinator.cb_new_device(_salt_device())
    finally:
        loaded_entry.runtime_data = rd
    assert loaded_entry.forward.await_count == 0


async def test_cloud_mirrors_start_with_the_options_and_stop_on_unload(
    hass, listeners
) -> None:
    await AsekoDeviceServer.remove_all()
    entry = _entry(
        hass,
        "mirrored",
        options={CONF_FORWARDER_ENABLED: True, CONF_FORWARDER_HOST: "cloud.test"},
    )
    with (
        patch.object(AsekoCloudMirror, "start", AsyncMock()) as start,
        patch.object(AsekoCloudMirror, "stop", AsyncMock()) as stop,
    ):
        assert await async_setup_entry(hass, entry)
        rd = entry.runtime_data
        assert (rd.mirror._host, rd.mirror._port) == (
            "cloud.test",
            DEFAULT_FORWARDER_PORT_V7,
        )
        assert rd.mirror_v8._port == DEFAULT_FORWARDER_PORT_V8
        assert rd.server._forward_cb == rd.mirror.enqueue
        assert rd.server._forward_v8_cb == rd.mirror_v8.enqueue
        assert start.await_count == 2

        assert await async_unload_entry(hass, entry)
        assert stop.await_count == 2


async def test_a_mirror_without_a_host_is_not_started(hass, listeners, caplog) -> None:
    await AsekoDeviceServer.remove_all()
    entry = _entry(
        hass, "no_host", options={CONF_FORWARDER_ENABLED: True, CONF_FORWARDER_HOST: ""}
    )
    assert await async_setup_entry(hass, entry)

    assert entry.runtime_data.mirror is None
    assert entry.runtime_data.mirror_v8 is None
    assert "Forwarder enabled but host not set" in caplog.text
    assert await async_unload_entry(hass, entry)


# ---------------------------------------------------------------------------
# unload
# ---------------------------------------------------------------------------


async def test_unload_removes_platforms_and_services_only_with_the_last_entry(
    hass, listeners
) -> None:
    await AsekoDeviceServer.remove_all()
    first = _entry(hass, "first", 12411)
    second = _entry(hass, "second", 12412)
    assert await async_setup_entry(hass, first)
    assert await async_setup_entry(hass, second)
    first.runtime_data.device_discovered = True  # its platforms were set up

    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    ) as unload_platforms:
        assert await async_unload_entry(hass, first)
    unload_platforms.assert_awaited_once()
    assert hass.services.has_service(DOMAIN, SERVICE_MARK_DUMP)

    await hass.config_entries.async_remove(first.entry_id)
    assert await async_unload_entry(hass, second)
    for service in (
        SERVICE_RESET_CONSUMPTION,
        SERVICE_SET_LAST_SCHEDULED_BACKWASH,
        SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH,
        SERVICE_MARK_DUMP,
    ):
        assert not hass.services.has_service(DOMAIN, service)


async def test_a_failed_platform_unload_keeps_the_server(hass, loaded_entry) -> None:
    loaded_entry.runtime_data.device_discovered = True
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    ):
        assert await async_unload_entry(hass, loaded_entry) is False
    assert loaded_entry.runtime_data.server.running
    loaded_entry.runtime_data.device_discovered = False


# ---------------------------------------------------------------------------
# services
# ---------------------------------------------------------------------------


async def test_reset_consumption_service_resets_the_chosen_unit(
    hass, loaded_entry
) -> None:
    coordinator = loaded_entry.runtime_data.coordinator
    with patch.object(coordinator, "reset_consumption") as reset:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESET_CONSUMPTION,
            {"pump": "cl", "counter": "total", "serial_number": 1234},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN, SERVICE_RESET_CONSUMPTION, {}, blocking=True
        )
    assert reset.call_args_list == [
        call("cl", "total", 1234),
        call("all", "canister", None),
    ]


async def test_backwash_services_without_a_matching_unit_are_refused(
    hass, loaded_entry
) -> None:
    past = dt_util.now() - timedelta(days=1)
    with pytest.raises(ServiceValidationError, match="has been seen yet"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_LAST_SCHEDULED_BACKWASH,
            {"timestamp": past},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError, match="serial_number 9999"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH,
            {"serial_number": 9999},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError, match="has been seen yet"):
        await hass.services.async_call(
            DOMAIN, SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH, {}, blocking=True
        )


@pytest.mark.parametrize("reading_first", [False, True])
async def test_a_unit_still_reading_its_history_stops_the_service_everywhere(
    hass, loaded_entry, reading_first
) -> None:
    """Audit R1: no entry is changed while another one's history is not in yet."""
    second = _entry(hass, "second", 12412)
    assert await async_setup_entry(hass, second)
    ready = loaded_entry.runtime_data.coordinator
    reading = second.runtime_data.coordinator
    if reading_first:
        ready, reading = reading, ready
    ready.devices_update_callback(_salt_device())
    await hass.async_block_till_done()
    # on the unit's clock, which the frames put in 2024: judged there
    unit_now = ready.unit_clock_now(1234)
    assert unit_now is not None
    past = unit_now - timedelta(days=1)
    ready.set_last_scheduled_backwash(past, 1234)
    stored = ready.get_device(1234).last_scheduled_backwash

    blocked = BackwashTracker(hass, 4321)
    blocked._loading = True  # as load_soon leaves it until the store answers
    reading._backwash_trackers[4321] = blocked
    try:
        for service, data in (
            # a date in the past: the loading check, not the clock, refuses it
            (SERVICE_SET_LAST_SCHEDULED_BACKWASH, {"timestamp": past}),
            (SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH, {}),
        ):
            with pytest.raises(ServiceValidationError, match="4321"):
                await hass.services.async_call(DOMAIN, service, data, blocking=True)
            assert ready.get_device(1234).last_scheduled_backwash == stored

        # with its history in, the same call reaches every unit
        blocked._loading = False
        await hass.services.async_call(
            DOMAIN, SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH, {}, blocking=True
        )
        assert ready.get_device(1234).last_scheduled_backwash is None
    finally:
        reading._backwash_trackers.pop(4321)
        await async_unload_entry(hass, second)


async def test_set_last_scheduled_backwash_is_judged_on_the_unit_clock(
    hass, loaded_entry
) -> None:
    coordinator = loaded_entry.runtime_data.coordinator
    coordinator.devices_update_callback(_salt_device())
    await hass.async_block_till_done()
    unit_now = coordinator.unit_clock_now(1234)
    assert unit_now is not None

    with pytest.raises(ServiceValidationError, match="is in the future"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_LAST_SCHEDULED_BACKWASH,
            {"timestamp": unit_now + timedelta(hours=1)},
            blocking=True,
        )

    # a naive time is Home Assistant's local time
    moment = (unit_now - timedelta(days=1)).replace(microsecond=0)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_LAST_SCHEDULED_BACKWASH,
        {"timestamp": moment.replace(tzinfo=None).isoformat(), "serial_number": 1234},
        blocking=True,
    )
    stored = coordinator.get_device(1234).last_scheduled_backwash
    assert stored == moment.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

    with pytest.raises(ServiceValidationError, match="serial_number 9999"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_LAST_SCHEDULED_BACKWASH,
            {"timestamp": moment, "serial_number": 9999},
            blocking=True,
        )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAR_LAST_SCHEDULED_BACKWASH,
        {"serial_number": 1234},
        blocking=True,
    )
    assert coordinator.get_device(1234).last_scheduled_backwash is None


async def _mark(hass, data: dict) -> dict:
    return await hass.services.async_call(
        DOMAIN, SERVICE_MARK_DUMP, data, blocking=True, return_response=True
    )


async def test_mark_dump_is_refused_while_it_could_not_mark_anything(
    hass, loaded_entry
) -> None:
    coordinator = loaded_entry.runtime_data.coordinator

    rd = loaded_entry.runtime_data
    loaded_entry.runtime_data = None
    try:
        with pytest.raises(ServiceValidationError, match="No Aseko Local entry"):
            await _mark(hass, {})
    finally:
        loaded_entry.runtime_data = rd

    coordinator.set_recording(enabled=False)
    with pytest.raises(ServiceValidationError, match="Recording is off"):
        await _mark(hass, {})

    coordinator.set_recording(enabled=True)
    with pytest.raises(ServiceValidationError, match="received a frame from 9999"):
        await _mark(hass, {"serial_number": 9999})


async def test_mark_dump_without_waiting_writes_at_once(hass, loaded_entry) -> None:
    coordinator = loaded_entry.runtime_data.coordinator
    coordinator.set_recording(enabled=True)

    with patch(
        "custom_components.aseko_local.persistent_notification.async_create"
    ) as notify:
        response = await _mark(hass, {"note": "pH 7.2", "wait_for_next_frame": False})

    (marker,) = response["markers"]
    assert marker["entry"] == loaded_entry.title
    assert marker["marker"] == 1
    assert marker["waited_for_frame"] is None
    assert notify.call_count == 1  # no "waiting" notice
    assert notify.call_args.kwargs["title"] == "Aseko mark: written"
    assert "(pH 7.2)" in notify.call_args.args[1]


async def test_mark_dump_waits_for_the_next_frame_of_the_unit(
    hass, loaded_entry
) -> None:
    coordinator = loaded_entry.runtime_data.coordinator
    coordinator.set_recording(enabled=True)
    coordinator.store_raw_frame(bytes(_make_base_bytes()))  # the unit is known
    with patch(
        "custom_components.aseko_local.persistent_notification.async_create"
    ) as notify:
        task = hass.async_create_task(_mark(hass, {"serial_number": 1234}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert notify.call_args.kwargs["title"] == "Aseko mark: waiting for a frame"

        coordinator.devices_update_callback(_salt_device())
        response = await task

    (marker,) = response["markers"]
    assert marker["waited_for_frame"] is True
    assert notify.call_args.kwargs["title"] == "Aseko mark: written"


async def test_mark_dump_that_waited_in_vain_says_so(hass, loaded_entry) -> None:
    coordinator = loaded_entry.runtime_data.coordinator
    coordinator.set_recording(enabled=True)
    with (
        patch.object(
            coordinator, "async_wait_for_frame", AsyncMock(return_value=False)
        ),
        patch(
            "custom_components.aseko_local.persistent_notification.async_create"
        ) as notify,
    ):
        response = await _mark(hass, {})

    assert response["markers"][0]["waited_for_frame"] is False
    assert notify.call_args.kwargs["title"] == "Aseko mark: no frame arrived"


async def test_mark_dump_stopped_while_waiting_writes_nothing(
    hass, loaded_entry
) -> None:
    coordinator = loaded_entry.runtime_data.coordinator
    coordinator.set_recording(enabled=True)
    with patch(
        "custom_components.aseko_local.persistent_notification.async_dismiss"
    ) as dismiss:
        task = hass.async_create_task(_mark(hass, {}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        coordinator.set_recording(enabled=False)  # stopped on another device
        coordinator.devices_update_callback(_salt_device())

        with pytest.raises(ServiceValidationError, match="stopped or deleted"):
            await task
    dismiss.assert_called_once()
    assert coordinator.frame_log.markers() == []
