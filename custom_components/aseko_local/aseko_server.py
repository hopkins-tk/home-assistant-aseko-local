"""robust server for Aseko devices with forwarder."""

import asyncio
import logging
from collections.abc import Callable
from enum import Enum, auto
from typing import ClassVar, Optional, Any

from .aseko_data import AsekoDevice
from .aseko_decoder import AsekoDecoder
from .aseko_decoder_v8 import AsekoV8Decoder
from .const import (
    DEFAULT_BINDING_ADDRESS,
    DEFAULT_BINDING_PORT,
    MESSAGE_SIZE,
    READ_TIMEOUT,
    UNSPECIFIED_VALUE,
)

_LOGGER = logging.getLogger(__name__)


class FrameType(Enum):
    """Aseko frame protocol type."""

    BINARY = auto()  # Classic binary v7 frame (120 bytes)
    V8 = auto()  # Text-based v8 frame starting with '{'


class AsekoDeviceServer:
    """Async TCP server for receiving and parsing Aseko unit data."""

    _instances: ClassVar[dict[str, "AsekoDeviceServer"]] = {}

    def __init__(
        self,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Optional[Callable[[AsekoDevice], Any]] = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
        v8_raw_sink: Optional[Callable[[bytes], Any]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_data = on_data
        self._raw_sink = raw_sink
        self._v8_raw_sink = v8_raw_sink
        self._forward_cb: Optional[Callable[[bytes], Any]] = None
        self._forward_v8_cb: Optional[Callable[[bytes], Any]] = None
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

    async def _call_v8_raw_sink(self, data: bytes) -> None:
        if self._v8_raw_sink:
            try:
                await self._maybe_await(self._v8_raw_sink(data))
            except Exception:
                _LOGGER.error("v8 raw sink raised an exception", exc_info=True)

    async def _call_forward_cb(self, data: bytes) -> None:
        if self._forward_cb:
            try:
                _LOGGER.debug("Forward callback called with %d bytes", len(data))
                await self._maybe_await(self._forward_cb(data))
            except Exception:
                _LOGGER.error("Forward callback raised an exception", exc_info=True)

    async def _call_forward_v8_cb(self, data: bytes) -> None:
        if self._forward_v8_cb:
            try:
                _LOGGER.debug("v8 forward callback called with %d bytes", len(data))
                await self._maybe_await(self._forward_v8_cb(data))
            except Exception:
                _LOGGER.error("v8 forward callback raised an exception", exc_info=True)

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
                    # Read the first MESSAGE_SIZE bytes to detect frame type
                    initial = await asyncio.wait_for(
                        reader.readexactly(MESSAGE_SIZE), timeout=READ_TIMEOUT
                    )

                    _LOGGER.debug(
                        "Initial bytes from %s (%d bytes):\n%s",
                        addr,
                        len(initial),
                        initial.hex(" ", 1),  # print as spaced hex string
                    )

                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "No data received from %s for %d seconds, closing connection",
                        addr,
                        READ_TIMEOUT,
                    )
                    break

                except asyncio.IncompleteReadError as exc:
                    if len(exc.partial) == 0:
                        _LOGGER.debug(
                            "Client %s closed the connection",
                            addr,
                        )
                    else:
                        _LOGGER.error(
                            "Client %s closed the connection after %d bytes (expected %d):\n%s",
                            addr,
                            len(exc.partial),
                            MESSAGE_SIZE,
                            exc.partial.hex(" ", 1),
                        )
                        # Store partial frame for diagnostics so users with non-standard
                        # frame lengths can share the raw data without enabling debug logging.
                        await self._call_raw_sink(exc.partial)
                    break

                # Detect frame type, assemble and rewind if necessary
                try:
                    frame, offset, frame_type = await self._sync_frame(reader, initial)
                except Exception:
                    _LOGGER.error(
                        "Frame sync error from %s → closing connection",
                        addr,
                        exc_info=True,
                    )
                    break

                # v8 text frame: decode, forward, deliver to on_data
                if frame_type == FrameType.V8:
                    await self._call_forward_v8_cb(frame)
                    try:
                        device = AsekoV8Decoder.decode(frame)
                        await self._call_v8_raw_sink(frame)
                    except ValueError as exc:
                        _LOGGER.error(
                            "v8 decode error from %s: %s → closing connection",
                            addr,
                            exc,
                        )
                        break
                    except Exception:
                        _LOGGER.error(
                            "v8 decode error from %s → closing connection",
                            addr,
                            exc_info=True,
                        )
                        break
                    _LOGGER.debug("v8 decoded data from %s: %s", addr, device)
                    await self._maybe_call_on_data(device)
                    continue

                # BINARY path — frame is already rewound by _sync_frame
                try:
                    # Call raw_sink so diagnostics see the correctly aligned frame
                    await self._call_raw_sink(frame)

                    # Forward CORRECTED data to cloud
                    await self._call_forward_cb(frame)

                    # 🔎 Plausibility check before decoding: pH values must be between 0 and 14
                    # 0xFF 0xFF (UNSPECIFIED_VALUE) means the probe is absent — skip the check
                    if (
                        frame[14] != UNSPECIFIED_VALUE
                        and frame[15] != UNSPECIFIED_VALUE
                    ):
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

                # If frame had to be rewound, close connection AFTER processing
                # to force realignment on reconnect
                if offset > 0:
                    _LOGGER.info(
                        "Frame was offset by %d bytes, closing connection to force realignment",
                        offset,
                    )
                    break  # Exit loop to close and allow reconnection

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

    def set_forward_v8_callback(
        self, callback: Optional[Callable[[bytes], Any]]
    ) -> None:
        self._forward_v8_cb = callback
        if callback:
            _LOGGER.debug("v8 forward callback registered")
        else:
            _LOGGER.debug("v8 forward callback removed")

    async def _sync_frame(
        self, reader: asyncio.StreamReader, initial: bytes
    ) -> tuple[bytes, int, FrameType]:
        """Detect frame type, assemble the complete frame, and rewind if necessary.

        Scans the initial MESSAGE_SIZE bytes for the v8 signature b"{v1 ".
        If found, any bytes before it are discarded (logged as a warning when
        offset > 0) and the remaining text frame is read until the closing '}'.

        For binary (v7) frames, the rewind check is applied to the initial
        MESSAGE_SIZE bytes and the corrected frame is returned together with
        the rewind offset (0 if no rewind was needed).

        Returns:
            tuple[bytes, int, FrameType]: (clean_frame, rewind_offset, frame_type)
        """
        brace_pos = initial.find(b"{v1 ")
        if brace_pos >= 0:
            if brace_pos > 0:
                prefix = initial[:brace_pos]
                if all(b in b"\r\n\t\x00" for b in prefix):
                    # Normal frame separator (e.g. \n between frames) — not a real shift
                    _LOGGER.debug(
                        "v8 frame: skipping %d separator byte(s) before '{'", brace_pos
                    )
                else:
                    _LOGGER.warning(
                        "v8 frame shifted by %d bytes — discarding prefix", brace_pos
                    )
            v8_data = initial[brace_pos:]
            try:
                rest = await asyncio.wait_for(
                    reader.readuntil(b"\n"), timeout=READ_TIMEOUT
                )
                return v8_data + rest, brace_pos, FrameType.V8
            except asyncio.IncompleteReadError as exc:
                return v8_data + exc.partial, brace_pos, FrameType.V8
        data, offset = self._rewind_binary(initial)
        return data, offset, FrameType.BINARY

    def _rewind_binary(self, data: bytes) -> tuple[bytes, int]:
        """Rewind misaligned binary frame to the correct start position.

        Sometimes the TCP stream gets out of sync and the frame
        starts at an offset. This function searches for the correct
        start position and rewinds the frame accordingly.

        Returns:
            tuple[bytes, int]: (rewound_frame, offset)
        """

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

        return data, offset

    @classmethod
    async def create(
        cls,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Optional[Callable[[AsekoDevice], Any]] = None,
        raw_sink: Optional[Callable[[bytes], Any]] = None,
        v8_raw_sink: Optional[Callable[[bytes], Any]] = None,
    ) -> "AsekoDeviceServer":
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoDeviceServer(host, port, on_data, raw_sink, v8_raw_sink)
            await cls._instances[key].start()
        else:
            if raw_sink:
                cls._instances[key]._raw_sink = raw_sink
            if v8_raw_sink:
                cls._instances[key]._v8_raw_sink = v8_raw_sink
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
