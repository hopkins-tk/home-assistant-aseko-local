"""robust server for Aseko devices with forwarder."""

import asyncio
import logging
from collections.abc import Callable
from typing import ClassVar, Optional, Any

from .aseko_data import AsekoDevice
from .aseko_decoder import AsekoDecoder
from .const import DEFAULT_BINDING_ADDRESS, DEFAULT_BINDING_PORT, MESSAGE_SIZE

_LOGGER = logging.getLogger(__name__)


class AsekoDeviceServer:
    """Async TCP server for receiving and parsing Aseko unit data."""

    _instances: ClassVar[dict[str, "AsekoDeviceServer"]] = {}

    def __init__(
        self,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Optional[Callable[[AsekoDevice], Any]] = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_data = on_data
        self._raw_sink = raw_sink
        self._forward_cb: Optional[Callable[[bytes], Any]] = None
        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        """Start of the TCP server."""

        try:
            self._server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )
            _LOGGER.debug("AsekoDeviceServer startet on %s:%d", self.host, self.port)
        except OSError as err:
            _LOGGER.error("AsekoDeviceServer start failed: %s", err)
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
            _LOGGER.debug("AsekoDeviceServer stopped on %s:%d", self.host, self.port)

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
                _LOGGER.error("Raw sink raised an exception", exc_info=True)

    async def _call_forward_cb(self, data: bytes) -> None:
        if self._forward_cb:
            try:
                _LOGGER.debug("Forward callback called with %d bytes", len(data))
                await self._maybe_await(self._forward_cb(data))
            except Exception:
                _LOGGER.error("Forward callback raised an exception", exc_info=True)

    async def _maybe_call_on_data(self, device: AsekoDevice) -> None:
        if self.on_data:
            try:
                await self._maybe_await(self.on_data(device))
            except Exception:
                _LOGGER.error("on_data callback raised an exception", exc_info=True)

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

                    _LOGGER.debug(
                        "Frame received from %s (%d bytes):\n%s",
                        addr,
                        len(frame),
                        frame.hex(" ", 1),  # print as spaced hex string
                    )

                except asyncio.IncompleteReadError:
                    _LOGGER.error("Client %s closed the connection", addr)
                    break

                # Forward raw data (e.g. for debugging or mirroring)
                await self._call_raw_sink(frame)
                await self._call_forward_cb(frame)

                # Try to decode the frame
                try:
                    frame = self._rewind_frame(frame)

                    # 🔎 Plausibility check before decoding: pH values must be between 0 and 14
                    ph_value = int.from_bytes(frame[14:16], "big") / 100
                    if not (0 <= ph_value <= 14):
                        _LOGGER.error(
                            "Unreasonable pH value (%s) received from %s → closing connection",
                            ph_value,
                            addr,
                        )
                        break  # leave loop → connection will be closed

                    required_ph = frame[52] / 10
                    if not (6 <= required_ph <= 10):
                        _LOGGER.error(
                            "Unreasonable required pH value (%s) received from %s → closing connection",
                            required_ph,
                            addr,
                        )
                        break  # leave loop → connection will be closed

                    device = AsekoDecoder.decode(frame)

                except ValueError as e:
                    _LOGGER.error(
                        "Invalid frame from %s: %s → closing connection", addr, e
                    )
                    break

                except Exception:
                    _LOGGER.error(
                        "Decoding error for data from %s → closing connection", addr
                    )
                    break

                _LOGGER.debug("Decoded data from %s: %s", addr, device)

                # Send decoded data to higher layer
                await self._maybe_call_on_data(device)

        except ConnectionResetError:
            _LOGGER.error("Client %s resets the connection", addr)
        finally:
            # Clean up and close connection
            self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # Set Forwarder
    def set_forward_callback(self, callback: Optional[Callable[[bytes], Any]]) -> None:
        self._forward_cb = callback
        if callback:
            _LOGGER.debug("Forward callback registered")
        else:
            _LOGGER.debug("Forward callback removed")

    def _rewind_frame(self, data: bytes) -> bytes:
        """Rewind the frame to the start position for processing."""

        offset = 0
        while (
            data[offset + 5] != 0x01
            or data[offset + 45] != 0x03
            or data[offset + 85] != 0x02
            or data[offset : offset + 4] != data[offset + 40 : offset + 44]
            or data[offset + 40 : offset + 44] != data[offset + 80 : offset + 84]
        ):
            offset += 1

        if offset == 0:
            _LOGGER.debug(
                "Frame did not have to be rewinded",
            )
        else:
            # Rewind the frame
            data = data[offset:] + data[:offset]

            _LOGGER.warning(
                "Frame has been rewinded by %d bytes:\n%s",
                offset,
                data.hex(" ", 1),  # print as spaced hex string
            )

        return data

    @classmethod
    async def create(
        cls,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Optional[Callable[[AsekoDevice], Any]] = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
    ) -> "AsekoDeviceServer":
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoDeviceServer(host, port, on_data, raw_sink)
            await cls._instances[key].start()
        else:
            if raw_sink:
                cls._instances[key]._raw_sink = raw_sink
            if on_data:
                cls._instances[key].on_data = on_data
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
    """Exception for connection error."""
