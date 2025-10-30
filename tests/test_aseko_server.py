import asyncio
import pytest

from custom_components.aseko_local.aseko_server import (
    AsekoDeviceServer,
)
from custom_components.aseko_local.aseko_data import AsekoDevice


# Hilfsfunktion: Hex-String zu Bytes
def hexstr_to_bytes(s: str) -> bytes:
    return bytes.fromhex(s.replace("\n", "").replace(" ", ""))


# Reales gültiges Frame (gekürzt für Beispiel)
VALID_FRAME_HEX = (
    "069187240901ffffffffffff000402da0027ffff0095ff01400149ff000006640000000000ff006c"
    "069187240903ffffffffffff480a08ffffffffffffffffff027e0149ffffffffffffffffffffffea"
    "069187240902ffffffffffff0001003cffff003cffff010383ff00781e02581e28ffffffff0049a9"
)
VALID_FRAME = hexstr_to_bytes(VALID_FRAME_HEX)  # MESSAGE_SIZE = 120

# Korruptes Frame: pH Wert ungültig (z.B. 99.99)
CORRUPT_FRAME = bytearray(VALID_FRAME)
CORRUPT_FRAME[14:16] = (9999).to_bytes(2, "big")  # pH = 99.99


class DummyWriter:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass

    def get_extra_info(self, name: str):
        # Simuliere Peername für Tests
        if name == "peername":
            return (self.host, self.port)
        return None


class DummyServer:
    def is_serving(self) -> bool:
        return True

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


@pytest.mark.asyncio
async def test_valid_device_frame(monkeypatch) -> None:
    """Test: Bestehendes Device wird erkannt und verarbeitet."""

    called = {}

    async def on_data(device: AsekoDevice) -> None:
        called["serial"] = device.serial_number

    async def dummy_start_server(handler, host, port) -> DummyServer:
        # Simulate a connection with valid data
        reader = asyncio.StreamReader()
        writer = DummyWriter("127.0.0.1", 12345)
        reader.feed_data(VALID_FRAME)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12345, on_data=on_data
    )
    assert server.running
    # Serial number should be captured
    assert "serial" in called
    assert called["serial"] == 110200612
    await server.stop()


@pytest.mark.asyncio
async def test_corrupt_frame_ph(monkeypatch) -> None:
    """Test: Korruptes Frame mit ungültigem pH-Wert schließt die Verbindung."""

    called = {}

    async def on_data(device: AsekoDevice) -> None:
        called["serial"] = device.serial_number

    async def dummy_start_server(handler, host, port) -> DummyServer:
        reader = asyncio.StreamReader()
        writer = DummyWriter("127.0.0.1", 12346)
        reader.feed_data(CORRUPT_FRAME)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12346, on_data=on_data
    )
    assert server.running
    # Kein Device sollte verarbeitet werden
    assert "serial" not in called
    await server.stop()


@pytest.mark.asyncio
async def test_issue_61_shifted_frame(monkeypatch) -> None:
    """Test: Shifted frame from issue 61."""

    BYTE_FRAME = hexstr_to_bytes(
        "0f0f1e14ffbf02970690cf4a0301190a12103232000402cb015201520152a3fe700099fe00080000"
        "00000000001302670690cf4a0303190a121032324842011d080f122d15001737027600a9000c1e0a"
        "012801e00e10a2020690cf4a0302190a12103232002d003c003c003c000a1e3c6e9600f00802580f"
    )

    called = {}

    async def on_data(device: AsekoDevice) -> None:
        called["serial"] = device.serial_number

    async def dummy_start_server(handler, host, port) -> DummyServer:
        # Simulate a connection with valid data
        reader = asyncio.StreamReader()
        writer = DummyWriter("127.0.0.1", 12347)
        reader.feed_data(BYTE_FRAME)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12347, on_data=on_data
    )
    assert server.running
    # Serial number should be captured
    assert "serial" in called
    assert called["serial"] == 110153546
    await server.stop()
