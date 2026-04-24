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


@pytest.mark.asyncio
async def test_no_connection_before_first_frame(monkeypatch) -> None:
    """Worker must not open a connection until the first frame is enqueued."""

    connect_count = 0

    async def dummy_open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        nonlocal connect_count
        connect_count += 1
        return None, DummyWriter()

    monkeypatch.setattr(asyncio, "open_connection", dummy_open_connection)

    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    # Give the worker task a chance to run without any frame
    await asyncio.sleep(0.1)

    assert connect_count == 0, "Connection opened before any frame was enqueued"

    await mirror.stop()


@pytest.mark.asyncio
async def test_connect_on_first_frame(monkeypatch) -> None:
    """Worker must open exactly one connection when the first frame arrives."""

    connect_count = 0
    dummy_writer = DummyWriter()

    async def dummy_open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        nonlocal connect_count
        connect_count += 1
        return None, dummy_writer

    monkeypatch.setattr(asyncio, "open_connection", dummy_open_connection)

    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await asyncio.sleep(0.05)  # worker is blocked in queue.get()
    assert connect_count == 0

    await mirror.enqueue(b"\xbb" * 120)
    await asyncio.sleep(0.1)  # worker processes the frame

    assert connect_count == 1, "Expected exactly one connection after first frame"
    assert len(dummy_writer.data) == 1

    await mirror.stop()


@pytest.mark.asyncio
async def test_multiple_frames_reuse_connection(monkeypatch) -> None:
    """Multiple frames must reuse the same connection — no reconnect per frame."""

    connect_count = 0
    dummy_writer = DummyWriter()

    async def dummy_open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        nonlocal connect_count
        connect_count += 1
        return None, dummy_writer

    monkeypatch.setattr(asyncio, "open_connection", dummy_open_connection)

    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()

    for i in range(5):
        await mirror.enqueue(bytes([i]) * 120)

    await asyncio.sleep(0.2)  # Give worker time to drain the queue

    assert connect_count == 1, f"Expected 1 connection, got {connect_count}"
    assert len(dummy_writer.data) == 5

    await mirror.stop()
