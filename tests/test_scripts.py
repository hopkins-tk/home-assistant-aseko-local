"""scripts/hex_tools.py and scripts/v8_tools.py, run the way people run them."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from custom_components.aseko_local.decoding.frames.v8 import (
    _HEADER_RE,
    parse_v8_sections,
)
from custom_components.aseko_local.decoding.profiles.v8 import model_from_header_type

from .test_decode_v7 import _make_base_bytes
from .test_decode_v8 import REFERENCE_FRAME

ROOT = Path(__file__).resolve().parents[1]
V7_HEX = bytes(_make_base_bytes()).hex(" ")
V8_FRAME = REFERENCE_FRAME.decode().strip()


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )


def _load(script: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        script.removesuffix(".py"), ROOT / "scripts" / script
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── hex_tools ────────────────────────────────────────────────────────────────


def test_hex_tools_help() -> None:
    result = _run("hex_tools.py", "--help")
    assert result.returncode == 0, result.stderr
    assert "--byteinfo" in result.stdout


def test_hex_tools_byteinfo_shows_the_byte_and_its_word() -> None:
    result = _run("hex_tools.py", V7_HEX, "--byteinfo", "25")
    assert result.returncode == 0, result.stderr
    # water temperature 24.5 is bytes 25-26 = 0x00f5
    assert result.stdout.strip() == (
        "byte[25] = 0x00 = 0 = 0b00000000 / word[25-26] = 0x00f5 = 245"
    )


def test_hex_tools_byteinfo_outside_the_frame_is_an_error() -> None:
    result = _run("hex_tools.py", V7_HEX, "--byteinfo", "120")
    assert result.returncode != 0
    assert "outside the frame" in result.stderr


def test_hex_tools_table_lists_every_byte() -> None:
    result = _run("hex_tools.py", V7_HEX, "--table")
    assert result.returncode == 0, result.stderr
    assert sum(line[:3].isdigit() for line in result.stdout.splitlines()) == 120


def test_hex_tools_tablewrite_writes_where_asked(tmp_path) -> None:
    out = tmp_path / "table.md"
    result = _run("hex_tools.py", V7_HEX, "--tablewrite", str(out))
    assert result.returncode == 0, result.stderr
    assert out.read_text(encoding="utf-8").count("\n") == 122


def test_hex_tools_generated_test_leaves_the_values_to_fill_in() -> None:
    result = _run("hex_tools.py", V7_HEX, "--generate-test")
    assert result.returncode == 0, result.stderr
    assert "assert device.serial_number == 1234" in result.stdout
    assert "TODO" in result.stdout
    assert "max_refill_time" not in result.stdout  # no old byte map
    compile(result.stdout, "generated", "exec")


# ── v8_tools ─────────────────────────────────────────────────────────────────


def test_v8_tools_help() -> None:
    result = _run("v8_tools.py", "--help")
    assert result.returncode == 0, result.stderr
    assert "--annotate" in result.stdout


@pytest.mark.parametrize(
    "frame",
    [
        V8_FRAME,
        V8_FRAME[:-1] + " crc16: 1a2B}",
        V8_FRAME.replace("ains: 708", "ains: x7", 1),
    ],
)
def test_v8_tools_parses_like_the_integration(frame) -> None:
    """The standalone parser must not drift from decoding/frames/v8.py."""
    v8_tools = _load("v8_tools.py")
    _, sections = v8_tools.parse_v8_frame(frame)
    body = frame.strip()[1:-1].strip()
    assert sections == {s.name: s.values for s in parse_v8_sections(body)}
    assert _HEADER_RE.match(body)


@pytest.mark.parametrize(
    "header_type", [0, 99, 100, 105, 199, 200, 799, 804, 812, 899, 900]
)
def test_v8_tools_names_models_like_the_integration(header_type) -> None:
    v8_tools = _load("v8_tools.py")
    model = model_from_header_type(header_type)
    assert v8_tools.model_from_header_type(header_type) == (
        model.name if model is not None else None
    )


def test_v8_tools_annotates_crc16_as_hex() -> None:
    result = _run("v8_tools.py", V8_FRAME[:-1] + " crc16: 1a2b}", "--annotate")
    assert result.returncode == 0, result.stderr
    assert "0x1a2b" in result.stdout
    assert "water_temperature" in result.stdout


def test_v8_tools_generated_test_names_the_model_from_the_header() -> None:
    salt = V8_FRAME.replace("{v1 123456789 804", "{v1 123456789 105", 1)
    result = _run("v8_tools.py", salt, "--generate-test")
    assert result.returncode == 0, result.stderr
    assert "AsekoDeviceType.SALT" in result.stdout
    assert "AsekoDeviceType.NET" not in result.stdout
    compile(result.stdout, "generated", "exec")


def test_v8_tools_rejects_a_frame_without_braces() -> None:
    result = _run("v8_tools.py", "v1 1 804 0 27 ins: 1", "--annotate")
    assert result.returncode != 0
