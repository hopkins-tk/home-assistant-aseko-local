"""Photos of the unit's display that go with frame-log markers, and the zip export.

The Aseko test cases card uploads a photo straight from the phone's camera.  The
photo is kept here at once, named after the upload time; its marker is written
into the frame log after the next decoded frame and names the photo, so photo
and frames line up without EXIF data, file names or anyone comparing clocks.
Messengers strip all of those; this path never leaves Home Assistant.  A mark
cancelled while it waited (recording stopped or deleted) removes its photo.

Photos are downscaled (longest side ``MAX_SIDE`` px, JPEG) when Pillow can
read them, and the folder is capped in bytes and count: the oldest photos go
first.  ``build_export_zip`` packs frames, markers, diagnostics and photos
into one file to attach to a GitHub issue.

Everything here is blocking file and image work: call it from an executor.
"""

from __future__ import annotations

import io
import json
import logging
import re
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_COUNT = 200
MAX_SIDE = 2048
JPEG_QUALITY = 85
EXIF_DATETIME_ORIGINAL = 36867
EXIF_IFD = 0x8769


@dataclass
class SavedPhoto:
    """What was stored for one upload."""

    file: str
    bytes: int
    captured: str | None  # the camera's own timestamp, when the file carried one


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40]


class PhotoStore:
    """A capped folder of display photos."""

    def __init__(
        self,
        directory: Path,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_count: int = DEFAULT_MAX_COUNT,
    ) -> None:
        """Set up a photo folder with its size and count limits."""
        self.directory = directory
        self.max_bytes = max_bytes
        self.max_count = max_count
        # Held while a photo is written, old ones are dropped and an export
        # reads them, so an export never meets a half-written or vanishing file.
        self.lock = threading.Lock()

    def save(
        self, data: bytes, received: datetime, note: str | None = None
    ) -> SavedPhoto:
        """Store one uploaded image and return its file name."""
        self.directory.mkdir(parents=True, exist_ok=True)
        image, captured, suffix = _prepare(data)
        stem = received.strftime("%Y%m%d-%H%M%S")
        if note:
            stem += f"_{_slug(note)}"
        with self.lock:
            path = self._reserve(stem, suffix)
            temporary = path.with_name(f".{path.name}.part")
            temporary.write_bytes(image)
            temporary.replace(path)
            self._enforce_cap()
        return SavedPhoto(file=path.name, bytes=len(image), captured=captured)

    def _reserve(self, stem: str, suffix: str) -> Path:
        """Claim a free file name: creating it fails if another upload has it."""
        counter = 1
        while True:
            name = f"{stem}{suffix}" if counter == 1 else f"{stem}_{counter}{suffix}"
            path = self.directory / name
            try:
                with path.open("xb"):
                    return path
            except FileExistsError:
                counter += 1

    def files(self) -> list[Path]:
        """Return the stored photos, oldest first."""
        if not self.directory.is_dir():
            return []
        return sorted(
            (
                p
                for p in self.directory.iterdir()
                if p.is_file() and not p.name.startswith(".")
            ),
            key=lambda p: (p.stat().st_mtime, p.name),
        )

    def delete(self, name: str) -> None:
        """Delete one stored photo, if it is still there."""
        with self.lock:
            (self.directory / name).unlink(missing_ok=True)

    def clear(self) -> int:
        """Delete every stored photo; return how many."""
        with self.lock:
            files = self.files()
            for path in files:
                path.unlink(missing_ok=True)
        return len(files)

    def count(self) -> int:
        """How many photos are stored, read under the lock."""
        with self.lock:
            return len(self.files())

    def size(self) -> int:
        """Return the bytes the stored photos take."""
        return sum(p.stat().st_size for p in self.files())

    def _enforce_cap(self) -> None:
        files = self.files()
        total = sum(p.stat().st_size for p in files)
        # The newest photo always stays: it is the one a marker just named.
        while len(files) > 1 and (
            total > self.max_bytes or len(files) > self.max_count
        ):
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            _LOGGER.debug("Dropped the oldest Aseko photo %s", oldest.name)


def _prepare(data: bytes) -> tuple[bytes, str | None, str]:
    """Downscale to JPEG and read the capture time; keep the bytes if Pillow can't."""
    try:
        from PIL import Image, ImageOps  # noqa: PLC0415
    except ImportError:
        return data, None, ".jpg"
    try:
        with Image.open(io.BytesIO(data)) as original:
            captured = _capture_time(original)
            image = ImageOps.exif_transpose(original)
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
            return out.getvalue(), captured, ".jpg"
    except Exception as err:  # noqa: BLE001 -- any unreadable upload is kept as is
        _LOGGER.warning(
            "Could not read the uploaded photo, keeping it as sent: %s", err
        )
        return data, None, ".bin"


def _capture_time(image: Image) -> str | None:
    try:
        exif = image.getexif()
        value = exif.get_ifd(EXIF_IFD).get(EXIF_DATETIME_ORIGINAL) or exif.get(306)
    except Exception:  # noqa: BLE001
        return None
    if not value:
        return None
    try:
        # EXIF carries the camera's wall clock and no zone: kept as it is
        return datetime.strptime(  # noqa: DTZ007
            str(value), "%Y:%m:%d %H:%M:%S"
        ).isoformat()
    except ValueError:
        return None


def build_export_zip(
    entries: list[dict[str, Any]],
    photos: list[Path],
    created: datetime,
) -> bytes:
    """One zip for a GitHub issue: frames and markers per entry, diagnostics, photos.

    ``entries`` holds, per config entry, ``title``, ``records`` (the frame log
    with absolute times) and ``diagnostics`` (what the diagnostics download
    would contain).
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        lines = [
            "Aseko Local export",
            f"created: {created.isoformat()}",
            "",
            "frames-<entry>.jsonl  every frame and marker, oldest first, one JSON",
            "                      object a line; 'k' is v7 / v8 / partial / rejected / mark",
            "cases-<entry>.json    the cases (markers) in this export; 'photo' names the",
            "                      file in photos/, 'frames' is false once the frames",
            "                      of that time have aged out of the log",
            "markers-<entry>.json  every marker still in the frame log",
            "diagnostics-<entry>.json  the diagnostics download of that entry",
            "photos/               display photos, named by upload time (UTC)",
        ]
        archive.writestr("README.txt", "\n".join(lines) + "\n")
        for entry in entries:
            # The title labels the files; the entry id keeps two entries with
            # the same (or same-looking) title from overwriting each other.
            parts = (_slug(entry["title"]), entry.get("entry_id"))
            slug = "-".join(part for part in parts if part) or "entry"
            records = entry["records"]
            archive.writestr(
                f"frames-{slug}.jsonl",
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
            )
            archive.writestr(
                f"markers-{slug}.json",
                json.dumps([r for r in records if r.get("k") == "mark"], indent=2),
            )
            archive.writestr(
                f"cases-{slug}.json",
                json.dumps(entry.get("cases", []), indent=2, ensure_ascii=False),
            )
            archive.writestr(
                f"diagnostics-{slug}.json",
                json.dumps(entry["diagnostics"], indent=2, default=str),
            )
        for photo in photos:
            try:
                archive.write(photo, f"photos/{photo.name}")
            except FileNotFoundError:
                # dropped by the cap after the list was taken: skip, not fail
                _LOGGER.debug("Aseko photo %s vanished during the export", photo.name)
    return buffer.getvalue()
