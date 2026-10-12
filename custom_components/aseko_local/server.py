"""robust server for Aseko devices with forwarder."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, ClassVar, TypedDict, Unpack

from .const import (
    DEFAULT_BINDING_ADDRESS,
    DEFAULT_BINDING_PORT,
    MESSAGE_SIZE,
    READ_TIMEOUT,
    UNSPECIFIED_VALUE,
)
from .decoding import Protocol, decode
from .models import AsekoDevice

_LOGGER = logging.getLogger(__name__)


class FrameType(Enum):
    """Aseko frame protocol type."""

    BINARY = auto()  # Classic binary v7 frame (120 bytes)
    V8 = auto()  # Text-based v8 frame starting with '{'


V8_SIGNATURE = b"{v1 "
# (serial, reason) pairs remembered for "warn once"; past this every repeat
# is logged at debug level, so an odd stream cannot grow the set forever
MAX_WARNED = 1000

# What a plausible v7 frame reads (a hint for diagnostics only)
PH_MIN, PH_MAX = 0, 14
PH_TARGET_MIN, PH_TARGET_MAX = 6, 10

# A v7 frame is three 40-byte segments; byte 5 of each names its type
V7_SEGMENT_TYPES = {5: 0x01, 45: 0x03, 85: 0x02}


async def _read_initial(reader: asyncio.StreamReader, buffered: bytes) -> bytes:
    """Read until MESSAGE_SIZE bytes are in, or a whole v8 frame is.

    A complete short v8 frame is handled at once, not after the next message
    or the read timeout.  Raises ``asyncio.IncompleteReadError`` with the
    newly read bytes when the unit hangs up first.
    """
    data = buffered
    while len(data) < MESSAGE_SIZE and not _holds_whole_v8_frame(data):
        chunk = await asyncio.wait_for(
            reader.read(MESSAGE_SIZE - len(data)), timeout=READ_TIMEOUT
        )
        if not chunk:
            raise asyncio.IncompleteReadError(data[len(buffered) :], MESSAGE_SIZE)
        data += chunk
    return data


def _holds_whole_v8_frame(data: bytes) -> bool:
    """Return True when ``data`` already starts with a complete v8 frame."""
    return data.lstrip(b"\r\n\t\x00").startswith(V8_SIGNATURE) and b"\n" in data


class ServerSinks(TypedDict, total=False):
    """Where the server hands what it reads besides decoded devices."""

    #: every aligned v7 frame, and a fragment when the unit hangs up early
    raw_sink: Callable[[bytes], Any] | None
    #: every v8 text frame, before it is decoded
    v8_raw_sink: Callable[[bytes], Any] | None
    #: (serial number, reason) of an implausible frame
    frame_warning_sink: Callable[[int, str], Any] | None
    #: bytes that could not be aligned into a frame, with the reason
    rejected_sink: Callable[[bytes, str], Any] | None


class AsekoDeviceServer:
    """Async TCP server for receiving and parsing Aseko unit data."""

    _instances: ClassVar[dict[str, "AsekoDeviceServer"]] = {}

    def __init__(
        self,
        host: str = DEFAULT_BINDING_ADDRESS,
        port: int = DEFAULT_BINDING_PORT,
        on_data: Callable[[AsekoDevice], Any] | None = None,
        **sinks: Unpack[ServerSinks],
    ) -> None:
        """Set up a server for ``host``:``port``; ``start`` opens it."""
        self.host = host
        self.port = port
        self.on_data = on_data
        self._raw_sink = sinks.get("raw_sink")
        self._v8_raw_sink = sinks.get("v8_raw_sink")
        self._frame_warning_sink = sinks.get("frame_warning_sink")
        # bytes that could not be aligned into a frame, with the reason
        self._rejected_sink = sinks.get("rejected_sink")
        # (serial, reason) pairs already logged as a warning; repeats go to
        # debug so a unit that keeps sending them does not flood the log.
        self._warned: set[tuple[int, str]] = set()
        self._forward_cb: Callable[[bytes], Any] | None = None
        self._forward_v8_cb: Callable[[bytes], Any] | None = None
        self._server: asyncio.AbstractServer | None = None
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
            msg = f"Failed to start server: {err}"
            raise ServerConnectionError(msg) from err

    async def stop(self) -> None:
        """Stop the TCP server and disconnect all clients."""

        if self._server:
            for w in list(self._clients):
                # a client that is gone already needs no closing
                with contextlib.suppress(Exception):
                    w.close()
                    await w.wait_closed()
            self._clients.clear()
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            _LOGGER.debug("AsekoDeviceServer stopped on %s:%d", self.host, self.port)

    @property
    def running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None and self._server.is_serving()

    async def _safe_call(
        self, callback: Callable[..., Any] | None, *args: object, name: str
    ) -> None:
        """Call a sink or callback that may be async; one that raises costs only its own call."""
        if callback is None:
            return
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            _LOGGER.exception("%s raised an exception", name)

    def _log_once(self, serial: int, reason: str, message: str, *args: object) -> None:
        """Log a unit's problem as a warning the first time, at debug level after.

        The register of (serial, reason) pairs is capped at MAX_WARNED, so an
        odd stream cannot grow it forever; past the cap everything is debug.
        """
        key = (serial, reason)
        first = key not in self._warned and len(self._warned) < MAX_WARNED
        if first:
            self._warned.add(key)
        (_LOGGER.warning if first else _LOGGER.debug)(message, *args)

    @staticmethod
    def _implausible_values(frame: bytes) -> list[str]:
        """Return why a v7 frame looks implausible, empty if it does not.

        Only a hint for diagnostics: such a frame is still decoded, because a
        unit nobody has mapped yet may lay its bytes out differently.
        """
        reasons = []
        # 0xFF 0xFF (UNSPECIFIED_VALUE) means the probe is absent
        if frame[14] != UNSPECIFIED_VALUE and frame[15] != UNSPECIFIED_VALUE:
            ph_value = int.from_bytes(frame[14:16], "big") / 100
            if not PH_MIN <= ph_value <= PH_MAX:
                reasons.append(f"pH {ph_value} outside {PH_MIN}-{PH_MAX}")
        ph_target = frame[52] / 10
        if not PH_TARGET_MIN <= ph_target <= PH_TARGET_MAX:
            reasons.append(
                f"required pH {ph_target} outside {PH_TARGET_MIN}-{PH_TARGET_MAX}"
            )
        return reasons

    async def _report_implausible(self, frame: bytes, addr: object) -> None:
        serial = int.from_bytes(frame[0:4], "big")
        for reason in self._implausible_values(frame):
            self._log_once(
                serial,
                reason,
                "Implausible v7 frame from %s (serial %s): %s; decoding it anyway",
                addr,
                serial,
                reason,
            )
            await self._safe_call(
                self._frame_warning_sink, serial, reason, name="Frame warning sink"
            )

    async def _report_frame_problems(self, device: AsekoDevice, addr: object) -> None:
        """Log and count values the parser could not read; the frame still counts."""
        serial = device.serial_number
        if serial is None:
            return
        for problem in device.frame_problems:
            reason = f"v8 value unreadable: {problem}"
            self._log_once(
                serial, reason, "v8 frame from %s (serial %s): %s", addr, serial, reason
            )
            await self._safe_call(
                self._frame_warning_sink, serial, reason, name="Frame warning sink"
            )

    async def _report_rejected_v8(self, frame: bytes, reason: str) -> None:
        """Count a v8 frame the decoder rejected, under its serial if readable."""
        if not self._frame_warning_sink:
            return
        try:
            serial = int(
                frame.decode("ascii", errors="replace").lstrip("{ ").split()[1]
            )
        except (ValueError, IndexError):
            return
        await self._safe_call(
            self._frame_warning_sink,
            serial,
            f"v8 frame rejected: {reason}",
            name="Frame warning sink",
        )

    def replace_sinks(self, **sinks: Unpack[ServerSinks]) -> None:
        """Take the sinks of a new config entry; one not given keeps the old."""
        if raw_sink := sinks.get("raw_sink"):
            self._raw_sink = raw_sink
        if v8_raw_sink := sinks.get("v8_raw_sink"):
            self._v8_raw_sink = v8_raw_sink
        if frame_warning_sink := sinks.get("frame_warning_sink"):
            self._frame_warning_sink = frame_warning_sink
        if rejected_sink := sinks.get("rejected_sink"):
            self._rejected_sink = rejected_sink

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        _LOGGER.debug("Connection from %s", addr)
        self._clients.add(writer)

        # Bytes read past the end of the previous frame: a short v8 frame
        # ends inside the first MESSAGE_SIZE bytes, and what follows it is
        # the start of the next message, not part of this one.
        carry = b""
        try:
            while True:
                step = await self._read_message(reader, carry, addr)
                if step is None:
                    break
                initial, carry = step
                if initial is None:
                    continue  # a whole v8 frame is carried over

                # Detect frame type, assemble and rewind if necessary
                try:
                    rest: list[bytes] = []
                    frame, offset, frame_type = await self._sync_frame(
                        reader, initial, rest
                    )
                    # the moment the frame is complete: the unit's clock is
                    # compared with it, so it is taken before any decoding
                    received_at = datetime.now(UTC)
                    carry = b"".join(rest)
                except Exception as exc:
                    _LOGGER.exception(
                        "Frame sync error from %s → closing connection", addr
                    )
                    # Keep the bytes: they are what a new layout would look like.
                    await self._safe_call(
                        self._rejected_sink,
                        initial,
                        f"frame sync failed: {type(exc).__name__}: {exc}",
                        name="Rejected sink",
                    )
                    break

                if frame_type == FrameType.V8:
                    if not await self._deliver_v8(frame, addr, received_at):
                        break
                    continue
                if not await self._deliver_v7(frame, addr, received_at):
                    break

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
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _read_message(
        self, reader: asyncio.StreamReader, buffered: bytes, addr: object
    ) -> tuple[bytes | None, bytes] | None:
        """Return the first bytes of the next message and what is carried after them.

        None: the connection is done (quiet too long, or the unit hung up).
        ``(None, carry)``: the unit hung up right after a whole short v8
        frame, which is carried over to be handled next.
        """
        try:
            if _holds_whole_v8_frame(buffered):
                initial, carry = buffered, b""
            else:
                # Read up to MESSAGE_SIZE bytes to detect the frame type --
                # or less, once a whole short v8 frame is in
                initial, carry = await _read_initial(reader, buffered), b""
                if len(initial) > MESSAGE_SIZE and V8_SIGNATURE not in initial:
                    initial, carry = initial[:MESSAGE_SIZE], initial[MESSAGE_SIZE:]
        except TimeoutError:
            _LOGGER.debug(
                "No data received from %s for %d seconds, closing connection",
                addr,
                READ_TIMEOUT,
            )
            return None
        except asyncio.IncompleteReadError as exc:
            partial = buffered + exc.partial
            if _holds_whole_v8_frame(partial):
                # a short v8 frame right before the unit hung up
                return None, partial
            if not partial:
                _LOGGER.debug("Client %s closed the connection", addr)
            else:
                _LOGGER.error(
                    "Client %s closed the connection after %d bytes (expected %d):\n%s",
                    addr,
                    len(partial),
                    MESSAGE_SIZE,
                    partial.hex(" ", 1),
                )
                # Store partial frame for diagnostics so users with non-standard
                # frame lengths can share the raw data without enabling debug logging.
                await self._safe_call(self._raw_sink, partial, name="Raw sink")
            return None
        _LOGGER.debug(
            "Initial bytes from %s (%d bytes):\n%s",
            addr,
            len(initial),
            initial.hex(" ", 1),  # print as spaced hex string
        )
        return initial, carry

    async def _deliver_v8(
        self, frame: bytes, addr: object, received_at: datetime
    ) -> bool:
        """Forward, log, decode and hand on a v8 frame; False closes the connection."""
        if self._forward_v8_cb:
            _LOGGER.debug("v8 forward callback called with %d bytes", len(frame))
        await self._safe_call(self._forward_v8_cb, frame, name="v8 forward callback")
        # Log the frame before decoding it: a frame the decoder rejects is
        # exactly the one worth having in the frame log.
        await self._safe_call(self._v8_raw_sink, frame, name="v8 raw sink")
        try:
            device = decode(frame, Protocol.V8)
        except ValueError as exc:
            _LOGGER.error("v8 decode error from %s: %s → closing connection", addr, exc)
            await self._report_rejected_v8(frame, str(exc))
            return False
        except Exception:
            _LOGGER.exception("v8 decode error from %s → closing connection", addr)
            return False
        await self._report_frame_problems(device, addr)
        _LOGGER.debug("v8 decoded data from %s: %s", addr, device)
        device.received_at = received_at
        await self._safe_call(self.on_data, device, name="on_data callback")
        return True

    async def _deliver_v7(
        self, frame: bytes, addr: object, received_at: datetime
    ) -> bool:
        """Log, forward, decode and hand on an aligned v7 frame; False closes."""
        try:
            # Call raw_sink so diagnostics see the correctly aligned frame
            await self._safe_call(self._raw_sink, frame, name="Raw sink")
            # Forward CORRECTED data to cloud
            if self._forward_cb:
                _LOGGER.debug("Forward callback called with %d bytes", len(frame))
            await self._safe_call(self._forward_cb, frame, name="Forward callback")
            # Implausible values are reported, not fatal: the frame is still
            # decoded and the connection stays open.
            await self._report_implausible(frame, addr)
            device = decode(frame, Protocol.V7)
        except ValueError as e:
            _LOGGER.error("Invalid frame from %s: %s → closing connection", addr, e)
            return False
        except Exception:
            _LOGGER.exception(
                "Decoding error for data from %s → closing connection", addr
            )
            return False
        _LOGGER.debug("Decoded data from %s: %s", addr, device)
        # Send decoded data to higher layer
        device.received_at = received_at
        await self._safe_call(self.on_data, device, name="on_data callback")
        return True

    # Set Forwarder
    def set_forward_callback(self, callback: Callable[[bytes], Any] | None) -> None:
        """Set or clear where v7 frames are forwarded."""
        self._forward_cb = callback
        if callback:
            _LOGGER.debug("Forward callback registered")
        else:
            _LOGGER.debug("Forward callback removed")

    def set_forward_v8_callback(self, callback: Callable[[bytes], Any] | None) -> None:
        """Set or clear where v8 frames are forwarded."""
        self._forward_v8_cb = callback
        if callback:
            _LOGGER.debug("v8 forward callback registered")
        else:
            _LOGGER.debug("v8 forward callback removed")

    async def _sync_frame(
        self,
        reader: asyncio.StreamReader,
        initial: bytes,
        rest: list[bytes] | None = None,
    ) -> tuple[bytes, int, FrameType]:
        r"""Detect frame type, assemble the complete frame, and rewind if necessary.

        Scans the initial MESSAGE_SIZE bytes for the v8 signature b"{v1 ".
        If found, any bytes before it are discarded (logged as a warning when
        offset > 0) and the remaining text frame is read until its terminating
        newline byte (``b"\\n"``), which is included in the returned frame when
        present.

        For binary (v7) frames, the rewind check is applied to the initial
        MESSAGE_SIZE bytes and the corrected frame is returned together with
        the rewind offset (0 if no rewind was needed).

        A v8 frame that already ends inside ``initial`` stops at its newline;
        the bytes after it are appended to ``rest`` for the next frame.

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
            newline = v8_data.find(b"\n")
            if newline >= 0:
                if rest is not None:
                    rest.append(v8_data[newline + 1 :])
                return v8_data[: newline + 1], brace_pos, FrameType.V8
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
            any(
                data[offset + position] != kind
                for position, kind in V7_SEGMENT_TYPES.items()
            )
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
        on_data: Callable[[AsekoDevice], Any] | None = None,
        **sinks: Unpack[ServerSinks],
    ) -> "AsekoDeviceServer":
        """Return the running server for ``host``:``port``, started when new."""
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoDeviceServer(host, port, on_data, **sinks)
            await cls._instances[key].start()
        else:
            cls._instances[key].replace_sinks(**sinks)
            if on_data:
                cls._instances[key].on_data = on_data
            # A server stopped by an unload that did not remove it stays in the
            # registry; hand it back running -- after the new callbacks are in
            # place, or the first frames would go to the old ones.
            if not cls._instances[key].running:
                await cls._instances[key].start()
        return cls._instances[key]

    @classmethod
    async def remove(cls, host: str, port: int) -> None:
        """Stop the server for ``host``:``port`` and forget it."""
        key = f"{host}:{port}"
        if key in cls._instances:
            await cls._instances[key].stop()
            del cls._instances[key]

    @classmethod
    def get(cls, host: str, port: int) -> "AsekoDeviceServer | None":
        """Return the server registered for ``host:port``, if any."""
        return cls._instances.get(f"{host}:{port}")

    @classmethod
    async def remove_all(cls) -> None:
        """Stop all running servers and free sockets cleanly."""
        for srv in list(cls._instances.values()):
            await srv.stop()
        cls._instances.clear()


class ServerConnectionError(Exception):
    """Exception for connection error."""
