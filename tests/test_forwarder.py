import asyncio
import logging

import pytest

from custom_components.aseko_local import forwarder as forwarder_module
from custom_components.aseko_local.forwarder import AsekoCloudMirror


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


@pytest.mark.asyncio
async def test_a_frame_that_failed_goes_out_before_newer_ones(monkeypatch) -> None:
    """Audit A4: connect fails for A while B waits; the cloud still gets A, B."""
    writer = DummyWriter()
    attempts = {"n": 0}

    async def flaky_open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            msg = "cloud unreachable"
            raise OSError(msg)
        return None, writer

    monkeypatch.setattr(asyncio, "open_connection", flaky_open_connection)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await mirror.enqueue(b"B")
    for _ in range(300):
        if len(writer.data) == 2:
            break
        await asyncio.sleep(0.01)
    await mirror.stop()

    assert writer.data == [b"A", b"B"]


@pytest.mark.asyncio
async def test_a_frame_whose_write_failed_goes_out_first(monkeypatch) -> None:
    class FailOnce(DummyWriter):
        def __init__(self) -> None:
            super().__init__()
            self.failed = False

        def write(self, frame: bytes) -> None:
            if not self.failed:
                self.failed = True
                msg = "broken pipe"
                raise OSError(msg)
            super().write(frame)

    writer = FailOnce()

    async def open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        return None, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await mirror.enqueue(b"B")
    for _ in range(300):
        if len(writer.data) == 2:
            break
        await asyncio.sleep(0.01)
    await mirror.stop()

    assert writer.data == [b"A", b"B"]


@pytest.mark.asyncio
async def test_repeated_write_failures_back_off(monkeypatch) -> None:
    """Audit B3: a cloud that keeps failing writes is not retried in a tight loop."""
    attempts = {"n": 0}

    class AlwaysFails(DummyWriter):
        def write(self, frame: bytes) -> None:
            attempts["n"] += 1
            msg = "broken pipe"
            raise OSError(msg)

    async def open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        return None, AlwaysFails()

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await asyncio.sleep(0.3)
    await mirror.stop()

    # the first attempt fails, then the worker waits a second before the next
    assert attempts["n"] == 1


async def _until(condition, tries: int = 300) -> None:
    for _ in range(tries):
        if condition():
            return
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_start_twice_runs_one_worker_and_stop_without_start_is_safe() -> None:
    idle = AsekoCloudMirror("localhost", 12345)
    await idle.stop()  # never started

    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    worker = mirror._task
    await mirror.start()
    assert mirror._task is worker
    await mirror.stop()
    assert mirror._task is None


@pytest.mark.asyncio
async def test_only_bytes_are_queued() -> None:
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.enqueue("not bytes")  # type: ignore[arg-type]
    await mirror.enqueue(bytearray(b"frame"))
    assert mirror._queue.qsize() == 1
    assert mirror._queue.get_nowait() == b"frame"


@pytest.mark.asyncio
async def test_a_full_queue_drops_the_oldest_frame() -> None:
    mirror = AsekoCloudMirror("localhost", 12345)
    mirror._queue = asyncio.Queue(maxsize=2)
    for frame in (b"1", b"2", b"3"):
        await mirror.enqueue(frame)
    assert [mirror._queue.get_nowait() for _ in range(2)] == [b"2", b"3"]


@pytest.mark.asyncio
async def test_a_queue_that_stays_full_drops_the_new_frame(caplog) -> None:
    class AlwaysFull(asyncio.Queue):
        def put_nowait(self, item: bytes) -> None:
            raise asyncio.QueueFull

        def get_nowait(self) -> bytes:
            raise asyncio.QueueEmpty

    mirror = AsekoCloudMirror("localhost", 12345)
    mirror._queue = AlwaysFull()
    await mirror.enqueue(b"frame")
    assert "Mirror queue overflow; frame dropped." in caplog.text


@pytest.mark.asyncio
async def test_the_connection_is_renewed_after_the_reconnect_interval(
    monkeypatch,
) -> None:
    writers: list[DummyWriter] = []

    async def open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        writers.append(DummyWriter())
        return None, writers[-1]

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    mirror = AsekoCloudMirror("localhost", 12345, reconnect_interval=-1)
    await mirror.start()
    await mirror.enqueue(b"A")
    await _until(lambda: len(writers) == 1 and writers[0].data)
    await mirror.enqueue(b"B")
    await _until(lambda: len(writers) == 2 and writers[1].data)
    await mirror.stop()

    assert [w.data for w in writers] == [[b"A"], [b"B"]]
    assert writers[0].closed


@pytest.mark.asyncio
async def test_frames_are_logged_as_hex_at_debug_level(monkeypatch, caplog) -> None:
    writer = DummyWriter()

    async def open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        return None, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    caplog.set_level(logging.DEBUG, logger=forwarder_module.__name__)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"\x01\xab")
    await _until(lambda: writer.data)
    await mirror.stop()

    assert "01 ab" in caplog.text


@pytest.mark.asyncio
async def test_an_unexpected_error_keeps_the_worker_and_the_frame(monkeypatch) -> None:
    class BreaksOnce(DummyWriter):
        def __init__(self) -> None:
            super().__init__()
            self.broken = False

        def write(self, frame: bytes) -> None:
            if not self.broken:
                self.broken = True
                msg = "unexpected"
                raise RuntimeError(msg)
            super().write(frame)

    writer = BreaksOnce()

    async def open_connection(host: str, port: int) -> tuple[None, DummyWriter]:
        return None, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await _until(lambda: writer.data)
    await mirror.stop()

    assert writer.data == [b"A"]


@pytest.mark.asyncio
async def test_what_the_cloud_sends_back_is_read_and_logged(
    monkeypatch, caplog
) -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"ACK")
    reader.feed_eof()

    async def open_connection(
        host: str, port: int
    ) -> tuple[asyncio.StreamReader, DummyWriter]:
        return reader, DummyWriter()

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    caplog.set_level(logging.DEBUG, logger=forwarder_module.__name__)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await _until(lambda: "closed the connection" in caplog.text)
    await mirror.stop()

    assert "cloud server sent 3 bytes back:\nACK" in caplog.text
    assert "Mirror: cloud server closed the connection." in caplog.text


@pytest.mark.asyncio
async def test_a_reader_that_is_still_waiting_is_cancelled_on_stop(
    monkeypatch,
) -> None:
    reader = asyncio.StreamReader()  # the cloud never answers

    async def open_connection(
        host: str, port: int
    ) -> tuple[asyncio.StreamReader, DummyWriter]:
        return reader, DummyWriter()

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await _until(lambda: mirror._read_task is not None)
    read_task = mirror._read_task
    await mirror.stop()

    assert read_task.cancelled()
    assert mirror._read_task is None


@pytest.mark.asyncio
async def test_a_broken_cloud_reader_ends_only_the_read(monkeypatch) -> None:
    reader = asyncio.StreamReader()
    reader.set_exception(ConnectionResetError())
    writer = DummyWriter()

    async def open_connection(
        host: str, port: int
    ) -> tuple[asyncio.StreamReader, DummyWriter]:
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    mirror = AsekoCloudMirror("localhost", 12345)
    await mirror.start()
    await mirror.enqueue(b"A")
    await _until(lambda: mirror._read_task is not None and mirror._read_task.done())
    await mirror.enqueue(b"B")
    await _until(lambda: len(writer.data) == 2)
    await mirror.stop()

    assert writer.data == [b"A", b"B"]
