"""HTTP side of the Aseko test cases card: photo upload, live status and zip export.

The card (``frontend/aseko-test-cases-card.js``) is loaded on every dashboard, so
``type: custom:aseko-test-cases-card`` works without adding a resource by hand.  It
talks to these authenticated endpoints, admin only like the diagnostics
download they extend:

* ``POST /api/aseko_local/photo`` -- a photo straight from the phone camera
  (multipart field ``photo``, optional ``note``).  The photo is stored under
  the upload time at once; the marker goes into every recording entry's frame
  log after the next whole frame (``wait``, ``serial_number``).
* ``GET /api/aseko_local/status`` -- how long ago each unit's last frame
  arrived, so the card can show it while waiting before a change.
* ``GET /api/aseko_local/export`` -- frames, markers, diagnostics and photos
  as one zip.
* ``POST /api/aseko_local/recording`` -- ``{"enabled": true|false}`` turns the
  frame log of every entry on or off; it is off until someone turns it on.
* ``POST /api/aseko_local/delete`` -- delete every recorded frame, case and
  photo.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.http import KEY_HASS
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..runtime import loaded_entries
from .photos import PhotoStore, build_export_zip

if TYPE_CHECKING:
    from .. import AsekoLocalConfigEntry

_LOGGER = logging.getLogger(__name__)

STATIC_URL = f"/{DOMAIN}_static"
# the newest marker number per entry an export holds, as JSON
EXPORT_THROUGH_HEADER = "X-Aseko-Export-Through"
CARD_FILE = "aseko-test-cases-card.js"
DATA_RECORDING = f"{DOMAIN}_recording"
# Well under Home Assistant's 16 MB request limit; phone photos are 2-8 MB.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def photo_store(hass: HomeAssistant) -> PhotoStore:
    """Return the one photo folder shared by every Aseko Local entry."""
    return hass.data[DATA_RECORDING]["photos"]


async def async_setup_recording(hass: HomeAssistant, version: str) -> None:
    """Serve the card, load it on every dashboard and register the endpoints, once."""
    if DATA_RECORDING in hass.data:
        return
    if hass.http is None or "frontend" not in hass.config.components:
        # A bare test instance without the web stack: nothing to serve to.
        _LOGGER.debug("HTTP or frontend not loaded; the Aseko test cases card is off")
        return
    hass.data[DATA_RECORDING] = {
        "photos": PhotoStore(Path(hass.config.path(DOMAIN, "photos"))),
    }
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False
            )
        ]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILE}?v={version}")
    hass.http.register_view(AsekoPhotoView())
    hass.http.register_view(AsekoPhotoFileView())
    hass.http.register_view(AsekoForgetView())
    hass.http.register_view(AsekoStatusView())
    hass.http.register_view(AsekoExportView())
    hass.http.register_view(AsekoExportedView())
    hass.http.register_view(AsekoRecordingView())
    hass.http.register_view(AsekoDeleteRecordingView())


def _require_admin(request: web.Request) -> HomeAssistant:
    if not request["hass_user"].is_admin:
        raise Unauthorized
    return request.app[KEY_HASS]


class _UploadRejectedError(Exception):
    """A photo upload the view answers with an error status."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


async def _read_photo_upload(
    request: web.Request,
) -> tuple[str | None, bool, int | None, bytes]:
    """(note, wait, serial number, photo) from the upload form."""
    note: str | None = None
    wait = True
    serial_number: int | None = None
    data = b""
    reader = await request.multipart()
    while (part := await reader.next()) is not None:
        if part.name == "note":
            note = (await part.text()).strip()[:200] or None
        elif part.name == "wait":
            wait = (await part.text()).strip() not in ("0", "false")
        elif part.name == "serial_number":
            text = (await part.text()).strip()
            serial_number = int(text) if text.isdigit() else None
        elif part.name == "photo":
            data = await part.read(decode=False)
            if len(data) > MAX_UPLOAD_BYTES:
                msg = "Photo too large"
                raise _UploadRejectedError(msg, 413)
    if not data:
        msg = "No photo in the upload"
        raise _UploadRejectedError(msg, 400)
    return note, wait, serial_number, data


class AsekoPhotoView(HomeAssistantView):
    """Store a display photo at once, and its marker after the next frame.

    The photo can exist before the unit has sent the change -- a unit with its
    settings menu open sends nothing until the menu is closed -- so the marker
    is written only once the next whole frame has arrived, like mark_dump.
    """

    url = f"/api/{DOMAIN}/photo"
    name = f"api:{DOMAIN}:photo"

    async def post(self, request: web.Request) -> web.Response:
        """Store a photo at once and write its marker after the next frame."""
        hass = _require_admin(request)
        received = dt_util.utcnow()
        entries = loaded_entries(hass)
        if not entries:
            return self.json_message("No Aseko Local entry is loaded", 409)
        entries = [e for e in entries if e.runtime_data.coordinator.frame_log.enabled]
        if not entries:
            return self.json_message("Recording is off", 409)

        try:
            note, wait, serial_number, data = await _read_photo_upload(request)
        except _UploadRejectedError as err:
            return self.json_message(err.message, err.status)
        if serial_number is not None:
            # wait only where that unit sends, not for a timeout elsewhere
            entries = [
                e
                for e in entries
                if e.runtime_data.coordinator.knows_serial(serial_number)
            ]
            if not entries:
                return self.json_message(
                    f"No recording entry has received a frame from {serial_number}",
                    409,
                )

        store = photo_store(hass)
        generations = {
            e.entry_id: e.runtime_data.coordinator.recording_generation for e in entries
        }
        saved = await hass.async_add_executor_job(store.save, data, received, note)

        async def mark(entry: AsekoLocalConfigEntry) -> dict[str, Any] | None:
            marker = await entry.runtime_data.coordinator.async_mark_after_frame(
                note,
                {"photo": saved.file, "captured": saved.captured},
                wait=wait,
                serial_number=serial_number,
                generation=generations[entry.entry_id],
            )
            if marker is None:
                return None  # stopped or deleted while this upload waited
            return {
                "entry": entry.title,
                "marker": marker["marker"],
                "time": dt_util.as_local(marker["time"]).isoformat(),
                "seconds_since_last_frame": marker["seconds_since_last_frame"],
                "waited_for_frame": marker["waited_for_frame"],
            }

        results = await asyncio.gather(*(mark(entry) for entry in entries))
        markers = [m for m in results if m is not None]
        if not markers:
            await hass.async_add_executor_job(store.delete, saved.file)
            return self.json_message(
                "Recording was stopped or deleted while waiting; the case and "
                "its photo were not kept",
                409,
            )
        _LOGGER.info("Aseko display photo %s stored with %s", saved.file, markers)
        return self.json(
            {"photo": saved.file, "bytes": saved.bytes, "markers": markers}
        )


class AsekoPhotoFileView(HomeAssistantView):
    """One stored photo, for the card's case list."""

    url = f"/api/{DOMAIN}/photo/{{name}}"
    name = f"api:{DOMAIN}:photo_file"

    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        """Serve one stored photo."""
        hass = _require_admin(request)
        store = photo_store(hass)
        if "/" in name or "\\" in name or name.startswith("."):
            return self.json_message("Bad photo name", 400)
        path = store.directory / name
        if not await hass.async_add_executor_job(path.is_file):
            return self.json_message("No such photo", 404)
        return web.FileResponse(path)


class AsekoForgetView(HomeAssistantView):
    """Clear the list of cases (frames and photos stay)."""

    url = f"/api/{DOMAIN}/forget"
    name = f"api:{DOMAIN}:forget"

    async def post(self, request: web.Request) -> web.Response:
        """Clear the case list of every entry; the frames stay."""
        hass = _require_admin(request)
        for entry in loaded_entries(hass):
            entry.runtime_data.coordinator.forget_markers()
        return self.json({"ok": True})


class AsekoStatusView(HomeAssistantView):
    """How long ago each unit's last frame arrived, and the cases clicked so far."""

    url = f"/api/{DOMAIN}/status"
    name = f"api:{DOMAIN}:status"

    async def get(self, request: web.Request) -> web.Response:
        """Report recording, frames, cases and photos for the card."""
        hass = _require_admin(request)
        now = dt_util.utcnow()
        store = photo_store(hass)
        photos = await hass.async_add_executor_job(store.count)
        return self.json(
            {
                "entries": [
                    {
                        "entry": entry.title,
                        "entry_id": entry.entry_id,
                        "recording": entry.runtime_data.coordinator.frame_log.enabled,
                        "seconds_since_last_frame": {
                            str(serial): age
                            for serial, age in entry.runtime_data.coordinator.seconds_since_last_frame(
                                now
                            ).items()
                        },
                        "markers": entry.runtime_data.coordinator.frame_log.markers(),
                        "not_downloaded": entry.runtime_data.coordinator.frame_log.not_downloaded(),
                    }
                    for entry in loaded_entries(hass)
                ],
                "photos": photos,
            }
        )


class AsekoExportView(HomeAssistantView):
    """Frames, markers, diagnostics and photos as one zip."""

    url = f"/api/{DOMAIN}/export"
    name = f"api:{DOMAIN}:export"

    async def get(self, request: web.Request) -> web.Response:
        """Build the export zip of every loaded entry."""
        # Imported here: diagnostics imports the platforms, which import this
        # package's __init__, which sets this module up.
        from ..diagnostics import async_get_config_entry_diagnostics  # noqa: PLC0415

        hass = _require_admin(request)
        only_new = request.query.get("new") == "1"
        created = dt_util.now()
        loaded = loaded_entries(hass)
        entries = []
        wanted_photos: set[str] = set()
        newest: dict[str, int] = {}
        for entry in loaded:
            log = entry.runtime_data.coordinator.frame_log
            listed = log.markers()
            markers = [m for m in listed if not (only_new and m["downloaded"])]
            wanted_photos.update(m["photo"] for m in markers if m.get("photo"))
            newest[entry.entry_id] = max((m["n"] for m in listed), default=0)
            # one snapshot for the frames and the diagnostics' frame log, read
            # once: both from the same moment
            records, frame_log = await hass.async_add_executor_job(
                log.snapshot().records_and_export
            )
            entries.append(
                {
                    "title": entry.title,
                    "entry_id": entry.entry_id,
                    "records": records,
                    "cases": markers,
                    "diagnostics": await async_get_config_entry_diagnostics(
                        hass, entry, frame_log_export=frame_log
                    ),
                }
            )
        store = photo_store(hass)

        def build() -> bytes:
            # list and read the photos under the store's lock: no upload or
            # cap can change them in between
            with store.lock:
                photos = store.files()
                if only_new:
                    photos = [p for p in photos if p.name in wanted_photos]
                return build_export_zip(entries, photos, created)

        body = await hass.async_add_executor_job(build)
        filename = f"aseko-local-export-{created.strftime('%Y%m%d-%H%M%S')}.zip"
        # Nothing is marked downloaded here: the response may never arrive.
        # The card confirms with the ids below once it holds the whole zip.
        return web.Response(
            body=body,
            content_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                EXPORT_THROUGH_HEADER: json.dumps(newest),
            },
        )


class AsekoExportedView(HomeAssistantView):
    """The card received an export: mark its cases downloaded."""

    url = f"/api/{DOMAIN}/exported"
    name = f"api:{DOMAIN}:exported"

    async def post(self, request: web.Request) -> web.Response:
        """Mark the cases the card has downloaded."""
        hass = _require_admin(request)
        try:
            through = (await request.json())["through"]
            marks = {str(entry_id): int(n) for entry_id, n in through.items()}
        except (ValueError, KeyError, TypeError, AttributeError):
            return self.json_message('Expected {"through": {entry_id: n}}', 400)
        for entry in loaded_entries(hass):
            if entry.entry_id in marks:
                entry.runtime_data.coordinator.mark_exported(marks[entry.entry_id])
        return self.json({"marked": marks})


class AsekoRecordingView(HomeAssistantView):
    """Turn the frame log of every entry on or off."""

    url = f"/api/{DOMAIN}/recording"
    name = f"api:{DOMAIN}:recording"

    async def post(self, request: web.Request) -> web.Response:
        """Turn recording on or off in every entry."""
        hass = _require_admin(request)
        try:
            enabled = (await request.json())["enabled"]
        except (ValueError, KeyError, TypeError):
            enabled = None
        if not isinstance(enabled, bool):
            return self.json_message('Expected {"enabled": true|false}', 400)
        for entry in loaded_entries(hass):
            entry.runtime_data.coordinator.set_recording(enabled=enabled)
        return self.json({"enabled": enabled})


class AsekoDeleteRecordingView(HomeAssistantView):
    """Delete every recorded frame, case and photo; recording stays as it is."""

    url = f"/api/{DOMAIN}/delete"
    name = f"api:{DOMAIN}:delete"

    async def post(self, request: web.Request) -> web.Response:
        """Delete the recording of every entry and its photos."""
        hass = _require_admin(request)
        for entry in loaded_entries(hass):
            entry.runtime_data.coordinator.clear_recording()
        photos = await hass.async_add_executor_job(photo_store(hass).clear)
        return self.json({"photos_deleted": photos})
