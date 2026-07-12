"""Temporary diagnostic dumper for v8 SALT NET frames (Issue #131 triage).

**Status: TEMPORARY** — this module is a triage aid for the ongoing
mirovra SALT NET investigation. It writes one line per *unique* v8
frame to a Markdown file so the wire-level frame can be compared
against mirovra's "History" screenshot from the Aseko mobile app.

**Activation:** enabled by default while the SALT NET triage is open
(see `DUMP_ENABLED` below). Disable by setting the constant to
`False` once the question list in `docs/temp/issue131_questions_mivovra.md`
is answered. The overhead is negligible — one disk write per
*unique* frame, not per frame — and identical frames are
de-duplicated in-memory (the Aseko app typically sends 0.5–1
frames per second, most of which are identical).

**Dedup: how "only when something changes" works**
The dumper keeps, in memory, the *last seen* raw frame per
device serial. On every `record(raw)` call it:

  1. Renders `raw` to a one-line ASCII string
     (`_frame_to_ascii_line`).
  2. Extracts the serial from the `{v1 <serial> …}` header
     (`_extract_serial`) — frames without a parseable header
     are silently skipped.
  3. Compares the rendered line with the cached one for that
     serial. **If identical → no disk write.** The function
     returns silently.
  4. Otherwise the line is written to the dump file (with a
     timestamp prefix) and the cache is updated.

The on-disk result is therefore a chronological list of *state
changes* — identical frames at 1 Hz for an hour produce zero
writes, while a pump turning on produces exactly one new line
when the corresponding `outs[…]` byte flips. This is what
mirovra's "History" screenshot shows, so the two can be
correlated line-for-line.

**Why raw frames, not decoded fields?** mirovra's screenshot shows
the public Aseko app view (pump running, electrolysis power,
algicide flow rate, …) but not the full configuration. To
correlate the wire-level state with the app view, we need the
*raw* frame on disk so a developer (or mirovra) can decode it
with `scripts/v8_tools.py` and see every section. Crucially,
when mirovra switches the pump from algicide to flocculant (or
toggles a feature), the decoded-field set we are interested in
may *change* — but the raw frame still shows the truth. The
raw-frame approach is forward-compatible: any future field can
be inspected post-hoc without re-running the capture.

**Where the file lives:** `/config/aseko_dump.md` by default. That
is the same directory HA keeps `configuration.yaml` in, so the
file is reachable via VS Code Server (Samba share, File editor
add-on, etc.) without a separate path lookup. On a HA Container
or HA Core install without a `/config` directory, override via
the `ASEKO_DUMP_PATH` environment variable. The file is created
lazily on the first unique frame; it is *not* truncated on each
run, so a long-running HA instance accumulates a chronological
history across restarts.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

_LOGGER = logging.getLogger(__name__)


# Toggle this to False once the SALT NET triage is closed and the
# v8 helper capability map is finalised. See module docstring.
DUMP_ENABLED: bool = True


# Default path used when ASEKO_DUMP_PATH is not set. `/config` is
# the HA Core / HA OS / HA Container config directory, the same
# level as `configuration.yaml`, so the file is reachable from
# VS Code Server, the File editor add-on, the Samba share, and
# `ha core logs` without any extra setup. Operators on non-`/config`
# installs (e.g. a plain Python venv) can override via
# ASEKO_DUMP_PATH.
DEFAULT_DUMP_PATH: str = "/config/aseko_dump.md"


def _resolve_dump_path() -> Path:
    """Resolve the on-disk path for the dump file.

    Honours the `ASEKO_DUMP_PATH` environment variable so an
    operator can redirect captures to a persistent location
    (e.g. `/config/aseko_dump.md` on a HA OS install) without
    touching the source code.
    """
    return Path(os.environ.get("ASEKO_DUMP_PATH", DEFAULT_DUMP_PATH))


def _frame_to_ascii_line(raw: bytes) -> str:
    """Return a one-line ASCII rendering of a v8 frame.

    Strips the trailing newline (the frame ends with `…}\\n` on
    the wire) and collapses any embedded whitespace to single
    spaces so the result fits on a single Markdown line. Returns
    the empty string if `raw` is not decodable as ASCII.
    """
    try:
        text = raw.decode("ascii", errors="replace").strip()
    except Exception:
        return ""
    return " ".join(text.split())


class V8FrameDumper:
    """Append-only, dedup-by-content dumper for v8 frames.

    Single-process, thread-safe (the decoder may be called from
    the asyncio event loop on a worker thread, and `record()` is
    called from there). The dumper keeps a fingerprint of the
    *last* frame for each device in memory; an incoming frame
    is appended **only when it differs** from the last one.
    This keeps the dump file readable when the device sends the
    same state at 1 Hz for hours.

    One instance per process, accessed via `V8FrameDumper.get()`.
    Tests that need a fresh instance use the `reset()` class
    method to clear the singleton.
    """

    _instance: "V8FrameDumper | None" = None

    def __init__(self, dump_path: Path) -> None:
        self._path = dump_path
        # Per-device cache of the last-written ASCII rendering. The
        # dedup decision in `_has_changed` reads + writes this dict
        # under `_lock`. Keyed by device serial so two v8 devices
        # on the same HA instance do not collide.
        self._last_per_serial: dict[int, str] = {}
        # Whether the dump file's Markdown header has been emitted.
        # Stays True once set, even if the file is later deleted by
        # the operator — the next record re-creates the file with
        # just the new line (no header) and we log a hint that the
        # operator wiped history. The simpler behaviour is to
        # always re-emit the header on a fresh file.
        self._header_written: bool = False
        # Counters for the diagnostics below. Useful for both
        # "did the dumper actually dedup" assertions in tests and
        # for operators reading the HA log when the dump file is
        # suspiciously small.
        self.frames_seen: int = 0
        self.frames_written: int = 0
        self.frames_deduped: int = 0
        self._lock = Lock()

    @classmethod
    def get(cls) -> "V8FrameDumper":
        """Return the process-wide singleton, creating it on first use.

        The path is resolved from the `ASEKO_DUMP_PATH` env var (or
        the built-in default) the first time the singleton is
        instantiated. Tests that need a different path should
        construct a `V8FrameDumper(path)` directly and use
        `V8FrameDumper.reset()` + re-instantiation to re-bind.
        """
        if cls._instance is None:
            cls._instance = cls(_resolve_dump_path())
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Drop the singleton (test helper).

        After calling `reset()`, the next `get()` returns a fresh
        dumper using the current `ASEKO_DUMP_PATH` env var. Used
        by tests that need to swap the path between cases.
        """
        cls._instance = None

    def record(self, raw: bytes) -> None:
        """Maybe-append `raw` (a v8 text frame) to the dump file.

        No-op when `DUMP_ENABLED` is False, when `raw` is empty,
        or when the ASCII rendering of the frame matches the
        last-seen frame for the same device (deduplication).

        The frame's serial number is extracted from the
        `{v1 <serial> …}` header so the dedup is per-device — a
        second v8 device (or a NET v8 unit) does not collide with
        the SALT NET we are triaging.

        Diagnostic counters (incremented under the lock):
        - `frames_seen`   — total `record()` calls
        - `frames_written` — calls that produced a new dump line
        - `frames_deduped` — calls that matched the previous frame
        """
        if not DUMP_ENABLED:
            return
        if not raw:
            return

        line = _frame_to_ascii_line(raw)
        if not line:
            return

        serial = self._extract_serial(line)
        if serial is None:
            return  # unparseable header — skip silently

        with self._lock:
            self.frames_seen += 1
            if not self._has_changed(serial, line):
                self.frames_deduped += 1
                return
            self._last_per_serial[serial] = line
            self.frames_written += 1
            self._append(line, serial)

    def _has_changed(self, serial: int, line: str) -> bool:
        """Return True iff `line` differs from the cached frame for `serial`.

        Extracted from `record()` so the dedup decision is a
        single, named function with an obvious contract. Always
        returns True for a serial that has not been seen before
        (the first frame of a session is always written as the
        baseline).
        """
        previous = self._last_per_serial.get(serial)
        return previous != line

    @staticmethod
    def _extract_serial(ascii_line: str) -> int | None:
        """Return the `<serial>` from a `{v1 <serial> …}` header, or None."""
        # Cheap and robust: the frame always starts with `{v1 ` and
        # the serial is the first whitespace-separated token. We
        # only need the integer for the dedup key.
        if not ascii_line.startswith("{v1 "):
            return None
        parts = ascii_line.split(maxsplit=3)
        if len(parts) < 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    def _append(self, line: str, serial: int) -> None:
        """Write one record line to the dump file.

        Creates the file (and the Markdown header) on the first
        record ever written for this dumper. Subsequent records
        are appended as-is. If the operator deletes the file out
        from under us between records, the next write recreates
        it with the header (we detect the missing file via
        `self._header_written` and re-emit unconditionally on a
        fresh path).

        I/O errors are logged at WARNING and swallowed — a
        failing dump must never crash the integration.
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        out_line = f"| `{ts}` | `{serial}` | `{line}` |"
        try:
            # The header is written at most once per dumper
            # lifetime, but if the operator `rm`'d the file we
            # detect that and re-emit. This keeps the dump file
            # self-describing even after manual cleanup.
            need_header = not self._header_written or not self._path.exists()
            if need_header:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("w", encoding="utf-8") as f:
                    f.write(self._header() + "\n")
                if not self._header_written:
                    _LOGGER.info("Aseko v8 dump started at %s", self._path)
                self._header_written = True
            with self._path.open("a", encoding="utf-8") as f:
                f.write(out_line + "\n")
        except OSError as exc:
            _LOGGER.warning("Could not write v8 dump file %s: %s", self._path, exc)

    @staticmethod
    def _header() -> str:
        """Return the Markdown header written on first record."""
        return (
            "# Aseko v8 raw-frame dump (Issue #131 triage)\n"
            "\n"
            "One line per *unique* v8 frame (in-memory dedup per serial).\n"
            "Use `python scripts/v8_tools.py decode_frame <line>` (or the\n"
            "`AsekoV8Decoder.decode(raw)` Python API) to inspect a line.\n"
            "\n"
            "| timestamp | serial | raw frame |\n"
            "|-----------|--------|-----------|"
        )
