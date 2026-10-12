"""The frame log: a ring buffer of frames and markers with a hard compressed cap."""

from __future__ import annotations

import asyncio
import base64
import json
import random
import zlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.aseko_local import _mark_dump_message
from custom_components.aseko_local.coordinator import RecordingOffError
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.recording.frame_log import (
    KIND_MARK,
    KIND_V7,
    KIND_V8,
    FrameLog,
    decode_lines,
)
from custom_components.aseko_local.server import AsekoDeviceServer

from .test_decode_v8 import REFERENCE_FRAME
from .test_entity_growth import _coordinator
from .test_server import V8_FULL_FRAME, DummyWriter

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _v8_frames(count: int, seed: int = 1) -> Iterator[tuple[datetime, bytes]]:
    """Frames of one v8 unit every ten seconds, with the jitter a real one has."""
    rng = random.Random(seed)
    parts = REFERENCE_FRAME.decode().strip().split()
    ins, ains = parts.index("ins:"), parts.index("ains:")
    for i in range(count):
        received = T0 + timedelta(seconds=10 * i + rng.random() * 0.3)
        frame = list(parts)
        frame[ins + 17] = str(received.hour)
        frame[ins + 18] = str(received.minute)
        frame[ains + 1] = frame[ains + 2] = str(708 + rng.choice((-1, 0, 0, 1)))
        frame[ains + 7] = frame[ains + 8] = str(779 + rng.choice((-2, -1, 0, 1, 2)))
        yield received, " ".join(frame).encode()


def test_records_come_back_in_order_with_absolute_times() -> None:
    log = FrameLog()
    frames = list(_v8_frames(100))
    for received, raw in frames[:50]:
        log.append_frame(received, KIND_V8, raw)
    number = log.append_marker(frames[49][0] + timedelta(seconds=3), "heating ON")
    for received, raw in frames[50:]:
        log.append_frame(received, KIND_V8, raw)
    log.append_frame(frames[-1][0], KIND_V7, bytes(range(120)))

    records = log.records()
    assert number == 1
    assert len(records) == 102
    assert records[50] == {
        "k": KIND_MARK,
        "n": 1,
        "note": "heating ON",
        "t": records[50]["t"],
    }
    assert (
        abs(
            datetime.fromisoformat(records[50]["t"]).timestamp()
            - (frames[49][0].timestamp() + 3)
        )
        < 0.06
    )
    assert records[0]["d"] == frames[0][1].decode()
    assert records[-1] == {
        "k": KIND_V7,
        "d": bytes(range(120)).hex(),
        "t": records[-1]["t"],
    }
    times = [datetime.fromisoformat(r["t"]) for r in records]
    assert times == sorted(times)


def test_the_cap_is_never_exceeded_and_old_chunks_go_first() -> None:
    log = FrameLog(max_bytes=32 * 1024, chunk_bytes=4 * 1024)
    for received, raw in _v8_frames(20000):
        log.append_frame(received, KIND_V8, raw)
        assert log.size() <= log.max_bytes
    records = log.records()
    assert log.export()["dropped_chunks"] > 0
    # the newest frame is always kept, the oldest are gone
    assert records[-1]["t"].startswith(
        (T0 + timedelta(seconds=10 * 19999)).isoformat()[:16]
    )
    assert datetime.fromisoformat(records[0]["t"]) > T0 + timedelta(days=1)


def test_rounded_time_deltas_do_not_drift() -> None:
    log = FrameLog()
    frames = list(_v8_frames(5000))
    for received, raw in frames:
        log.append_frame(received, KIND_V8, raw)
    last = datetime.fromisoformat(log.records()[-1]["t"])
    assert abs(last.timestamp() - frames[-1][0].timestamp()) < 0.06


def test_every_chunk_starts_with_an_absolute_time() -> None:
    """Dropping old chunks must never leave a stream that starts with a delta."""
    log = FrameLog(max_bytes=32 * 1024, chunk_bytes=4 * 1024)
    for received, raw in _v8_frames(5000):
        log.append_frame(received, KIND_V8, raw)
    for chunk in log._chunks:
        first = zlib.decompress(chunk).splitlines()[0]
        assert first.startswith(b'{"t":')


def test_huge_frames_cannot_break_the_ceiling() -> None:
    log = FrameLog(max_bytes=8 * 1024, chunk_bytes=2 * 1024)
    rng = random.Random(7)
    for i in range(300):
        noise = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 3000)))
        log.append_frame(T0 + timedelta(seconds=i), KIND_V7, noise)
        assert log.size() <= log.max_bytes


def test_store_roundtrip_keeps_frames_markers_and_numbering() -> None:
    log = FrameLog(max_bytes=64 * 1024, chunk_bytes=4 * 1024)
    frames = list(_v8_frames(3000))
    for received, raw in frames[:2000]:
        log.append_frame(received, KIND_V8, raw)
    log.append_marker(frames[1999][0], "before restart")

    restored = FrameLog(max_bytes=64 * 1024, chunk_bytes=4 * 1024)
    restored.load_store(log.to_store())
    assert restored.records() == log.records()

    for received, raw in frames[2000:]:
        restored.append_frame(received, KIND_V8, raw)
    assert restored.append_marker(frames[-1][0]) == 2
    assert restored.size() <= restored.max_bytes
    times = [datetime.fromisoformat(r["t"]) for r in restored.records()]
    assert times == sorted(times)


def test_unreadable_store_starts_an_empty_log() -> None:
    log = FrameLog()
    log.load_store({"chunks": ["not base64 zlib"], "open": "???"})
    assert log.records() == []
    log.append_frame(T0, KIND_V7, b"\x00" * 120)
    assert len(log.records()) == 1


def test_export_blob_decodes_to_the_same_records() -> None:
    log = FrameLog(max_bytes=32 * 1024, chunk_bytes=4 * 1024)
    for received, raw in _v8_frames(3000):
        log.append_frame(received, KIND_V8, raw)
    log.append_marker(T0 + timedelta(hours=9), "display photo 1")

    exported = log.export(recent=5)
    blob = zlib.decompress(base64.b64decode(exported["blob"]))
    assert list(decode_lines(blob.splitlines(keepends=True))) == log.records()
    assert exported["records"] == len(log.records())
    assert exported["markers"][0]["note"] == "display photo 1"
    assert len(exported["recent"]) == 5
    assert exported["size_bytes"] <= exported["cap_bytes"]


def test_chunk_size_must_leave_room_under_the_cap() -> None:
    with pytest.raises(ValueError, match="at most half"):
        FrameLog(max_bytes=10_000, chunk_bytes=6_000)


def test_coordinator_logs_every_frame_and_numbers_markers() -> None:
    coordinator = _coordinator()
    coordinator.set_recording(enabled=True)
    coordinator.store_v8_frame(REFERENCE_FRAME)
    coordinator.store_raw_frame(bytes(120))
    coordinator.store_raw_frame(bytes(40))  # partial frame
    marker = coordinator.mark_dump("photo of the display")

    records = coordinator.frame_log.records()
    assert [r["k"] for r in records] == ["v8", "v7", "partial", "mark"]
    assert marker["marker"] == 1
    assert records[-1]["note"] == "photo of the display"
    assert marker["time"].tzinfo is not None
    # the v8 reference unit and the all-zero v7 serial both reported just now
    assert set(marker["seconds_since_last_frame"]) == {123456789, 0}
    assert all(0 <= age < 5 for age in marker["seconds_since_last_frame"].values())
    assert records[-1]["since"] == {
        str(serial): age for serial, age in marker["seconds_since_last_frame"].items()
    }


@pytest.mark.asyncio
async def test_waiting_for_the_next_frame() -> None:

    coordinator = _coordinator()
    coordinator.hass.loop = asyncio.get_running_loop()

    waiting = asyncio.create_task(coordinator.async_wait_for_frame(5))
    await asyncio.sleep(0)
    coordinator.store_v8_frame(REFERENCE_FRAME)  # logged, not decoded yet
    await asyncio.sleep(0)
    assert not waiting.done()
    coordinator.devices_update_callback(decode(REFERENCE_FRAME))
    assert await waiting is True

    assert await coordinator.async_wait_for_frame(0.01) is False
    assert coordinator._frame_waiters == []


def test_mark_dump_notification_says_whether_the_marker_is_written() -> None:
    written = {
        "marker": 3,
        "time": "2026-09-13T12:01:05+02:00",
        "seconds_since_last_frame": {110000001: 0.2},
        "waited_for_frame": True,
        "seconds_after_tap": 7.1,
    }
    text = _mark_dump_message([written], wait=True, label=" (heating ON)")
    assert "Marker **3** (heating ON) written at 12:01:05" in text
    assert "7.1 s after the tap" in text
    assert "change the unit again" in text

    timed_out = {**written, "waited_for_frame": False}
    assert "No frame within 60 s" in _mark_dump_message([timed_out], "", wait=True)

    immediate = {**written, "waited_for_frame": None}
    assert "last frame 0.2 s before" in _mark_dump_message([immediate], "", wait=False)


def test_cases_list_survives_restart_and_tracks_downloads() -> None:
    log = FrameLog(max_bytes=32 * 1024, chunk_bytes=4 * 1024)
    frames = list(_v8_frames(200))
    for received, raw in frames[:100]:
        log.append_frame(received, KIND_V8, raw)
    log.append_marker(frames[99][0], "Heating control ON", extra={"photo": "a.jpg"})
    log.append_marker(frames[99][0] + timedelta(seconds=5), "Winter mode ON")

    assert [m["note"] for m in log.markers()] == [
        "Heating control ON",
        "Winter mode ON",
    ]
    assert log.not_downloaded() == 2
    assert all(m["frames"] and not m["downloaded"] for m in log.markers())

    log.mark_exported(1)
    restored = FrameLog(max_bytes=32 * 1024, chunk_bytes=4 * 1024)
    restored.load_store(log.to_store())
    assert [m["downloaded"] for m in restored.markers()] == [True, False]
    assert restored.markers()[0]["photo"] == "a.jpg"
    assert restored.not_downloaded() == 1

    # the frames of old cases age out, the cases stay listed
    for received, raw in _v8_frames(20000, seed=2):
        restored.append_frame(received + timedelta(days=3), KIND_V8, raw)
    assert len(restored.markers()) == 2
    assert not restored.markers()[0]["frames"]

    restored.forget_markers()
    assert restored.markers() == []


def test_an_older_store_gets_its_cases_rebuilt_from_the_frames() -> None:
    log = FrameLog()
    frames = list(_v8_frames(20))
    for received, raw in frames:
        log.append_frame(received, KIND_V8, raw)
    log.append_marker(frames[-1][0], "heating on")
    old_store = log.to_store()
    del old_store["markers"], old_store["exported_through"]

    restored = FrameLog()
    restored.load_store(old_store)
    assert [m["note"] for m in restored.markers()] == ["heating on"]
    assert restored.not_downloaded() == 1


def test_open_chunk_is_sealed_by_uncompressed_size_too() -> None:
    """R10: well-compressing frames must not pile up uncompressed in memory."""
    log = FrameLog()
    frames = list(_v8_frames(43_200))  # five days, one frame every ten seconds
    for received, raw in frames:
        log.append_frame(received, KIND_V8, raw)
    held = sum(len(line) for line in log._current_lines)
    assert held < log.chunk_raw_bytes + 2_000
    assert log.size() <= log.max_bytes


def test_snapshot_reads_the_same_as_the_log_and_stays_put() -> None:
    """R10: the export works on a copy; frames arriving afterwards do not change it."""
    log = FrameLog()
    frames = list(_v8_frames(3_000))
    for received, raw in frames[:2_000]:
        log.append_frame(received, KIND_V8, raw)
    snapshot = log.snapshot()
    expected = log.records()
    for received, raw in frames[2_000:]:
        log.append_frame(received, KIND_V8, raw)
    assert snapshot.records() == expected
    assert snapshot.export()["records"] == len(expected)


def test_oldest_frame_time_survives_dropping_and_a_restart() -> None:
    """The age of the oldest frame comes from a side list, not a decompression."""
    log = FrameLog(max_bytes=64 * 1024)
    for received, raw in _v8_frames(20_000):
        log.append_frame(received, KIND_V8, raw)
    first = datetime.fromisoformat(log.records()[0]["t"])
    assert log._oldest_time() == first

    restored = FrameLog(max_bytes=64 * 1024)
    restored.load_store(log.to_store())
    assert restored._oldest_time() == first


@pytest.mark.parametrize(
    "damage",
    [
        {"next_marker": "broken"},
        {"exported_through": None},
        {"markers": "not a list"},
        {"chunks": ["!!not base64!!"]},
        {"dropped_chunks": [1]},
    ],
)
def test_a_damaged_store_leaves_the_log_empty_instead_of_raising(damage) -> None:
    """A broken diagnostic history must never stop the integration from starting."""
    log = FrameLog()
    for received, raw in _v8_frames(50):
        log.append_frame(received, KIND_V8, raw)
    log.append_marker(T0, "a case")
    stored = {**log.to_store(), **damage}

    restored = FrameLog()
    restored.load_store(stored)  # must not raise
    assert restored.records() == []
    assert restored.markers() == []


@pytest.mark.asyncio
async def test_a_fragment_or_another_unit_does_not_end_the_wait() -> None:
    """R8: only a whole frame from the unit being waited for writes the marker."""

    coordinator = _coordinator()
    coordinator.hass.loop = asyncio.get_running_loop()

    waiting = asyncio.create_task(
        coordinator.async_wait_for_frame(5, serial_number=123456789)
    )
    await asyncio.sleep(0)
    coordinator.store_raw_frame(b"\x00\x00\x04\xd2")  # four bytes, no measurements
    other = bytearray(120)
    other[0:4] = (1234).to_bytes(4, "big")
    coordinator.store_raw_frame(bytes(other))  # a whole frame, another unit
    coordinator.devices_update_callback(decode(bytes(other)))
    await asyncio.sleep(0)
    assert not waiting.done()

    coordinator.store_v8_frame(REFERENCE_FRAME)  # serial 123456789
    coordinator.devices_update_callback(decode(REFERENCE_FRAME))
    assert await waiting is True
    assert coordinator._frame_waiters == []


def test_rejected_bytes_are_logged_with_their_reason_and_counted() -> None:
    coordinator = _coordinator()
    coordinator.set_recording(enabled=True)
    coordinator.store_rejected_frame(bytes(range(120)), "frame sync failed: IndexError")
    coordinator.store_rejected_frame(bytes(range(120)), "frame sync failed: IndexError")

    records = coordinator.frame_log.records()
    assert [r["k"] for r in records] == ["rejected", "rejected"]
    assert records[0]["why"] == "frame sync failed: IndexError"
    assert records[0]["d"] == bytes(range(120)).hex()
    assert (
        coordinator.get_rejected_frames()["frame sync failed: IndexError"]["count"] == 2
    )


# -- recording on / off ------------------------------------------------------


def test_recording_is_off_until_turned_on_and_nothing_is_logged() -> None:

    coordinator = _coordinator()
    assert coordinator.frame_log.enabled is False
    coordinator.store_v8_frame(REFERENCE_FRAME)
    coordinator.store_rejected_frame(bytes(range(120)), "frame sync failed")
    assert coordinator.frame_log.records() == []
    # the frame age and the rejection count still work while off
    assert 123456789 in coordinator.seconds_since_last_frame(dt_util.utcnow())
    assert coordinator.get_rejected_frames()["frame sync failed"]["count"] == 1
    with pytest.raises(RecordingOffError):
        coordinator.mark_dump("no frames around it")

    coordinator.set_recording(enabled=True)
    coordinator.store_v8_frame(REFERENCE_FRAME)
    coordinator.mark_dump("now")
    assert [r["k"] for r in coordinator.frame_log.records()] == ["v8", "mark"]

    coordinator.set_recording(enabled=False)  # what was recorded stays
    coordinator.store_v8_frame(REFERENCE_FRAME)
    assert [r["k"] for r in coordinator.frame_log.records()] == ["v8", "mark"]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, False),  # no log before: off
        ({"enabled": False}, False),  # turned off: stays off
        ({"enabled": True}, True),  # turned on: stays on
        ({}, True),  # a log from before the switch was recording: stays on
    ],
)
def test_recording_state_survives_a_restart_and_an_update(stored, expected) -> None:
    log = FrameLog()
    if stored is not None:
        log.load_store({**FrameLog().to_store(), **stored} if stored else _legacy())
    assert log.enabled is expected


def _legacy() -> dict:
    """Return a store written before recording could be switched off."""
    data = FrameLog().to_store()
    del data["enabled"]
    return data


def test_clear_drops_frames_and_cases_but_keeps_counting() -> None:
    log = FrameLog()
    log.enabled = True
    for received, raw in _v8_frames(20):
        log.append_frame(received, KIND_V8, raw)
    log.append_marker(T0, "one")
    log.append_marker(T0, "two")

    log.clear()

    assert log.records() == []
    assert log.markers() == []
    assert log.not_downloaded() == 0
    assert log.enabled is True
    assert log.append_marker(T0, "three") == 3


@pytest.mark.asyncio
async def test_a_frame_the_decoder_rejects_does_not_end_the_wait() -> None:
    """Audit N2: raw bytes are logged first, but only a decoded frame answers a wait."""

    coordinator = _coordinator()
    coordinator.set_recording(enabled=True)
    coordinator.hass.loop = asyncio.get_running_loop()
    server = AsekoDeviceServer(
        host="127.0.0.1",
        port=12360,
        on_data=coordinator.devices_update_callback,
        v8_raw_sink=coordinator.store_v8_frame,
    )

    waiting = asyncio.create_task(coordinator.async_wait_for_frame(5))
    await asyncio.sleep(0)
    reader = asyncio.StreamReader()
    reader.feed_data(V8_FULL_FRAME)  # readable serial, header the decoder rejects
    reader.feed_eof()
    await server._handle_client(reader, DummyWriter("127.0.0.1", 12360))
    await asyncio.sleep(0)

    assert [r["k"] for r in coordinator.frame_log.records()] == ["v8"]
    assert not waiting.done()
    waiting.cancel()


@pytest.mark.parametrize(
    "marker",
    [
        {"n": "bad", "t": T0.isoformat(), "k": "mark"},
        {"n": 1, "t": "broken", "k": "mark"},
        {"n": True, "t": T0.isoformat(), "k": "mark"},
        {"t": T0.isoformat(), "k": "mark"},
        "not a marker",
    ],
)
def test_a_damaged_marker_is_dropped_and_the_list_still_works(marker) -> None:
    """Audit N4: one bad case must not break status or export."""
    log = FrameLog()
    for received, raw in _v8_frames(5):
        log.append_frame(received, KIND_V8, raw)
    good = log.append_marker(T0, "good")
    stored = log.to_store()
    stored["markers"] = [marker, *stored["markers"]]

    restored = FrameLog()
    restored.load_store(stored)

    assert [m["n"] for m in restored.markers()] == [good]
    assert restored.not_downloaded() == 1


def test_an_open_record_without_a_time_leaves_the_log_empty() -> None:
    """Audit N4: the replay runs only after every open record has its time."""
    line = json.dumps({"dt": 1.0, "k": "v8", "d": "{v1 1 804 0 27}"}).encode() + b"\n"
    stored = {
        **FrameLog().to_store(),
        "open": base64.b64encode(zlib.compress(line)).decode(),
    }
    restored = FrameLog()
    restored.load_store(stored)  # must not raise
    assert restored.records() == []


def test_records_and_export_come_from_one_read() -> None:
    """Audit O1: the export download reads the snapshot once for both."""
    log = FrameLog(max_bytes=4096, chunk_bytes=1024, chunk_raw_bytes=512)
    for i, (received, raw) in enumerate(_v8_frames(120)):
        log.append_frame(received, KIND_V8, raw)
        if i % 40 == 0:
            log.append_marker(received, note=f"case {i}")
    snapshot = log.snapshot()

    reads = 0
    lines = type(snapshot).lines

    def counting_lines(self) -> Iterator[bytes]:
        nonlocal reads
        reads += 1
        return lines(self)

    type(snapshot).lines = counting_lines
    try:
        records, exported = snapshot.records_and_export()
    finally:
        type(snapshot).lines = lines

    assert reads == 1
    assert records == snapshot.records()
    assert exported == snapshot.export()
    blob = zlib.decompress(base64.b64decode(exported["blob"]))
    assert list(decode_lines(blob.splitlines(keepends=True))) == records
