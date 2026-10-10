"""scripts/frame_log_tool.py run the way the docs tell people to run it."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custom_components.aseko_local.recording.frame_log import KIND_V7, FrameLog

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "frame_log_tool.py"
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # a fresh interpreter: nothing of frame_log is imported yet
    return subprocess.run(
        [sys.executable, "-B", str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )


def _diagnostics(tmp_path: Path) -> Path:
    log = FrameLog()
    for i in range(5):
        log.append_frame(T0 + timedelta(seconds=10 * i), KIND_V7, bytes([i]) * 120)
    log.append_marker(T0 + timedelta(seconds=25), note="pump on")
    log.append_frame(T0 + timedelta(seconds=300), KIND_V7, b"\x09" * 120)
    blob = base64.b64encode(zlib.compress(b"".join(log.snapshot().lines()), 9))
    path = tmp_path / "diagnostics.json"
    path.write_text(
        json.dumps({"data": {"frame_log": {"blob": blob.decode()}}}), encoding="utf-8"
    )
    return path


def test_help_runs() -> None:
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "--around" in result.stdout


def test_lists_the_markers(tmp_path) -> None:
    result = _run(str(_diagnostics(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "marker   1" in result.stdout
    assert "pump on" in result.stdout
    assert "7 records" in result.stdout


def test_around_prints_the_frames_near_a_marker(tmp_path) -> None:
    result = _run(str(_diagnostics(tmp_path)), "--around", "1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert any("MARK 1 pump on" in line for line in lines)
    # five frames within a minute of the marker; the one 275 s later is left out
    assert sum(" v7 " in line for line in lines) == 5


def test_jsonl_writes_every_record(tmp_path) -> None:
    out = tmp_path / "frames.jsonl"
    result = _run(str(_diagnostics(tmp_path)), "--jsonl", str(out))
    assert result.returncode == 0, result.stderr
    records = [
        json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 7
    assert [r["k"] for r in records].count("mark") == 1
