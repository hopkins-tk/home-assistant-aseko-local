from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .logging_helper import LoggingHelper


class AsekoCloudMirror:
    """Asynchronous TCP forwarder to Aseko Cloud with optional logging via LoggingHelper.
    - Non-blocking: frames are queued and sent by a worker task.
    - Resilient: reconnects on errors with backoff.
    """

    def __init__(
        self,
        cloud_host: str,
        cloud_port: int,
        logger: Optional[logging.Logger] = None,
        log_helper: Optional[LoggingHelper] = None,
    ) -> None:
        self._host = cloud_host
        self._port = int(cloud_port)
        self._logger = logger or logging.getLogger(__name__)
        self._queue: "asyncio.Queue[bytes]" = asyncio.Queue(maxsize=1000)
        self._task: Optional[asyncio.Task] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected_event = asyncio.Event()

        # Zentraler Logger (HEX/BIN/Info)
        self._log_helper = log_helper

    async def start(self) -> None:
        """Start worker task."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._worker(), name="AsekoCloudMirrorWorker")

    async def stop(self) -> None:
        """Stop worker task and close connection."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._close_writer()

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
            except Exception:
                pass
            try:
                self._queue.put_nowait(bytes(frame))
            except Exception:
                self._logger.debug("Mirror queue overflow; frame dropped.")

        # Optional: Logging via zentralem Helper
        if self._log_helper:
            try:
                self._log_helper.log_hex_frame(frame)
                self._log_helper.log_bin_frame(frame)
            except Exception:
                self._logger.debug("Failed to log frame in mirror.", exc_info=True)

    async def _worker(self) -> None:
        """Connection loop with reconnect/backoff and queue consumption."""
        backoff = 1.0
        while True:
            try:
                # Ensure connection
                if self._writer is None:
                    try:
                        reader, writer = await asyncio.open_connection(self._host, self._port)
                        self._writer = writer
                        self._connected_event.set()
                        backoff = 1.0
                        self._logger.debug("Mirror connected to %s:%s", self._host, self._port)
                        if self._log_helper:
                            self._log_helper.log_info(
                                "mirror", f"Connected to {self._host}:{self._port}"
                            )
                    except Exception as e:
                        self._logger.debug("Mirror connect failed: %s", e)
                        if self._log_helper:
                            self._log_helper.log_info(
                                "mirror", f"Connect failed: {e}"
                            )
                        await asyncio.sleep(min(backoff, 10.0))
                        backoff = min(backoff * 2.0, 10.0)
                        continue

                # Get next frame to send
                frame = await self._queue.get()
                try:
                    self._writer.write(frame)
                    await self._writer.drain()
                except Exception as e:
                    self._logger.debug("Mirror write failed: %s", e)
                    if self._log_helper:
                        self._log_helper.log_info("mirror", f"Write failed: {e}")
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
                self._logger.debug("Mirror worker loop error.", exc_info=True)
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
                if self._log_helper:
                    self._log_helper.log_info("mirror", "Disconnected")
