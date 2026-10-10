"""A ring buffer of raw frames and user markers, capped in compressed bytes.

While recording is on (the test cases card turns it on), every frame the
server receives (v7 binary, v8 text, partial, rejected) is appended as one
JSON line with the Home Assistant receive time.  A marker from ``mark_dump``
or the card goes into the same stream once the next decoded frame arrives,
so a change on the unit and the frames that carry it line up by position,
without anyone comparing clocks.  A display photo is kept by ``photos`` and
named in its marker; the zip export packs both.

The ceiling is hard: the sealed compressed chunks, plus the compressed bytes
of the chunk being written, plus the records not yet handed to its
compressor (counted uncompressed) never exceed ``max_bytes``, whatever the
units send.  When the next record would pass it, whole chunks are dropped
from the old end.

Consecutive frames of a unit differ in a few digits, so they compress well
once the receive time stops being the noisiest field: the first record of
each chunk carries the absolute time (``t``) and every later one only the
seconds since the previous record (``dt``).  With that, 256 kB holds about
five days of one v8 unit sending every ten seconds.

The buffer is kept in a Home Assistant ``Store`` so it survives a restart,
and the diagnostics download carries it as one base64 zlib blob -- decode it
with ``scripts/frame_log_tool.py`` -- plus the markers and the latest records
in plain text.
"""

from __future__ import annotations

import base64
import json
import logging
import zlib
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 256 * 1024
DEFAULT_CHUNK_BYTES = 16 * 1024
# The open chunk keeps its lines uncompressed as well (for the export and the
# store), so it is sealed at this many uncompressed bytes too.  Frames that
# compress 30:1 would otherwise hold megabytes in memory before the
# compressed size ever reached ``DEFAULT_CHUNK_BYTES``.  384 kB keeps what
# 256 kB holds within a few percent (smaller chunks compress worse).
DEFAULT_CHUNK_RAW_BYTES = 384 * 1024
# Markers are also kept in a list of their own, outside the capped frame
# chunks, so the cases a user clicked stay listed after their frames age out.
MAX_MARKERS = 500
# Records reach the compressor in batches: a sync flush after every record
# would cost a few bytes each, and a batch this small keeps the uncompressed
# remainder, which counts against the cap at full size, small.
FLUSH_EVERY = 32

KIND_V7 = "v7"
KIND_V8 = "v8"
KIND_PARTIAL = "partial"
# bytes the server could not align into a frame; the record carries "why"
KIND_REJECTED = "rejected"
KIND_MARK = "mark"


def decode_lines(lines: Iterable[bytes]) -> Iterator[dict[str, Any]]:
    """Turn stored JSON lines back into records with an absolute ``t``.

    A line with ``t`` restarts the clock (every chunk begins with one); a
    line with ``dt`` is that many seconds after the previous record.
    """
    last: datetime | None = None
    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        if "t" in record:
            last = datetime.fromisoformat(record["t"])
        elif last is not None:
            last = datetime.fromtimestamp(
                last.timestamp() + record.pop("dt"), last.tzinfo
            )
            record["t"] = last.isoformat()
        yield record


def _valid_marker(marker: object) -> bool:
    """Return whether a stored case can be listed: an integer number and a readable time."""
    if not isinstance(marker, dict):
        return False
    number = marker.get("n")
    if not isinstance(number, int) or isinstance(number, bool):
        return False
    try:
        datetime.fromisoformat(marker["t"])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _require[T](value: object, kind: type[T], what: str) -> T:
    """``value`` when it is a ``kind``; TypeError (an unreadable store) otherwise."""
    if not isinstance(value, kind):
        msg = f"{what} is not a {kind.__name__}"
        raise TypeError(msg)
    return value


class FrameLog:
    """Append-only stream of frames and markers with a hard compressed-size cap."""

    def __init__(
        self,
        max_bytes: int = DEFAULT_MAX_BYTES,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
        chunk_raw_bytes: int = DEFAULT_CHUNK_RAW_BYTES,
    ) -> None:
        """Set up an empty, switched-off log with the given size limits."""
        if chunk_bytes * 2 > max_bytes:
            msg = "chunk_bytes must be at most half of max_bytes"
            raise ValueError(msg)
        self.max_bytes = max_bytes
        self.chunk_bytes = chunk_bytes
        self.chunk_raw_bytes = chunk_raw_bytes
        self._chunks: deque[bytes] = deque()  # sealed zlib streams, oldest first
        # the time of each sealed chunk's first record, so the age of the
        # oldest frame needs no decompression on every status poll
        self._chunk_times: deque[datetime] = deque()
        self._sealed_bytes = 0
        self._dropped_chunks = 0
        self._next_marker = 1
        self._markers: list[dict[str, Any]] = []
        self._exported_through = 0
        # Off until someone turns recording on (the test cases card).  The
        # coordinator appends nothing while it is off; the log keeps what it
        # already holds until it is cleared.
        self.enabled = False
        self._start_chunk()

    # -- writing -----------------------------------------------------------

    def _start_chunk(self) -> None:
        self._compressor = zlib.compressobj(9)
        self._current = bytearray()  # compressed bytes of the open chunk so far
        self._current_lines: list[bytes] = []  # every record of the open chunk
        self._pending: list[bytes] = []  # records not yet given to the compressor
        self._current_raw = 0  # uncompressed bytes of the open chunk
        self._current_first: datetime | None = None  # time of its first record
        self._last_time: datetime | None = None  # None: next record carries ``t``

    def append_frame(
        self, received: datetime, kind: str, raw: bytes, why: str | None = None
    ) -> None:
        """Record one frame as it arrived from a unit (``why``: a rejection's reason)."""
        if kind == KIND_V8:
            data = raw.decode("ascii", errors="replace").strip()
        else:
            data = bytes(raw).hex()
        body: dict[str, Any] = {"k": kind, "d": data}
        if why:
            body["why"] = why
        self._append(received, body)

    def append_marker(
        self,
        received: datetime,
        note: str | None = None,
        since_last_frame: dict[str, float] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int:
        """Record a marker and return its number, counted since the log began.

        ``since_last_frame`` maps a unit's serial number to how many seconds
        before the marker its last frame arrived; ``extra`` adds fields such
        as the name of a display photo uploaded with the marker.
        """
        number = self._next_marker
        self._next_marker += 1
        record: dict[str, Any] = {"k": KIND_MARK, "n": number}
        if note:
            record["note"] = note
        if since_last_frame:
            record["since"] = since_last_frame
        if extra:
            # None means "not given"; False (no frame came) must be kept
            record.update(
                {key: value for key, value in extra.items() if value is not None}
            )
        self._append(received, record)
        self._markers.append({"t": received.isoformat(), **record})
        del self._markers[:-MAX_MARKERS]
        return number

    def _append(self, received: datetime, body: dict[str, Any]) -> None:
        if self._last_time is None:
            record = {"t": received.isoformat(), **body}
            self._last_time = received
            self._current_first = received
        else:
            # Measure from the time the reader will reconstruct, not the true
            # previous one, so rounding never accumulates along a chunk.
            delta = round(received.timestamp() - self._last_time.timestamp(), 1)
            record = {"dt": delta, **body}
            self._last_time = datetime.fromtimestamp(
                self._last_time.timestamp() + delta, self._last_time.tzinfo
            )
        self._add_line(json.dumps(record, separators=(",", ":")).encode() + b"\n")

    def _add_line(self, line: bytes) -> None:
        self._current_lines.append(line)
        self._pending.append(line)
        self._current_raw += len(line)
        if len(self._pending) >= FLUSH_EVERY:
            self._flush_pending()
        if (
            len(self._current) >= self.chunk_bytes
            or self._current_raw >= self.chunk_raw_bytes
        ):
            self._seal()
        self._enforce_cap()

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        self._current += self._compressor.compress(b"".join(self._pending))
        self._current += self._compressor.flush(zlib.Z_SYNC_FLUSH)
        self._pending = []

    def _seal(self) -> None:
        self._flush_pending()
        self._current += self._compressor.flush(zlib.Z_FINISH)
        self._chunks.append(bytes(self._current))
        self._chunk_times.append(self._current_first)
        self._sealed_bytes += len(self._current)
        self._start_chunk()

    def size(self) -> int:
        """Upper bound of the compressed size, the figure the cap applies to."""
        pending = sum(len(line) for line in self._pending)
        return self._sealed_bytes + len(self._current) + pending

    def _enforce_cap(self) -> None:
        while self.size() > self.max_bytes and self._chunks:
            self._sealed_bytes -= len(self._chunks.popleft())
            self._chunk_times.popleft()
            self._dropped_chunks += 1
        if self.size() > self.max_bytes:
            # Only the open chunk is left and it alone passes the cap -- not
            # reachable while chunk_bytes <= max_bytes / 2 and records are
            # small, but the ceiling holds even then.
            self._dropped_chunks += 1
            self._start_chunk()

    def markers(self) -> list[dict[str, Any]]:
        """Every marker still listed, oldest first, with a ``downloaded`` flag.

        ``frames`` says whether the frame log still holds frames from that
        marker's time -- older ones have aged out of the capped buffer.
        """
        oldest = self._oldest_time()
        return [
            {
                **marker,
                "downloaded": marker["n"] <= self._exported_through,
                "frames": oldest is not None
                and datetime.fromisoformat(marker["t"]) >= oldest,
            }
            for marker in self._markers
        ]

    def not_downloaded(self) -> int:
        """How many listed markers have not been in an export yet."""
        return sum(1 for m in self._markers if m["n"] > self._exported_through)

    def mark_exported(self, through: int) -> None:
        """Every marker up to number ``through`` has been downloaded."""
        self._exported_through = max(self._exported_through, through)

    def clear(self) -> None:
        """Drop every frame and marker; marker numbers keep counting."""
        self._chunks.clear()
        self._chunk_times.clear()
        self._sealed_bytes = 0
        self._dropped_chunks = 0
        self._markers = []
        self._exported_through = self._next_marker - 1
        self._start_chunk()

    def forget_markers(self) -> None:
        """Clear the list of markers (the frames stay)."""
        self._markers = []

    def _oldest_time(self) -> datetime | None:
        if self._chunk_times:
            return self._chunk_times[0]
        return self._current_first if self._current_lines else None

    # -- reading -----------------------------------------------------------

    def snapshot(self) -> FrameLogSnapshot:
        """Return an immutable copy of the buffer, cheap to take on the event loop.

        Decompressing and re-encoding it is the expensive part: run
        ``snapshot.records()`` / ``snapshot.export()`` in an executor, while the
        live log keeps taking frames.
        """
        return FrameLogSnapshot(
            chunks=tuple(self._chunks),
            open_lines=b"".join(self._current_lines),
            max_bytes=self.max_bytes,
            size_bytes=self.size(),
            dropped_chunks=self._dropped_chunks,
        )

    def records(self) -> list[dict[str, Any]]:
        """Every record still held, oldest first, with absolute times."""
        return self.snapshot().records()

    def export(self, recent: int = 20) -> dict[str, Any]:
        """Return the buffer for the diagnostics download."""
        return self.snapshot().export(recent)

    # -- persistence -------------------------------------------------------

    def to_store(self) -> dict[str, Any]:
        """Return the serialisable state: sealed chunks as they are, the open chunk recompressed."""
        return {
            "chunks": [base64.b64encode(chunk).decode() for chunk in self._chunks],
            "open": base64.b64encode(
                zlib.compress(b"".join(self._current_lines), 9)
            ).decode(),
            "dropped_chunks": self._dropped_chunks,
            "next_marker": self._next_marker,
            "markers": self._markers,
            "exported_through": self._exported_through,
            "enabled": self.enabled,
        }

    def load_store(self, data: dict[str, Any]) -> None:
        """Restore what ``to_store`` saved; an unreadable store leaves the log empty."""
        try:
            chunks = [base64.b64decode(chunk) for chunk in data.get("chunks", [])]
            stored_open = data.get("open")
            open_lines = (
                zlib.decompress(base64.b64decode(stored_open)) if stored_open else b""
            )
            open_records = list(decode_lines(open_lines.splitlines(keepends=True)))
            chunk_times = [
                datetime.fromisoformat(
                    json.loads(zlib.decompress(chunk).split(b"\n", 1)[0])["t"]
                )
                for chunk in chunks
            ]
            dropped_chunks = int(data.get("dropped_chunks", 0))
            next_marker = int(data.get("next_marker", 1))
            exported_through = int(data.get("exported_through", 0))
            # A store from before the switch was recording all along: keep it on.
            enabled = _require(data.get("enabled", True), bool, "enabled")
            markers = _require(data.get("markers", []), list, "markers")
            # every open record needs its absolute time before anything is
            # replayed, so a bad one cannot leave the log half restored
            replay = [
                (datetime.fromisoformat(record.pop("t")), record)
                for record in open_records
            ]
        except (ValueError, TypeError, KeyError, AttributeError, zlib.error) as err:
            _LOGGER.warning("Discarding an unreadable Aseko frame log: %s", err)
            return
        self._chunks = deque(chunks)
        self._chunk_times = deque(chunk_times)
        self._sealed_bytes = sum(len(chunk) for chunk in chunks)
        self._dropped_chunks = dropped_chunks
        self._next_marker = next_marker
        # a damaged marker is dropped on its own; the rest of the log stays
        self._markers = [m for m in markers if _valid_marker(m)][-MAX_MARKERS:]
        self._exported_through = exported_through
        self.enabled = enabled
        backfill = "markers" not in data
        self._start_chunk()
        # Re-encode rather than replay the lines: a chunk sealed on the way
        # must start again with an absolute time.
        for received, record in replay:
            self._append(received, record)
        self._enforce_cap()
        if backfill:
            # A store written before cases were listed: rebuild the list from
            # the markers still in the frames.
            self._markers = [r for r in self.records() if r.get("k") == KIND_MARK][
                -MAX_MARKERS:
            ]


@dataclass(frozen=True)
class FrameLogSnapshot:
    """What a ``FrameLog`` held at one moment; safe to read from any thread."""

    chunks: tuple[bytes, ...]
    open_lines: bytes
    max_bytes: int
    size_bytes: int
    dropped_chunks: int

    def lines(self) -> Iterator[bytes]:
        """Return the stored JSON lines, oldest first."""
        for chunk in self.chunks:
            yield from zlib.decompress(chunk).splitlines(keepends=True)
        yield from self.open_lines.splitlines(keepends=True)

    def records(self) -> list[dict[str, Any]]:
        """Every record, oldest first, with absolute times."""
        return list(decode_lines(self.lines()))

    def export(self, recent: int = 20) -> dict[str, Any]:
        """Return the buffer for the diagnostics download."""
        return self.records_and_export(recent)[1]

    def records_and_export(
        self, recent: int = 20
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Return ``records()`` and ``export()`` from a single decompression.

        The export download needs both; reading the chunks once gives them
        from the same moment and does not unpack the log three times.
        """
        data = b"".join(self.lines())
        records = list(decode_lines(data.splitlines(keepends=True)))
        return records, {
            "about": (
                "Raw frames and mark_dump markers in the order Home Assistant "
                "received them. 'blob' is the whole buffer: base64 of zlib-compressed "
                "JSON lines; decode it with scripts/frame_log_tool.py."
            ),
            "cap_bytes": self.max_bytes,
            "size_bytes": self.size_bytes,
            "records": len(records),
            "oldest": records[0]["t"] if records else None,
            "newest": records[-1]["t"] if records else None,
            "dropped_chunks": self.dropped_chunks,
            "markers": [r for r in records if r.get("k") == KIND_MARK],
            "recent": records[-recent:],
            "blob": base64.b64encode(zlib.compress(data, 9)).decode(),
        }
