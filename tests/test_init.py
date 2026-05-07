"""Test Aseko Local setup process."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry
from typing import Any

from custom_components.aseko_local import (
    async_setup_entry,
)
from custom_components.aseko_local.aseko_data import AsekoDevice
from custom_components.aseko_local.const import (
    DOMAIN,
)

from .const import MOCK_CONFIG
import asyncio
from custom_components.aseko_local.mirror_forwarder import AsekoCloudMirror
from custom_components.aseko_local.aseko_server import (
    AsekoDeviceServer,
)


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
    # call, no code from custom_components/aseko_local/aseko_server.py actually runs.
    assert await async_setup_entry(hass, config_entry)

    class DummyWriter:
        def __init__(self) -> None:
            self.data = []
            self.closed = False

        def write(self, frame) -> None:
            self.data.append(frame)

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            pass

    @pytest.mark.asyncio
    async def test_mirror_forwarder_enqueue_and_worker(monkeypatch) -> None:
        """Test that AsekoCloudMirror enqueues and sends frames."""

        async def dummy_open_connection(host, port) -> tuple[None, DummyWriter]:
            return None, DummyWriter()

        monkeypatch.setattr(asyncio, "open_connection", dummy_open_connection)

        mirror = AsekoCloudMirror("localhost", 12345)
        await mirror.start()
        frame = b"\x01" * 120
        await mirror.enqueue(frame)
        await asyncio.sleep(0.1)
        await mirror.stop()
        # The DummyWriter stores frames in .data
        assert any(f == frame for f in getattr(mirror._writer, "data", []))

    @pytest.mark.asyncio
    async def test_server_forward_callback(monkeypatch) -> None:
        """Test that AsekoDeviceServer forwards frames using the callback."""
        called = {}

        async def forward_cb(data) -> None:
            called["frame"] = data

        class DummyServer:
            def is_serving(self) -> bool:
                return True

            def close(self) -> None:
                pass

            async def wait_closed(self) -> None:
                pass

        # Patch start_server to avoid opening real sockets
        async def dummy_start_server(handler, host, port) -> DummyServer:
            return DummyServer()

        monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

        server = await AsekoDeviceServer.create(host="127.0.0.1", port=12345)
        server.set_forward_callback(forward_cb)
        frame = b"\x02" * 120
        await server._call_forward_cb(frame)  # noqa: SLF001
        assert called["frame"] == frame

    @pytest.mark.asyncio
    async def test_server_forward_callback_none(monkeypatch) -> None:
        """Test that removing the forward callback disables forwarding."""

        class DummyServer:
            def is_serving(self) -> bool:
                return True

            def close(self) -> None:
                pass

            async def wait_closed(self) -> None:
                pass

        async def dummy_start_server(handler, host, port) -> DummyServer:
            return DummyServer()

        monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

        server = await AsekoDeviceServer.create(host="127.0.0.1", port=12346)
        server.set_forward_callback(None)
        frame = b"\x03" * 120
        # Should not raise or call anything
        await server._call_forward_cb(frame)  # noqa: SLF001


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

        def get_extra_info(self, name: str) -> Any:
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
    from custom_components.aseko_local.aseko_data import AsekoDeviceType

    device = AsekoDevice()
    device.serial_number = serial
    device.device_type = AsekoDeviceType.NET
    return device


@pytest.mark.asyncio
async def test_coordinator_new_device_listener_called_for_new_device(hass) -> None:
    """Listener is called exactly once when a brand-new device arrives."""
    from custom_components.aseko_local.coordinator import (
        AsekoLocalDataUpdateCoordinator,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.aseko_local.const import DOMAIN
    from tests.const import MOCK_CONFIG

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
    from custom_components.aseko_local.coordinator import (
        AsekoLocalDataUpdateCoordinator,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.aseko_local.const import DOMAIN
    from tests.const import MOCK_CONFIG

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
    from custom_components.aseko_local.coordinator import (
        AsekoLocalDataUpdateCoordinator,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.aseko_local.const import DOMAIN
    from tests.const import MOCK_CONFIG

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
