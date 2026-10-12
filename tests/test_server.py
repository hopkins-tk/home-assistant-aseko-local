import asyncio
import logging

import pytest

from custom_components.aseko_local import server as server_module
from custom_components.aseko_local.coordinator import (
    MAX_WARNING_REASONS,
    OTHER_WARNING_REASONS,
)
from custom_components.aseko_local.models import AsekoDevice
from custom_components.aseko_local.server import (
    AsekoDeviceServer,
    FrameType,
    ServerConnectionError,
)

from .test_entity_growth import _coordinator


# Hilfsfunktion: Hex-String zu Bytes
def hexstr_to_bytes(s: str) -> bytes:
    return bytes.fromhex(s.replace("\n", "").replace(" ", ""))


# Reales gültiges Frame (gekürzt für Beispiel)
VALID_FRAME_HEX = (
    "069187240901ffffffffffff000402da0027ffff0095ff01400149ff000006640000000000ff006c"
    "069187240903ffffffffffff480a08ffffffffffffffffff027e0149ffffffffffffffffffffffea"
    "069187240902ffffffffffff0001003cffff003cffff010383ff00781e02581e28ffffffff0049a9"
)
VALID_FRAME2_HEX = (
    "069187250901ffffffffffff000402da0027ffff0095ff01400149ff000006640000000000ff006c"
    "069187250903ffffffffffff480a08ffffffffffffffffff027e0149ffffffffffffffffffffffea"
    "069187250902ffffffffffff0001003cffff003cffff010383ff00781e02581e28ffffffff0049a9"
)
VALID_FRAME = hexstr_to_bytes(VALID_FRAME_HEX)  # MESSAGE_SIZE = 120
VALID_FRAME2 = hexstr_to_bytes(VALID_FRAME2_HEX)  # MESSAGE_SIZE = 120

# Korruptes Frame: pH Wert ungültig (z.B. 99.99)
CORRUPT_FRAME = bytearray(VALID_FRAME)
CORRUPT_FRAME[14:16] = (9999).to_bytes(2, "big")  # pH = 99.99


class DummyWriter:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass

    def get_extra_info(self, name: str) -> tuple[str, int] | None:
        # Simuliere Peername für Tests
        if name == "peername":
            return (self.host, self.port)
        return None


class DummyServer:
    def is_serving(self) -> bool:
        return True

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


@pytest.mark.asyncio
async def test_valid_device_frame(monkeypatch) -> None:
    """Test: Bestehendes Device wird erkannt und verarbeitet."""

    called = {}

    async def on_data(device: AsekoDevice) -> None:
        called["serial"] = device.serial_number

    async def dummy_start_server(handler, host, port) -> DummyServer:
        # Simulate a connection with valid data
        reader = asyncio.StreamReader()
        writer = DummyWriter("127.0.0.1", 12344)
        reader.feed_data(VALID_FRAME)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12344, on_data=on_data
    )
    assert server.running
    # Serial number should be captured
    assert "serial" in called
    assert called["serial"] == 110200612
    await server.stop()


@pytest.mark.asyncio
async def test_multiple_valid_device_frames(monkeypatch) -> None:
    """Test: Multiple valid device frames are processed correctly."""

    called = []

    async def on_data(device: AsekoDevice) -> None:
        called.append(device)

    async def dummy_start_server(handler, host, port) -> DummyServer:
        # Simulate a connection with valid data
        writer = DummyWriter("127.0.0.1", 12345)

        reader = asyncio.StreamReader()
        reader.feed_data(VALID_FRAME)
        reader.feed_eof()
        await handler(reader, writer)

        reader = asyncio.StreamReader()
        reader.feed_data(VALID_FRAME2)
        reader.feed_eof()
        await handler(reader, writer)

        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12345, on_data=on_data
    )
    assert server.running
    # 2 serial numbers should be captured
    assert len(called) == 2
    assert called[0].serial_number == 110200612
    assert called[1].serial_number == 110200613
    await server.stop()


@pytest.mark.asyncio
async def test_implausible_frame_is_decoded_and_reported(monkeypatch) -> None:
    """An implausible pH no longer closes the connection.

    The frame is still decoded and handed on -- a unit nobody has mapped may
    lay its bytes out differently -- the reason goes to the warning sink for
    diagnostics, and the next frame on the same connection is read too.
    """

    devices: list[AsekoDevice] = []
    warnings: list[tuple[int, str]] = []

    async def on_data(device: AsekoDevice) -> None:
        devices.append(device)

    def frame_warning_sink(serial: int, reason: str) -> None:
        warnings.append((serial, reason))

    async def dummy_start_server(handler, host, port) -> DummyServer:
        reader = asyncio.StreamReader()
        writer = DummyWriter("127.0.0.1", 12346)
        reader.feed_data(bytes(CORRUPT_FRAME) + VALID_FRAME2)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1",
        port=12346,
        on_data=on_data,
        frame_warning_sink=frame_warning_sink,
    )
    assert server.running
    assert [d.serial_number for d in devices] == [110200612, 110200613]
    assert warnings == [(110200612, "pH 99.99 outside 0-14")]
    await server.stop()


@pytest.mark.asyncio
async def test_issue_61_shifted_frame(monkeypatch) -> None:
    """Test: Shifted frame from issue 61."""

    byte_frame = hexstr_to_bytes(
        "0f0f1e14ffbf02970690cafe0301190a12103232000402cb015201520152a3fe700099fe00080000"
        "00000000001302670690cafe0303190a121032324842011d080f122d15001737027600a9000c1e0a"
        "012801e00e10a2020690cafe0302190a12103232002d003c003c003c000a1e3c6e9600f00802580f"
    )

    called = {}

    async def on_data(device: AsekoDevice) -> None:
        called["serial"] = device.serial_number

    async def dummy_start_server(handler, host, port) -> DummyServer:
        # Simulate a connection with valid data
        reader = asyncio.StreamReader()
        writer = DummyWriter("127.0.0.1", 12347)
        reader.feed_data(byte_frame)
        reader.feed_eof()
        await handler(reader, writer)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)

    server = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12347, on_data=on_data
    )
    assert server.running
    # Serial number should be captured
    assert "serial" in called
    assert called["serial"] == 110152446
    await server.stop()


# ---------------------------------------------------------------------------
# v8 frame tests
# ---------------------------------------------------------------------------

# Minimal synthetic v8 frame: starts with '{v1 ', ends with '}'
V8_INITIAL = b"{v1 12345678" + b" " * 108  # 120 bytes, starts with '{v1 '
assert len(V8_INITIAL) == 120
V8_REST = (
    b" ins: 0000 outs: 0000 crc16: ABCD}\n"  # read by readuntil(b'\n'), includes \n
)
V8_FULL_FRAME = V8_INITIAL + V8_REST  # exact bytes the device sends

# Shifted v8 frame: 3 garbage prefix bytes before the '{v1 ' signature
V8_SHIFTED_PREFIX = b"\x00\x00\x00"
V8_SHIFTED_INITIAL = V8_SHIFTED_PREFIX + b"{v1 12345678" + b" " * 105  # 120 bytes
assert len(V8_SHIFTED_INITIAL) == 120
V8_SHIFTED_FULL_FRAME = V8_SHIFTED_INITIAL[3:] + V8_REST  # starts at '{', exact bytes


@pytest.mark.asyncio
async def test_v8_frame_forwarded_before_decode() -> None:
    """v8 frames must be forwarded even if the frame body is unparseable."""

    v8_forwarded = {}

    async def v8_forward_cb(frame: bytes) -> None:
        v8_forwarded["frame"] = frame

    server = AsekoDeviceServer(host="127.0.0.1", port=12350, on_data=None)
    server.set_forward_v8_callback(v8_forward_cb)

    reader = asyncio.StreamReader()
    writer = DummyWriter("127.0.0.1", 12350)
    reader.feed_data(V8_FULL_FRAME)
    reader.feed_eof()
    await server._handle_client(reader, writer)

    # forward callback must have received the full frame
    assert "frame" in v8_forwarded
    assert v8_forwarded["frame"] == V8_FULL_FRAME


# Real parseable v8 frame — same as REFERENCE_FRAME in test_decode_v8.py
_V8_REAL_FRAME = (
    b"{v1 123456789 804 0 27 "
    b"ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0 "
    b"ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0 "
    b"outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"areqs: 74 73 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 "
    b"reqs: 0 0 0 0 0 0 0 24 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 "
    b"fncs: 0 0 3 0 0 0 2 0 "
    b"mods: 2 0 0 1 0 0 0 0 "
    b"flags: 2 0 0 0 0 0 0 0 "
    b"crc16: C3C8}\n"
)
# Split at the 120-byte mark for _sync_frame
_V8_REAL_INITIAL = _V8_REAL_FRAME[:120]
_V8_REAL_REST = _V8_REAL_FRAME[120:]


@pytest.mark.asyncio
async def test_v8_frame_decoded_and_delivered() -> None:
    """A valid v8 frame must be decoded and delivered to on_data."""

    received = {}

    async def on_data(device: AsekoDevice) -> None:
        received["device"] = device

    server = AsekoDeviceServer(host="127.0.0.1", port=12350, on_data=on_data)

    reader = asyncio.StreamReader()
    writer = DummyWriter("127.0.0.1", 12350)
    reader.feed_data(_V8_REAL_FRAME)
    reader.feed_eof()
    await server._handle_client(reader, writer)

    assert "device" in received
    assert received["device"].serial_number == 123456789


@pytest.mark.asyncio
async def test_sync_frame_binary_returns_binary_type() -> None:
    """_sync_frame must return FrameType.BINARY for a non-v8 initial chunk."""

    server = AsekoDeviceServer.__new__(AsekoDeviceServer)

    reader = asyncio.StreamReader()
    frame, offset, frame_type = await server._sync_frame(reader, VALID_FRAME)
    assert frame_type == FrameType.BINARY
    assert offset == 0
    assert frame == VALID_FRAME


@pytest.mark.asyncio
async def test_sync_frame_v8_returns_v8_type() -> None:
    """_sync_frame must return FrameType.V8 when initial chunk starts with '{'."""

    server = AsekoDeviceServer.__new__(AsekoDeviceServer)

    reader = asyncio.StreamReader()
    reader.feed_data(V8_REST)
    reader.feed_eof()

    full, offset, frame_type = await server._sync_frame(reader, V8_INITIAL)
    assert frame_type == FrameType.V8
    assert offset == 0
    assert full == V8_FULL_FRAME


@pytest.mark.asyncio
async def test_sync_frame_v8_shifted() -> None:
    """_sync_frame must find '{v1 ' past a garbage prefix and return correct offset."""

    server = AsekoDeviceServer.__new__(AsekoDeviceServer)

    reader = asyncio.StreamReader()
    reader.feed_data(V8_REST)
    reader.feed_eof()

    full, offset, frame_type = await server._sync_frame(reader, V8_SHIFTED_INITIAL)
    assert frame_type == FrameType.V8
    assert offset == len(V8_SHIFTED_PREFIX)  # 3
    assert full == V8_SHIFTED_FULL_FRAME


@pytest.mark.asyncio
async def test_sync_frame_binary_shifted() -> None:
    """_sync_frame must rewind a shifted binary frame via _rewind_binary."""

    # This is the issue-61 frame: 8 bytes of a previous frame's tail precede
    # the actual aligned frame content.
    shifted_binary = hexstr_to_bytes(
        "0f0f1e14ffbf02970690cafe0301190a12103232000402cb015201520152a3fe700099fe00080000"
        "00000000001302670690cafe0303190a121032324842011d080f122d15001737027600a9000c1e0a"
        "012801e00e10a2020690cafe0302190a12103232002d003c003c003c000a1e3c6e9600f00802580f"
    )

    server = AsekoDeviceServer.__new__(AsekoDeviceServer)
    reader = asyncio.StreamReader()

    frame, offset, frame_type = await server._sync_frame(reader, shifted_binary)

    assert frame_type == FrameType.BINARY
    assert offset == 8
    # After rewind, alignment markers must be at the correct positions
    assert frame[5] == 0x01
    assert frame[45] == 0x03
    assert frame[85] == 0x02
    # Serial number must be consistent across all three sub-frames
    assert frame[0:4] == frame[40:44] == frame[80:84]


@pytest.mark.asyncio
async def test_create_restarts_a_server_stopped_but_still_registered(
    monkeypatch,
) -> None:
    """R1: stop() without remove() must not hand a dead server to the next setup."""
    starts = []

    async def dummy_start_server(handler, host, port) -> DummyServer:
        starts.append(port)
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)
    await AsekoDeviceServer.remove(host="127.0.0.1", port=12350)

    first = await AsekoDeviceServer.create(host="127.0.0.1", port=12350)
    await first.stop()
    assert not first.running

    again = await AsekoDeviceServer.create(host="127.0.0.1", port=12350)
    assert again is first
    assert again.running
    assert starts == [12350, 12350]

    await AsekoDeviceServer.remove(host="127.0.0.1", port=12350)
    assert AsekoDeviceServer.get("127.0.0.1", 12350) is None


@pytest.mark.asyncio
async def test_remove_leaves_other_servers_running(monkeypatch) -> None:
    """R1: stopping one entry's server keeps the others listening."""

    async def dummy_start_server(handler, host, port) -> DummyServer:
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", dummy_start_server)
    one = await AsekoDeviceServer.create(host="127.0.0.1", port=12351)
    two = await AsekoDeviceServer.create(host="127.0.0.1", port=12352)

    await AsekoDeviceServer.remove(host="127.0.0.1", port=12351)
    assert not one.running
    assert two.running
    await AsekoDeviceServer.remove(host="127.0.0.1", port=12352)


@pytest.mark.asyncio
async def test_rejected_v8_frame_still_reaches_the_frame_log() -> None:
    """R5: the raw sink sees a v8 frame before the decoder can reject it."""
    logged: list[bytes] = []
    warnings: list[tuple[int, str]] = []

    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12353,
        on_data=None,
        v8_raw_sink=logged.append,
        frame_warning_sink=lambda serial, reason: warnings.append((serial, reason)),
    )
    reader = asyncio.StreamReader()
    writer = DummyWriter("127.0.0.1", 12353)
    reader.feed_data(V8_FULL_FRAME)  # header without the four numbers: rejected
    reader.feed_eof()
    await server._handle_client(reader, writer)

    assert logged == [V8_FULL_FRAME]
    assert len(warnings) == 1
    assert warnings[0][0] == 12345678
    assert warnings[0][1].startswith("v8 frame rejected:")


@pytest.mark.asyncio
async def test_bytes_that_never_align_are_kept_with_the_reason() -> None:
    """R5: a frame sync failure no longer drops the bytes silently."""
    rejected: list[tuple[bytes, str]] = []
    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12354,
        on_data=None,
        rejected_sink=lambda data, reason: rejected.append((data, reason)),
    )
    garbage = bytes(range(120))  # no segment markers anywhere: cannot be aligned
    reader = asyncio.StreamReader()
    writer = DummyWriter("127.0.0.1", 12354)
    reader.feed_data(garbage)
    reader.feed_eof()
    await server._handle_client(reader, writer)

    assert len(rejected) == 1
    assert rejected[0][0] == garbage
    assert rejected[0][1].startswith("frame sync failed:")


@pytest.mark.asyncio
async def test_a_restarted_server_uses_the_new_callbacks(monkeypatch) -> None:
    """R1: frames arriving right at the restart go to the new setup's on_data."""
    old_calls: list = []
    new_calls: list = []

    async def quiet_start(handler, host, port) -> DummyServer:
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", quiet_start)
    await AsekoDeviceServer.remove(host="127.0.0.1", port=12355)
    first = await AsekoDeviceServer.create(
        host="127.0.0.1", port=12355, on_data=old_calls.append
    )
    await first.stop()

    async def start_with_a_frame(handler, host, port) -> DummyServer:
        reader = asyncio.StreamReader()
        reader.feed_data(VALID_FRAME)
        reader.feed_eof()
        await handler(reader, DummyWriter(host, port))
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", start_with_a_frame)
    await AsekoDeviceServer.create(
        host="127.0.0.1", port=12355, on_data=new_calls.append
    )
    assert old_calls == []
    assert len(new_calls) == 1
    await AsekoDeviceServer.remove(host="127.0.0.1", port=12355)


@pytest.mark.asyncio
async def test_unreadable_v8_value_is_reported_and_the_frame_still_delivered() -> None:
    """A corrupt token costs one value, not the frame: counted, logged, decoded."""
    received: list[AsekoDevice] = []
    warnings: list[tuple[int, str]] = []

    async def on_data(device: AsekoDevice) -> None:
        received.append(device)

    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12356,
        on_data=on_data,
        frame_warning_sink=lambda serial, reason: warnings.append((serial, reason)),
    )
    reader = asyncio.StreamReader()
    reader.feed_data(_V8_REAL_FRAME.replace(b"ains: 708 ", b"ains: 7x8 "))
    reader.feed_eof()
    await server._handle_client(reader, DummyWriter("127.0.0.1", 12356))

    assert len(received) == 1
    assert received[0].ph is None
    assert warnings == [(123456789, "v8 value unreadable: ains[0] is not a number")]


@pytest.mark.asyncio
async def test_a_short_v8_frame_does_not_swallow_the_next_one() -> None:
    """Audit N1: a v8 frame ending inside the first 120 bytes stops at its newline."""
    received: list[AsekoDevice] = []

    async def on_data(device: AsekoDevice) -> None:
        received.append(device)

    server = AsekoDeviceServer(host="127.0.0.1", port=12357, on_data=on_data)
    short = b"{v1 111 804 0 27 ins: 200 ains: 700 outs: 0 areqs: 70}\n"
    assert len(short) < 120
    reader = asyncio.StreamReader()
    reader.feed_data(short + _V8_REAL_FRAME + short)
    reader.feed_eof()
    await server._handle_client(reader, DummyWriter("127.0.0.1", 12357))

    assert [(d.serial_number, d.ph) for d in received] == [
        (111, 7.0),
        (123456789, 7.08),
        (111, 7.0),
    ]


@pytest.mark.asyncio
async def test_two_long_v8_frames_in_one_read_stay_apart() -> None:
    received: list[AsekoDevice] = []

    async def on_data(device: AsekoDevice) -> None:
        received.append(device)

    server = AsekoDeviceServer(host="127.0.0.1", port=12358, on_data=on_data)
    reader = asyncio.StreamReader()
    reader.feed_data(_V8_REAL_FRAME + _V8_REAL_FRAME)
    reader.feed_eof()
    await server._handle_client(reader, DummyWriter("127.0.0.1", 12358))

    assert [d.serial_number for d in received] == [123456789, 123456789]


@pytest.mark.asyncio
async def test_a_whole_short_v8_frame_is_handled_without_waiting_for_more() -> None:
    """A complete short frame is decoded at once, while the connection stays open."""
    received: list[AsekoDevice] = []

    async def on_data(device: AsekoDevice) -> None:
        received.append(device)

    server = AsekoDeviceServer(host="127.0.0.1", port=12359, on_data=on_data)
    reader = asyncio.StreamReader()
    reader.feed_data(b"{v1 111 804 0 27 ins: 200 ains: 700 outs: 0 areqs: 70}\n")
    handler = asyncio.ensure_future(
        server._handle_client(reader, DummyWriter("127.0.0.1", 12359))
    )
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0)

    assert [(d.serial_number, d.ph) for d in received] == [(111, 7.0)]
    reader.feed_eof()
    await asyncio.wait_for(handler, 5)


def test_the_warning_register_stays_bounded() -> None:
    """Whatever a unit sends, the reasons kept per unit are capped."""

    coordinator = _coordinator()
    for i in range(1000):
        coordinator.store_frame_warning(1, f"reason {i}")

    reasons = coordinator.get_frame_warnings(1)
    assert len(reasons) == MAX_WARNING_REASONS
    assert reasons[OTHER_WARNING_REASONS]["count"] == 1000 - (MAX_WARNING_REASONS - 1)


# ---------------------------------------------------------------------------
# start / stop, the server registry and callbacks
# ---------------------------------------------------------------------------


async def _serve(server: AsekoDeviceServer, data: bytes, *, eof: bool = True) -> None:
    """Run one client connection that sends ``data``."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    if eof:
        reader.feed_eof()
    await server._handle_client(reader, DummyWriter("127.0.0.1", server.port))


def _raises(*_args: object) -> None:
    msg = "sink failed"
    raise RuntimeError(msg)


@pytest.mark.asyncio
async def test_a_port_that_cannot_be_bound_raises_a_connection_error(
    monkeypatch,
) -> None:
    async def refuse(handler, host, port) -> DummyServer:
        msg = "address in use"
        raise OSError(msg)

    monkeypatch.setattr(asyncio, "start_server", refuse)
    server = AsekoDeviceServer(host="127.0.0.1", port=12370)
    with pytest.raises(ServerConnectionError, match="address in use"):
        await server.start()
    assert not server.running


@pytest.mark.asyncio
async def test_stop_closes_every_client_even_one_that_is_gone() -> None:
    class GoneWriter(DummyWriter):
        def close(self) -> None:
            msg = "already closed"
            raise OSError(msg)

    server = AsekoDeviceServer(host="127.0.0.1", port=12371)
    server._server = DummyServer()
    alive = DummyWriter("127.0.0.1", 1)
    server._clients = {GoneWriter("127.0.0.1", 2), alive}

    await server.stop()

    assert alive.closed
    assert server._clients == set()
    assert not server.running


@pytest.mark.asyncio
async def test_remove_all_stops_and_forgets_every_server(monkeypatch) -> None:
    async def quiet_start(handler, host, port) -> DummyServer:
        return DummyServer()

    monkeypatch.setattr(asyncio, "start_server", quiet_start)
    one = await AsekoDeviceServer.create(host="127.0.0.1", port=12372)
    two = await AsekoDeviceServer.create(host="127.0.0.1", port=12373)

    await AsekoDeviceServer.remove_all()

    assert not one.running
    assert not two.running
    assert AsekoDeviceServer.get("127.0.0.1", 12372) is None
    assert AsekoDeviceServer.get("127.0.0.1", 12373) is None


def test_replacing_sinks_keeps_the_ones_not_given() -> None:
    old_raw, new_raw = [], []
    server = AsekoDeviceServer(host="127.0.0.1", port=12374, raw_sink=old_raw.append)

    server.replace_sinks(
        v8_raw_sink=new_raw.append,
        frame_warning_sink=print,
        rejected_sink=print,
    )
    assert server._raw_sink == old_raw.append
    assert server._v8_raw_sink == new_raw.append

    server.replace_sinks(raw_sink=new_raw.append)
    assert server._raw_sink == new_raw.append
    assert server._frame_warning_sink is print
    assert server._rejected_sink is print


@pytest.mark.asyncio
async def test_forward_callbacks_get_the_frames_until_cleared() -> None:
    v7_frames: list[bytes] = []
    v8_frames: list[bytes] = []
    server = AsekoDeviceServer(host="127.0.0.1", port=12375)
    server.set_forward_callback(v7_frames.append)
    server.set_forward_v8_callback(v8_frames.append)

    await _serve(server, VALID_FRAME)
    await _serve(server, _V8_REAL_FRAME)
    assert v7_frames == [VALID_FRAME]
    assert v8_frames == [_V8_REAL_FRAME]

    server.set_forward_callback(None)
    server.set_forward_v8_callback(None)
    await _serve(server, VALID_FRAME)
    await _serve(server, _V8_REAL_FRAME)
    assert v7_frames == [VALID_FRAME]
    assert v8_frames == [_V8_REAL_FRAME]


# ---------------------------------------------------------------------------
# a callback that raises costs nothing but its own call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failing_v7_callbacks_do_not_stop_the_next_frame() -> None:
    delivered: list[int | None] = []

    def on_data(device: AsekoDevice) -> None:
        delivered.append(device.serial_number)
        _raises()

    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12376,
        on_data=on_data,
        raw_sink=_raises,
        frame_warning_sink=_raises,
    )
    server.set_forward_callback(_raises)

    await _serve(server, bytes(CORRUPT_FRAME) + VALID_FRAME2)

    assert delivered == [110200612, 110200613]


@pytest.mark.asyncio
async def test_failing_v8_callbacks_do_not_stop_the_next_frame() -> None:
    delivered: list[int | None] = []

    def on_data(device: AsekoDevice) -> None:
        delivered.append(device.serial_number)
        _raises()

    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12377,
        on_data=on_data,
        v8_raw_sink=_raises,
        frame_warning_sink=_raises,
    )
    server.set_forward_v8_callback(_raises)
    unreadable = _V8_REAL_FRAME.replace(b"ains: 708 ", b"ains: 7x8 ")

    await _serve(server, unreadable + _V8_REAL_FRAME)

    assert delivered == [123456789, 123456789]


@pytest.mark.asyncio
async def test_failing_sinks_for_rejected_bytes_are_contained() -> None:
    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12378,
        frame_warning_sink=_raises,
        rejected_sink=_raises,
    )
    await _serve(server, V8_FULL_FRAME)  # rejected v8 header
    await _serve(server, bytes(range(120)))  # never aligns


# ---------------------------------------------------------------------------
# what a frame can look like
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_implausible_ph_target_is_reported_once_as_a_warning(caplog) -> None:
    warnings: list[tuple[int, str]] = []
    frame = bytearray(VALID_FRAME)
    frame[52] = 200  # required pH 20.0
    frame[14:16] = b"\xff\xff"  # pH probe absent: not checked
    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12379,
        frame_warning_sink=lambda serial, reason: warnings.append((serial, reason)),
    )

    with caplog.at_level(logging.DEBUG, logger=server_module.__name__):
        await _serve(server, bytes(frame) * 2)

    reason = "required pH 20.0 outside 6-10"
    assert warnings == [(110200612, reason)] * 2
    logged = [r for r in caplog.records if reason in r.getMessage()]
    assert [r.levelno for r in logged] == [logging.WARNING, logging.DEBUG]


@pytest.mark.asyncio
async def test_frame_problems_without_a_serial_number_are_not_reported() -> None:
    warnings: list[tuple[int, str]] = []
    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12380,
        frame_warning_sink=lambda serial, reason: warnings.append((serial, reason)),
    )
    await server._report_frame_problems(
        AsekoDevice(frame_problems=("ains[0] is not a number",)), "addr"
    )
    assert warnings == []


@pytest.mark.asyncio
async def test_a_rejected_v8_frame_is_counted_only_under_a_readable_serial() -> None:
    warnings: list[tuple[int, str]] = []
    silent = AsekoDeviceServer(host="127.0.0.1", port=12381)
    await silent._report_rejected_v8(V8_FULL_FRAME, "no sink")  # nowhere to count

    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12381,
        frame_warning_sink=lambda serial, reason: warnings.append((serial, reason)),
    )
    await server._report_rejected_v8(b"{v1 notanumber}\n", "bad header")
    await server._report_rejected_v8(b"{v1}\n", "bad header")
    assert warnings == []


@pytest.mark.asyncio
async def test_a_v8_decoder_crash_closes_the_connection(monkeypatch) -> None:
    delivered: list[AsekoDevice] = []
    logged: list[bytes] = []

    def crash(raw: bytes, protocol: object = None) -> AsekoDevice:
        msg = "decoder bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(server_module, "decode", crash)
    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12382,
        on_data=delivered.append,
        v8_raw_sink=logged.append,
    )
    await _serve(server, _V8_REAL_FRAME + _V8_REAL_FRAME)

    assert delivered == []
    assert logged == [_V8_REAL_FRAME]  # the second frame is never read


@pytest.mark.parametrize("error", [ValueError, RuntimeError])
@pytest.mark.asyncio
async def test_a_v7_frame_the_decoder_refuses_closes_the_connection(
    monkeypatch, error
) -> None:
    delivered: list[AsekoDevice] = []
    logged: list[bytes] = []

    def refuse(raw: bytes, protocol: object = None) -> AsekoDevice:
        msg = "refused"
        raise error(msg)

    monkeypatch.setattr(server_module, "decode", refuse)
    server = AsekoDeviceServer(
        host="127.0.0.1", port=12383, on_data=delivered.append, raw_sink=logged.append
    )
    await _serve(server, VALID_FRAME + VALID_FRAME2)

    assert delivered == []
    assert logged == [VALID_FRAME]


@pytest.mark.asyncio
async def test_two_short_v8_frames_in_one_read_are_both_delivered() -> None:
    """The second frame is whole in the carried bytes and is read from there."""
    received: list[AsekoDevice] = []
    server = AsekoDeviceServer(host="127.0.0.1", port=12384, on_data=received.append)
    short = b"{v1 111 804 0 27 ins: 200 ains: 700 outs: 0 areqs: 70}\n"
    assert len(short) * 2 < 120

    await _serve(server, short * 2)

    assert [d.serial_number for d in received] == [111, 111]


@pytest.mark.asyncio
async def test_a_v8_frame_cut_off_before_its_newline_is_still_logged() -> None:
    logged: list[bytes] = []
    server = AsekoDeviceServer(host="127.0.0.1", port=12385, v8_raw_sink=logged.append)
    cut = V8_INITIAL + b" ins: 0000 outs: 0000"  # the unit hangs up mid-frame

    await _serve(server, cut)

    assert logged == [cut]


@pytest.mark.asyncio
async def test_a_v8_frame_after_foreign_bytes_is_found_with_a_warning(caplog) -> None:
    received: list[AsekoDevice] = []
    server = AsekoDeviceServer(host="127.0.0.1", port=12386, on_data=received.append)

    with caplog.at_level(logging.WARNING, logger=server_module.__name__):
        await _serve(server, b"xyz" + _V8_REAL_FRAME)

    assert [d.serial_number for d in received] == [123456789]
    assert "v8 frame shifted by 3 bytes" in caplog.text


@pytest.mark.asyncio
async def test_a_fragment_before_hanging_up_goes_to_the_raw_sink() -> None:
    logged: list[bytes] = []
    server = AsekoDeviceServer(host="127.0.0.1", port=12387, raw_sink=logged.append)

    await _serve(server, VALID_FRAME[:50])

    assert logged == [VALID_FRAME[:50]]


@pytest.mark.asyncio
async def test_a_quiet_unit_is_disconnected_after_the_read_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(server_module, "READ_TIMEOUT", 0.01)
    server = AsekoDeviceServer(host="127.0.0.1", port=12388)
    reader = asyncio.StreamReader()  # sends nothing, never hangs up
    writer = DummyWriter("127.0.0.1", 12388)

    await asyncio.wait_for(server._handle_client(reader, writer), 5)

    assert writer.closed
    assert server._clients == set()


@pytest.mark.asyncio
async def test_a_connection_reset_by_the_unit_is_closed_cleanly() -> None:
    server = AsekoDeviceServer(host="127.0.0.1", port=12389)
    reader = asyncio.StreamReader()
    reader.set_exception(ConnectionResetError())
    writer = DummyWriter("127.0.0.1", 12389)

    await server._handle_client(reader, writer)

    assert writer.closed
    assert server._clients == set()
