"""Display photos for frame-log markers and the zip export."""

from __future__ import annotations

import io
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from PIL import Image

from custom_components.aseko_local.recording.frame_log import KIND_V8, FrameLog
from custom_components.aseko_local.recording.photos import (
    MAX_SIDE,
    PhotoStore,
    build_export_zip,
)

T0 = datetime(2026, 9, 13, 10, 1, 5, tzinfo=UTC)


def _jpeg(width: int, height: int, captured: str | None = None) -> bytes:
    image = Image.new("RGB", (width, height), (30, 120, 200))
    exif = Image.Exif()
    if captured:
        exif.get_ifd(0x8769)[36867] = captured
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_photo_is_downscaled_named_by_upload_time_and_keeps_capture_time(
    tmp_path,
) -> None:
    store = PhotoStore(tmp_path)
    saved = store.save(
        _jpeg(4000, 3000, "2026:09:13 12:01:02"), T0, "Heating control ON"
    )

    assert saved.file == "20260913-100105_Heating-control-ON.jpg"
    assert saved.captured == "2026-09-13T12:01:02"
    with Image.open(tmp_path / saved.file) as stored:
        assert max(stored.size) == MAX_SIDE


def test_same_second_uploads_do_not_overwrite(tmp_path) -> None:
    store = PhotoStore(tmp_path)
    first = store.save(_jpeg(100, 100), T0)
    second = store.save(_jpeg(100, 100), T0)
    assert first.file != second.file
    assert len(store.files()) == 2


def test_unreadable_upload_is_kept_as_sent(tmp_path) -> None:
    saved = PhotoStore(tmp_path).save(b"not an image", T0)
    assert saved.file.endswith(".bin")
    assert (tmp_path / saved.file).read_bytes() == b"not an image"
    assert saved.captured is None


def test_folder_cap_drops_the_oldest_photos(tmp_path) -> None:
    store = PhotoStore(tmp_path, max_bytes=10**9, max_count=3)
    names = []
    for i in range(5):
        saved = store.save(_jpeg(200, 200), T0 + timedelta(seconds=i))
        os.utime(tmp_path / saved.file, (1_000_000 + i, 1_000_000 + i))
        names.append(saved.file)
    assert [p.name for p in store.files()] == names[-3:]

    # a cap smaller than one photo still keeps the photo just uploaded
    small = PhotoStore(tmp_path, max_bytes=1, max_count=100)
    latest = small.save(_jpeg(200, 200), T0 + timedelta(seconds=10))
    assert [p.name for p in small.files()] == [latest.file]


def test_export_zip_holds_frames_markers_diagnostics_and_photos(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    log = FrameLog()
    log.append_frame(T0, KIND_V8, b"{v1 123 804 0 27 ins: 1}\n")
    saved = store.save(_jpeg(300, 200), T0 + timedelta(seconds=3), "pH 7.2")
    log.append_marker(
        T0 + timedelta(seconds=3), "pH 7.2", {"123": 3.0}, {"photo": saved.file}
    )

    body = build_export_zip(
        [{"title": "Aseko Local", "records": log.records(), "diagnostics": {"a": 1}}],
        store.files(),
        T0,
    )
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = set(archive.namelist())
        assert {
            "README.txt",
            "frames-Aseko-Local.jsonl",
            "markers-Aseko-Local.json",
            "diagnostics-Aseko-Local.json",
            f"photos/{saved.file}",
        } <= names
        markers = json.loads(archive.read("markers-Aseko-Local.json"))
        assert markers[0]["photo"] == saved.file
        assert markers[0]["since"] == {"123": 3.0}
        frames = archive.read("frames-Aseko-Local.jsonl").decode().splitlines()
        assert json.loads(frames[0])["k"] == "v8"


def test_export_zip_keeps_two_entries_with_the_same_title_apart(tmp_path) -> None:
    """R9: files are named by title and entry id, so equal titles do not collide."""
    log = FrameLog()
    log.append_frame(T0, KIND_V8, b"{v1 123 804 0 27 ins: 1}\n")
    entries = [
        {
            "title": "Aseko Local",
            "entry_id": "01AAA",
            "records": log.records(),
            "diagnostics": {"a": 1},
        },
        {
            "title": "Aseko Local",
            "entry_id": "01BBB",
            "records": [],
            "diagnostics": {"b": 2},
        },
    ]
    body = build_export_zip(entries, [], T0)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
    assert len(names) == len(set(names))
    assert "frames-Aseko-Local-01AAA.jsonl" in names
    assert "diagnostics-Aseko-Local-01BBB.json" in names


def test_concurrent_uploads_in_the_same_second_get_their_own_files(tmp_path) -> None:
    """Minor fix 3: the name is claimed atomically, no upload overwrites another."""
    store = PhotoStore(tmp_path / "photos")
    when = T0 + timedelta(seconds=5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        saved = list(
            pool.map(lambda i: store.save(_jpeg(40 + i, 30), when, "pH"), range(8))
        )
    names = {s.file for s in saved}
    assert len(names) == 8
    assert len(store.files()) == 8
    assert not any(p.name.startswith(".") for p in (tmp_path / "photos").iterdir())


def test_export_skips_a_photo_that_vanished_after_the_list(tmp_path) -> None:
    """Minor fix 3: a photo dropped between listing and reading does not fail the zip."""
    store = PhotoStore(tmp_path / "photos")
    kept = store.save(_jpeg(40, 30), T0, "kept")
    gone = store.save(_jpeg(40, 30), T0 + timedelta(seconds=1), "gone")
    photos = store.files()
    (store.directory / gone.file).unlink()

    body = build_export_zip([], photos, T0)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
    assert f"photos/{kept.file}" in names
    assert f"photos/{gone.file}" not in names
