from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

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
        self._host = cloud_host
        self._port = int(cloud_port)
        self._queue: "asyncio.Queue[bytes]" = asyncio.Queue(maxsize=1000)
        self._task: Optional[asyncio.Task] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected_event = asyncio.Event()
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
            await self._task
            self._task = None
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
            try:
                _ = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(bytes(frame))
            except Exception:
                _LOGGER.error("Mirror queue overflow; frame dropped.")

    async def _worker(self) -> None:
        """Loop connection with reconnect/backoff and queue consumption."""

        backoff = 1.0
        while True:
            try:
                # Ensure connection
                if self._writer is None:
                    try:
                        reader, writer = await asyncio.open_connection(
                            self._host, self._port
                        )
                        self._writer = writer
                        self._last_connect = time.time()

                        self._connected_event.set()
                        backoff = 1.0
                        _LOGGER.debug(
                            "Mirror connected to %s:%s", self._host, self._port
                        )
                    except Exception as e:
                        _LOGGER.error("Mirror connect failed: %s", e)
                        await asyncio.sleep(min(backoff, 10.0))
                        backoff = min(backoff * 2.0, 10.0)
                        continue

                # Check reconnect interval
                if time.time() - self._last_connect > self._reconnect_interval:
                    _LOGGER.debug(
                        "Mirror reconnect interval reached (%ds), reconnecting...",
                        self._reconnect_interval,
                    )
                    await self._close_writer()
                    continue  # next loop will reconnect

                # Get next frame to send
                frame = await self._queue.get()
                try:
                    self._writer.write(frame)
                    _LOGGER.debug(
                        "Frame to cloud sent (%d Bytes):\n%s",
                        len(frame),
                        frame.hex(" ", 1),
                    )
                    await self._writer.drain()
                except Exception as e:
                    _LOGGER.error("Mirror write failed: %s", e)
                    await self._close_writer()
                    # requeue the frame to try again
                    try:
                        self._queue.put_nowait(frame)
                    except Exception:
                        pass
                    await asyncio.sleep(0)  # yield

            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.error("Mirror worker loop error.", exc_info=True)
                await asyncio.sleep(0.1)

    async def _close_writer(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                try:
                    await self._writer.wait_closed()
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self._writer = None
                self._connected_event.clear()
                _LOGGER.debug("Mirror connection closed.")
