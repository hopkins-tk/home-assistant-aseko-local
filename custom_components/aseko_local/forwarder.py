"""Forward the frames a unit sends to Aseko Cloud, as the unit itself would."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

_LOGGER = logging.getLogger(__name__)


class AsekoCloudMirror:
    """Asynchronous TCP forwarder to Aseko Cloud.

    - Non-blocking: frames are queued and sent by a worker task.
    - Resilient: reconnects on errors with backoff and also on a fixed interval.
    """

    def __init__(
        self,
        cloud_host: str,
        cloud_port: int,
        reconnect_interval: int = 900,  # force reconnect 15 minutes
    ) -> None:
        """Set up a mirror to one cloud host and port; ``start`` runs it."""
        self._host = cloud_host
        self._port = int(cloud_port)
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1000)
        self._task: asyncio.Task | None = None
        self._read_task: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_connect: float = 0.0
        self._reconnect_interval = reconnect_interval

    async def start(self) -> None:
        """Start worker task."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._worker(), name="AsekoCloudMirrorWorker")
        _LOGGER.debug("Mirror worker started.")

    async def stop(self) -> None:
        """Stop worker task and close connection."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._read_task:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task
            self._read_task = None
        await self._close_writer()
        _LOGGER.debug("Mirror worker stopped.")

    async def enqueue(self, frame: bytes) -> None:
        """Queue one raw Aquanet frame (120 bytes). Non-blocking for the caller."""
        if not isinstance(frame, (bytes, bytearray)):
            return
        try:
            self._queue.put_nowait(bytes(frame))
        except asyncio.QueueFull:
            # Drop oldest to keep stream moving
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self._queue.get_nowait()
            try:
                self._queue.put_nowait(bytes(frame))
            except asyncio.QueueFull:
                _LOGGER.error("Mirror queue overflow; frame dropped.")

    async def _worker(self) -> None:
        """Loop: wait for a frame, connect lazily, send, reconnect on errors."""

        backoff = 1.0
        # A frame that failed to go out is sent again before any newer one, so
        # the cloud receives them in the order the unit sent them.
        pending: bytes | None = None
        while True:
            try:
                # Wait for the next frame — no connection is opened until data arrives
                if pending is None:
                    pending = await self._queue.get()
                frame = pending

                # Reconnect interval: force fresh connection periodically
                if (
                    self._writer is not None
                    and time.time() - self._last_connect > self._reconnect_interval
                ):
                    _LOGGER.debug(
                        "Mirror reconnect interval reached (%ds), reconnecting...",
                        self._reconnect_interval,
                    )
                    await self._close_writer()

                # Connect if not already connected
                if self._writer is None:
                    try:
                        reader, writer = await asyncio.open_connection(
                            self._host, self._port
                        )
                        self._writer = writer
                        self._last_connect = time.time()
                        _LOGGER.debug(
                            "Mirror connected to %s:%d", self._host, self._port
                        )
                        # Start background task to drain and log cloud responses
                        if self._read_task:
                            self._read_task.cancel()
                        self._read_task = asyncio.create_task(
                            self._drain_cloud_reader(reader),
                            name="AsekoCloudMirrorReader",
                        )
                    except OSError as e:  # refused, unreachable, timed out
                        _LOGGER.error("Mirror connect failed: %s", e)
                        # keep the frame as pending: it goes out first next time
                        await asyncio.sleep(min(backoff, 10.0))
                        backoff = min(backoff * 2.0, 10.0)
                        continue

                # Send the frame
                try:
                    self._writer.write(frame)
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "Frame to cloud sent (%d Bytes):\n%s",
                            len(frame),
                            frame.hex(" ", 1),
                        )
                    await self._writer.drain()
                    pending = None
                    backoff = 1.0
                except OSError as e:  # reset, broken pipe
                    _LOGGER.error("Mirror write failed: %s", e)
                    await self._close_writer()
                    # keep the frame as pending: it goes out first next time,
                    # after the same growing pause as a failed connect
                    await asyncio.sleep(min(backoff, 10.0))
                    backoff = min(backoff * 2.0, 10.0)

            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Mirror worker loop error.")
                await asyncio.sleep(0.1)

    async def _drain_cloud_reader(self, reader: asyncio.StreamReader) -> None:
        """Read and log any data the cloud server sends back."""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    _LOGGER.debug("Mirror: cloud server closed the connection.")
                    break
                text = data.decode("ascii", errors="replace")
                _LOGGER.debug(
                    "Mirror: cloud server sent %d bytes back:\n%s", len(data), text
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- whatever ended the read ends only the read
            _LOGGER.debug("Mirror reader closed.", exc_info=False)

    async def _close_writer(self) -> None:
        if self._writer:
            try:
                # a connection that is gone already needs no closing
                with contextlib.suppress(Exception):
                    self._writer.close()
                    await self._writer.wait_closed()
            finally:
                self._writer = None
                _LOGGER.debug("Mirror connection closed.")
