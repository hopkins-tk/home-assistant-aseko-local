"""Tests for the v8 raw-frame dumper (aseko_v8_dump.py).

The dumper is a temporary triage aid for Issue #131 (mirovra SALT
NET). These tests pin the **diff-only** behaviour:

  * First record for a serial is always written (baseline).
  * A subsequent record with the *identical* raw frame is NOT
    written (avoids flooding the file with one-line-per-frame
    spam at the Aseko app's 0.5–1 Hz frame rate).
  * A subsequent record where **any** byte differs IS written.
  * The Markdown header is written exactly once per file.
  * The default path is `/config/aseko_dump.md` so the file
    lands next to `configuration.yaml` (reachable via VS Code
    Server / Samba share / File editor add-on).
  * `ASEKO_DUMP_PATH` env var overrides the default path.
  * `DUMP_ENABLED = False` short-circuits the entire pipeline.
"""

import pytest

from custom_components.aseko_local.aseko_v8_dump import (
    DEFAULT_DUMP_PATH,
    V8FrameDumper,
    _frame_to_ascii_line,
    _resolve_dump_path,
)


# ---------- fixtures & helpers ---------------------------------------------


@pytest.fixture(autouse=True)
def _reset_dumper_singleton():
    """Reset the process-wide dumper singleton between tests.

    The module uses a class-level singleton (`V8FrameDumper._instance`)
    to avoid threading the path through every call site. Each test
    that constructs a fresh `V8FrameDumper(path)` therefore calls
    `reset()` first so the next `get()` does not return a stale
    instance from a previous test.
    """
    V8FrameDumper.reset()
    yield
    V8FrameDumper.reset()


@pytest.fixture
def dump_path(tmp_path):
    """A fresh dump path inside pytest's tmp_path (overrides env)."""
    return tmp_path / "aseko_dump.md"


def _frame(*sections: str, serial: int = 110215844, f2: int = 100) -> bytes:
    """Build a v8 text frame for testing.

    Example::

        _frame("ins: 200 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0",
               "outs: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0")
    """
    body = f"v1 {serial} {f2} 0 31 " + " ".join(sections)
    return ("{" + body + "}\n").encode("ascii")


# ---------- default path & env override -----------------------------------


def test_default_dump_path_is_under_config():
    """`DEFAULT_DUMP_PATH` is `/config/aseko_dump.md` so the file lands
    next to `configuration.yaml` and is reachable via VS Code Server /
    Samba share / File editor add-on. Hardcoding the path here keeps
    the contract from drifting silently.
    """
    assert DEFAULT_DUMP_PATH == "/config/aseko_dump.md"


def test_resolve_dump_path_prefers_env(monkeypatch, tmp_path):
    """`ASEKO_DUMP_PATH` env var overrides the default path."""
    custom = tmp_path / "elsewhere.md"
    monkeypatch.setenv("ASEKO_DUMP_PATH", str(custom))
    assert _resolve_dump_path() == custom


def test_resolve_dump_path_falls_back_to_default(monkeypatch):
    """Without the env var, the default `/config/aseko_dump.md` wins."""
    from pathlib import Path

    monkeypatch.delenv("ASEKO_DUMP_PATH", raising=False)
    assert _resolve_dump_path() == Path(DEFAULT_DUMP_PATH)


# ---------- helpers --------------------------------------------------------


def test_frame_to_ascii_line_strips_newline_and_collapses_whitespace():
    """The on-disk line must be a single line with single spaces."""
    raw = b"{v1 123 100 0 31   ins:  1   2   3   }\n"
    line = _frame_to_ascii_line(raw)
    assert "\n" not in line
    assert "  " not in line  # no double spaces
    assert line.startswith("{v1 123 100 0 31 ins: 1 2 3 }")


def test_frame_to_ascii_line_returns_empty_on_empty_input():
    """Empty input is the only path to `""`; the function uses
    `errors="replace"` so non-ASCII bytes survive (we rely on
    `_extract_serial` to drop frames without a parseable
    `{v1 …}` header downstream).
    """
    assert _frame_to_ascii_line(b"") == ""


def test_extract_serial_reads_v1_header():
    """The serial comes from the second whitespace-separated token."""
    assert V8FrameDumper._extract_serial("{v1 110215844 100 0 31 …") == 110215844
    assert V8FrameDumper._extract_serial("{v1 999 100 0 31 …") == 999
    assert V8FrameDumper._extract_serial("not a v8 frame") is None
    assert V8FrameDumper._extract_serial("{v1}") is None
    assert V8FrameDumper._extract_serial("{v1 notanumber 100 0 31 …") is None


# ---------- dedup: the headline behaviour --------------------------------


def test_identical_raw_frames_are_deduplicated(dump_path):
    """Ten identical frames at 1 Hz produce ONE record line, not ten.

    This is the headline behaviour the user asked for: the dump
    only grows when the wire-level frame *changes*, mirroring
    mirovra's "History" screenshot which only logs state changes.
    """
    dumper = V8FrameDumper(dump_path)
    frame = _frame(
        "ins: 200 0 0 0 0 0 0 0 1 0 0 0 0 24 6 29 10 28 0",
        "outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
    )
    for _ in range(10):
        dumper.record(frame)
    # Counters expose the dedup arithmetic
    assert dumper.frames_seen == 10
    assert dumper.frames_written == 1
    assert dumper.frames_deduped == 9
    # File has exactly one record line below the table header.
    contents = dump_path.read_text(encoding="utf-8")
    record_lines = [ln for ln in contents.splitlines() if ln.startswith("| `20")]
    assert len(record_lines) == 1


def test_one_byte_change_produces_one_new_line(dump_path):
    """A single byte change in any section triggers exactly one new line."""
    dumper = V8FrameDumper(dump_path)
    base = _frame(
        "ins: 200 0 0 0 0 0 0 0 1 0 0 0 0 24 6 29 10 28 0",
        "outs: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
    )
    # Change one byte: outs[2] flips 0 → 2 (filtration pump on).
    changed = _frame(
        "ins: 200 0 0 0 0 0 0 0 1 0 0 0 0 24 6 29 10 28 0",
        "outs: 0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
    )
    dumper.record(base)
    dumper.record(base)  # duplicate → deduped
    dumper.record(changed)  # changed → written
    dumper.record(changed)  # duplicate → deduped
    assert dumper.frames_seen == 4
    assert dumper.frames_written == 2  # baseline + change
    assert dumper.frames_deduped == 2
    contents = dump_path.read_text(encoding="utf-8")
    record_lines = [ln for ln in contents.splitlines() if ln.startswith("| `20")]
    assert len(record_lines) == 2


def test_dedup_is_per_serial(dump_path):
    """Two v8 devices on the same instance do not collide with each other."""
    dumper = V8FrameDumper(dump_path)
    frame_a = _frame("ins: 0", serial=111111111)
    frame_b = _frame("ins: 0", serial=222222222)
    dumper.record(frame_a)
    dumper.record(frame_b)
    dumper.record(frame_a)  # same as first → deduped
    dumper.record(frame_b)  # same as second → deduped
    assert dumper.frames_written == 2
    assert dumper.frames_deduped == 2


# ---------- file format ---------------------------------------------------


def test_first_record_writes_header(dump_path):
    """The Markdown header is emitted exactly once on first record."""
    dumper = V8FrameDumper(dump_path)
    dumper.record(_frame("ins: 0"))
    contents = dump_path.read_text(encoding="utf-8")
    assert "# Aseko v8 raw-frame dump" in contents
    assert "One line per *unique* v8 frame" in contents
    assert "| timestamp | serial | raw frame |" in contents
    # Count only table body lines, not the header row
    body = [ln for ln in contents.splitlines() if ln.startswith("| `20")]
    assert len(body) == 1


def test_record_line_carries_serial_and_raw_frame(dump_path):
    """Each record line includes timestamp, serial, and the full raw frame."""
    dumper = V8FrameDumper(dump_path)
    dumper.record(
        _frame(
            "ins: 0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0",
            "outs: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
            serial=42,
        )
    )
    line = dump_path.read_text(encoding="utf-8").splitlines()[-1]
    assert "`42`" in line
    assert "outs: 0 0 0" in line  # raw frame content present, not decoded fields


def test_header_re_emitted_if_operator_deletes_file(dump_path):
    """If the operator `rm`'s the dump file, the next record re-emits the header."""
    dumper = V8FrameDumper(dump_path)
    dumper.record(_frame("ins: 0"))
    dump_path.unlink()  # operator wipes history
    dumper.record(_frame("ins: 0 0 0 0"))
    contents = dump_path.read_text(encoding="utf-8")
    assert "# Aseko v8 raw-frame dump" in contents  # header re-emitted
    body = [ln for ln in contents.splitlines() if ln.startswith("| `20")]
    assert len(body) == 1  # only the post-deletion record


# ---------- activation flag ----------------------------------------------


def test_dumper_no_op_when_disabled(dump_path, monkeypatch):
    """`DUMP_ENABLED = False` short-circuits the entire pipeline."""
    monkeypatch.setattr(
        "custom_components.aseko_local.aseko_v8_dump.DUMP_ENABLED", False
    )
    dumper = V8FrameDumper(dump_path)
    dumper.record(_frame("ins: 0"))
    dumper.record(_frame("ins: 0 0 0 0"))
    assert not dump_path.exists()
    assert dumper.frames_seen == 0
    assert dumper.frames_written == 0


# ---------- robustness ----------------------------------------------------


def test_dumper_no_op_for_empty_frame(dump_path):
    """An empty / unparseable frame is silently skipped."""
    dumper = V8FrameDumper(dump_path)
    dumper.record(b"")
    dumper.record(b"not a v8 frame")
    assert not dump_path.exists()


def test_dumper_no_op_for_frame_without_v1_header(dump_path):
    """A frame without the `{v1 …}` prefix is skipped (no serial = no key)."""
    dumper = V8FrameDumper(dump_path)
    dumper.record(b"{notv1 1 2 3 4}\n")
    assert not dump_path.exists()


def test_dumper_swallows_oserror(dump_path, monkeypatch):
    """A failing write must not crash the integration; counters still update."""
    dumper = V8FrameDumper(dump_path)

    # Force the underlying Path.open to raise. The dumper must
    # catch the OSError, log a warning, and continue. The
    # counters still advance (we counted the frame before
    # attempting the I/O), but the file is never created.
    def _broken_open(self, *args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr("pathlib.PosixPath.open", _broken_open)
    dumper.record(_frame("ins: 0"))  # must NOT raise
    assert dumper.frames_written == 1
    assert not dump_path.exists()
