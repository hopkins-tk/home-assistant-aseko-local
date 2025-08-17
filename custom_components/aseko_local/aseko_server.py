"""Server for receiving and parsing Aseko unit data."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import ClassVar, Optional, Any

from .aseko_data import AsekoDevice
from .aseko_decoder import AsekoDecoder
from .const import DEFAULT_BINDING_ADDRESS, DEFAULT_BINDING_PORT, MESSAGE_SIZE
from .logging_helper import LoggingHelper  # Neuer zentraler Logger

_LOGGER = logging.getLogger(__name__)


class AsekoDeviceServer:
    """Async TCP server for receiving and parsing Aseko unit data."""

    _instances: ClassVar[dict[str, "AsekoDeviceServer"]] = {}

    def __init__(
        self,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Callable[[AsekoDevice], Any] | None = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
        log_helper: Optional[LoggingHelper] = None,  # Neu
    ) -> None:
        """Initialize the server."""
        self.host = host
        self.port = port
        self.on_data = on_data  # callback with decoded AsekoDevice
        self._server: asyncio.AbstractServer | None = None

        # Optional raw sink (receives the raw 120-byte frame)
        self._raw_sink: Optional[Callable[[bytes], Any]] = raw_sink

        # Optional forward callback (e.g. cloud mirror). Receives raw bytes.
        self._forward_cb: Optional[Callable[[bytes], Any]] = None

        # Zentraler Logger
        self._log_helper: Optional[LoggingHelper] = log_helper

    async def start(self) -> None:
        """Start the TCP server."""
        try:
            self._server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )
            _LOGGER.info("AsekoUnitServer started on %s:%d", self.host, self.port)
        except OSError as err:
            _LOGGER.error("Failed to start AsekoUnitServer: %s", err)
            message = f"Failed to start server: {err}"
            raise ServerConnectionError(message) from err

    async def stop(self) -> None:
        """Stop the TCP server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            _LOGGER.info("AsekoUnitServer stopped")

    @property
    def running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None and self._server.is_serving()

    async def _maybe_await(self, fn_result: Any) -> None:
        """Await result if it is an awaitable; otherwise do nothing."""
        if asyncio.iscoroutine(fn_result):
            await fn_result

    async def _call_raw_sink(self, data: bytes) -> None:
        """Call raw sink if present (sync or async), swallow errors."""
        sink = self._raw_sink
        if sink is None:
            return
        try:
            res = sink(data)
            if asyncio.iscoroutine(res):
                await res
        except Exception:  # pragma: no cover
            _LOGGER.debug("Raw sink raised an exception.", exc_info=True)

    async def _call_forward_cb(self, data: bytes) -> None:
        """Call forward callback if present (sync or async), swallow errors."""
        cb = self._forward_cb
        if cb is None:
            return
        try:
            _LOGGER.debug("Forward callback called with %d bytes", len(data))
            res = cb(data)
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            _LOGGER.debug("Forward callback raised an exception.", exc_info=True)

    async def _maybe_call_on_data(self, device: AsekoDevice) -> None:
        """Call on_data if present (sync or async)."""
        cb = self.on_data
        if cb is None:
            return
        try:
            res = cb(device)
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            _LOGGER.debug("on_data callback raised an exception.", exc_info=True)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming client connection with frame buffering."""
        addr = writer.get_extra_info("peername")
        _LOGGER.debug("Connection from %s", addr)

        buffer = b""

        try:
            while True:
                chunk = await reader.read(1024)
                if not chunk:
                    _LOGGER.debug("Client %s closed connection", addr)
                    break

                buffer += chunk

                while len(buffer) >= MESSAGE_SIZE:
                    frame = buffer[:MESSAGE_SIZE]
                    buffer = buffer[MESSAGE_SIZE:]

                    await self._call_raw_sink(frame)
                    await self._call_forward_cb(frame)

                    try:
                        device = AsekoDecoder.decode(frame)
                    except ValueError as e:
                        _LOGGER.warning(
                            "Skipping invalid frame from %s (%s): %s",
                            addr,
                            e,
                            frame.hex(),
                        )
                        continue
                    except Exception:
                        _LOGGER.exception("Unexpected error decoding frame from %s", addr)
                        continue

                    _LOGGER.debug("Received data parsed as %s", device)

                    if self._log_helper is not None:
                        try:
                            self._log_helper.log_flowrates("AsekoDeviceServer", device)
                        except Exception:
                            _LOGGER.debug("Flowrate logging failed", exc_info=True)

                    await self._maybe_call_on_data(device)

        except ConnectionResetError:
            _LOGGER.debug("Client %s closed connection unexpectedly", addr)
        except asyncio.IncompleteReadError:
            _LOGGER.debug("Connection from %s closed", addr)
        except Exception:
            _LOGGER.exception("Error while handling client %s", addr)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


    @classmethod
    async def create(
        cls,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Callable[[AsekoDevice], Any] | None = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
        log_helper: Optional[LoggingHelper] = None,
    ) -> "AsekoDeviceServer":
        """Get or create an instance of AsekoUnitServer for the given host and port."""
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoDeviceServer(
                host, port, on_data, raw_sink, log_helper
            )
            await cls._instances[key].start()
        else:
            # Update handlers if instance already exists
            if raw_sink is not None:
                cls._instances[key]._raw_sink = raw_sink
            if on_data is not None:
                cls._instances[key].on_data = on_data
            if log_helper is not None:
                cls._instances[key]._log_helper = log_helper
        return cls._instances[key]

    @classmethod
    async def remove(cls, host: str, port: int) -> None:
        """Remove an instance of AsekoUnitServer for the given host and port."""
        key = f"{host}:{port}"
        if key in cls._instances and cls._instances[key] is not None:
            await cls._instances[key].stop()
            del cls._instances[key]

    # Public API to set forwarder at runtime
    def set_forward_callback(self, callback: Optional[Callable[[bytes], Any]]) -> None:
        """Register or clear the forward callback that receives raw bytes."""
        self._forward_cb = callback
        if callback is None:
            _LOGGER.info("Forward callback cleared.")
        else:
            _LOGGER.info("Forward callback registered.")

    # Optional: allow setting/changing the raw sink later
    def set_raw_sink(self, sink: Optional[Callable[[bytes], Any]]) -> None:
        """Register or clear the raw sink callback."""
        self._raw_sink = sink
        if sink is None:
            _LOGGER.info("Raw sink cleared.")
        else:
            _LOGGER.info("Raw sink registered.")

    def set_log_helper(self, log_helper: Optional[LoggingHelper]) -> None:
        """Register or clear the log helper instance."""
        self._log_helper = log_helper
        if log_helper is None:
            _LOGGER.info("Log helper cleared.")
        else:
            _LOGGER.info("Log helper registered.")


class ServerConnectionError(Exception):
    """Exception class for connection error."""
