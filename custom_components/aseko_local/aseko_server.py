"""Robuster Server für Aseko-Geräte mit Forwarder."""

import asyncio
import logging
from collections.abc import Callable
from typing import ClassVar, Optional, Any

from .aseko_data import AsekoDevice
from .aseko_decoder import AsekoDecoder
from .const import DEFAULT_BINDING_ADDRESS, DEFAULT_BINDING_PORT, MESSAGE_SIZE
from .logging_helper import LoggingHelper

_LOGGER = logging.getLogger(__name__)


class AsekoDeviceServer:
    """Async TCP server für Aseko-Gerätedaten."""

    _instances: ClassVar[dict[str, "AsekoDeviceServer"]] = {}

    def __init__(
        self,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Optional[Callable[[AsekoDevice], Any]] = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
        log_helper: Optional[LoggingHelper] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_data = on_data
        self._raw_sink = raw_sink
        self._forward_cb: Optional[Callable[[bytes], Any]] = None
        self._log_helper = log_helper
        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        """Start of the TCP server."""

        try:
            self._server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )
            _LOGGER.info("AsekoDeviceServer gestartet auf %s:%d", self.host, self.port)
        except OSError as err:
            _LOGGER.error("Serverstart fehlgeschlagen: %s", err)
            raise ServerConnectionError(f"Failed to start server: {err}") from err

    async def stop(self) -> None:
        """Stop the TCP server and disconnect all clients."""

        if self._server:
            for w in list(self._clients):
                try:
                    w.close()
                    await w.wait_closed()
                except Exception:
                    pass
            self._clients.clear()
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            _LOGGER.info("AsekoDeviceServer gestoppt")

    @property
    def running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None and self._server.is_serving()

    async def _maybe_await(self, result: Any) -> None:
        if asyncio.iscoroutine(result):
            await result

    async def _call_raw_sink(self, data: bytes) -> None:
        if self._raw_sink:
            try:
                await self._maybe_await(self._raw_sink(data))
            except Exception:
                _LOGGER.debug("Raw sink raised an exception", exc_info=True)

    async def _call_forward_cb(self, data: bytes) -> None:
        if self._forward_cb:
            try:
                _LOGGER.debug("Forward callback called with %d bytes", len(data))
                await self._maybe_await(self._forward_cb(data))
            except Exception:
                _LOGGER.debug("Forward callback raised an exception", exc_info=True)

    async def _maybe_call_on_data(self, device: AsekoDevice) -> None:
        if self.on_data:
            try:
                await self._maybe_await(self.on_data(device))
            except Exception:
                _LOGGER.debug("on_data callback raised an exception", exc_info=True)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        _LOGGER.debug("Connection from %s", addr)
        self._clients.add(writer)

        try:
            while True:
                try:
                    # ✅ Read exactly MESSAGE_SIZE bytes per frame
                    frame = await reader.readexactly(MESSAGE_SIZE)

                    _LOGGER.info(
                        "Frame received from %s (%d bytes):\n%s",
                        addr,
                        len(frame),
                        frame.hex(" ", 1),  # print as spaced hex string
                    )

                except asyncio.IncompleteReadError:
                    _LOGGER.debug("Client %s closed the connection", addr)
                    break

                # Forward raw data (e.g. for debugging or mirroring)
                await self._call_raw_sink(frame)
                await self._call_forward_cb(frame)

                # Try to decode the frame
                try:
                    # 🔎 Plausibility check before decoding: pH values must be between 0 and 14
                    # Sometimes after server start we get garbage data (shifted bytes) that
                    # opens a new incorrect new device in Home Assistant. The device type
                    # is shown as SALT and any serial number. Such records are never resynched.
                    # To avoid this, we check the pH values here. If they are out of range,
                    # the package is ignored and the connection is reopened.
                    ph_value = int.from_bytes(frame[14:16], "big") / 100
                    if not (0 <= ph_value <= 14):
                        _LOGGER.warning(
                            "Unreasonable pH value (%s) received from %s → closing connection",
                            ph_value,
                            addr,
                        )
                        break  # leave loop → connection will be closed

                    required_ph = frame[52] / 10
                    if not (6 <= required_ph <= 10):
                        _LOGGER.warning(
                            "Unreasonable required pH value (%s) received from %s → closing connection",
                            required_ph,
                            addr,
                        )
                        break  # leave loop → connection will be closed

                    device = AsekoDecoder.decode(frame)  # Logger temporary only

                except ValueError as e:
                    _LOGGER.warning(
                        "Invalid frame from %s: %s → closing connection", addr, e
                    )
                    break
                except Exception:
                    _LOGGER.exception(
                        "Decoding error for data from %s → closing connection", addr
                    )
                    break

                _LOGGER.debug("Decoded data from %s: %s", addr, device)

                # Optional: log flowrates
                if self._log_helper:
                    try:
                        await self._log_helper.log_flowrates(
                            "AsekoDeviceServer", device
                        )
                    except Exception:
                        _LOGGER.debug("Flowrate logging failed", exc_info=True)

                # Send decoded data to higher layer
                await self._maybe_call_on_data(device)

        except ConnectionResetError:
            _LOGGER.warning("Client %s reset the connection", addr)
        finally:
            # Clean up and close connection
            self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # Forwarder setzen
    def set_forward_callback(self, callback: Optional[Callable[[bytes], Any]]) -> None:
        self._forward_cb = callback
        if callback:
            _LOGGER.info("Forward callback registriert")
        else:
            _LOGGER.info("Forward callback entfernt")

    @classmethod
    async def create(
        cls,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Optional[Callable[[AsekoDevice], Any]] = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
        log_helper: Optional[LoggingHelper] = None,
    ) -> "AsekoDeviceServer":
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoDeviceServer(
                host, port, on_data, raw_sink, log_helper
            )
            await cls._instances[key].start()
        else:
            if raw_sink:
                cls._instances[key]._raw_sink = raw_sink
            if on_data:
                cls._instances[key].on_data = on_data
            if log_helper:
                cls._instances[key]._log_helper = log_helper
        return cls._instances[key]

    @classmethod
    async def remove(cls, host: str, port: int) -> None:
        key = f"{host}:{port}"
        if key in cls._instances:
            await cls._instances[key].stop()
            del cls._instances[key]

    @classmethod
    async def remove_all(cls) -> None:
        """Stop all running servers and free sockets cleanly."""
        for srv in list(cls._instances.values()):
            await srv.stop()
        cls._instances.clear()


class ServerConnectionError(Exception):
    """Exception für Verbindungsfehler."""
