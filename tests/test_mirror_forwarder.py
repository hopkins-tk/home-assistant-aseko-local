import asyncio
import pytest

from custom_components.aseko_local.mirror_forwarder import AsekoCloudMirror


class DummyWriter:
    def __init__(self) -> None:
        self.data = []
        self.closed = False

    def write(self, frame: bytes) -> None:
        self.data.append(frame)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


@pytest.mark.asyncio
async def test_forwarding(monkeypatch) -> None:
    """Test that frames are forwarded by the mirror worker."""

    dummy_writer = DummyWriter()

    async def dummy_open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        return None, dummy_writer

    monkeypatch.setattr(asyncio, "open_connection", dummy_open_connection)

    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    frame = b"\xaa" * 120
    await mirror.enqueue(frame)
    await asyncio.sleep(0.2)  # Give worker time to process
    await mirror.stop()

    # Check that the frame was written to DummyWriter
    assert any(f == frame for f in dummy_writer.data)
