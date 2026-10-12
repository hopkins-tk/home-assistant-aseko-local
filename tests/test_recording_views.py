"""The HTTP endpoints of the test cases card, called the way aiohttp calls them.

The views get a real coordinator and photo store; only the request and Home
Assistant around them are stand-ins, so these run without the web stack.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.http import KEY_HASS
from PIL import Image

from custom_components.aseko_local import coordinator as coordinator_module
from custom_components.aseko_local.coordinator import AsekoLocalDataUpdateCoordinator
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.recording import views
from custom_components.aseko_local.recording.photos import PhotoStore

from .test_decode_v7 import _make_base_bytes


@pytest.fixture(autouse=True)
def _quiet_logging() -> Iterator[None]:
    """Silence logging for this module's tests only, and turn it back on."""
    before = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(before)


SERIAL = 1234  # the serial number of the base frame


# ── stand-ins ────────────────────────────────────────────────────────────────


class FakePart:
    def __init__(self, name: str, value: bytes) -> None:
        self.name = name
        self._value = value

    async def text(self) -> str:
        return self._value.decode()

    async def read(self, decode: bool = False) -> bytes:
        return self._value


class FakeMultipart:
    def __init__(self, parts: dict[str, bytes]) -> None:
        self._parts = [FakePart(name, value) for name, value in parts.items()]

    async def next(self) -> FakePart | None:
        return self._parts.pop(0) if self._parts else None


class FakeRequest(dict):
    """What the views read off an aiohttp request."""

    def __init__(
        self,
        hass: object,
        admin: bool = True,
        query: dict[str, str] | None = None,
        body: object = None,
        parts: dict[str, bytes] | None = None,
    ) -> None:
        super().__init__(hass_user=MagicMock(is_admin=admin))
        self.app = {KEY_HASS: hass}
        self.query = query or {}
        self._body = body
        self._parts = parts or {}

    async def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    async def multipart(self) -> FakeMultipart:
        return FakeMultipart(dict(self._parts))


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (30, 120, 200)).save(out, "JPEG")
    return out.getvalue()


def _setup(tmp_path: Path, entries: int = 1) -> tuple[MagicMock, list[MagicMock]]:
    """Return a hass with loaded entries, each with its own real coordinator."""

    async def run_inline(job, *args: object) -> object:
        return job(*args)

    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    hass.async_add_executor_job = run_inline
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))
    hass.async_create_task.side_effect = lambda coro, *a, **k: coro.close()
    hass.data = {views.DATA_RECORDING: {"photos": PhotoStore(tmp_path / "photos")}}

    loaded = []
    for index in range(entries):
        entry = MagicMock()
        entry.entry_id = f"entry{index}"
        entry.title = f"Aseko {index}"
        entry.unique_id = f"u{index}"
        entry.data = {"host": "0.0.0.0", "port": 47524 + index}
        entry.options = {}
        entry.state = ConfigEntryState.LOADED
        entry.runtime_data.coordinator = AsekoLocalDataUpdateCoordinator(hass, entry)
        entry.runtime_data.coordinator.set_recording(enabled=True)
        loaded.append(entry)
    hass.config_entries.async_entries.return_value = loaded
    return hass, loaded


def _frame_arrives(entry: MagicMock) -> None:
    raw = bytes(_make_base_bytes())
    coordinator = entry.runtime_data.coordinator
    coordinator.store_raw_frame(raw)
    coordinator.devices_update_callback(decode(raw))


def _body(response: object) -> dict[str, Any]:
    return json.loads(response.body)


# ── admin only ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("view", "method", "args"),
    [
        (views.AsekoPhotoView, "post", ()),
        (views.AsekoPhotoFileView, "get", ("x.jpg",)),
        (views.AsekoForgetView, "post", ()),
        (views.AsekoStatusView, "get", ()),
        (views.AsekoExportView, "get", ()),
        (views.AsekoExportedView, "post", ()),
    ],
)
async def test_every_endpoint_is_admin_only(tmp_path, view, method, args) -> None:
    hass, _ = _setup(tmp_path)
    with pytest.raises(Unauthorized):
        await getattr(view(), method)(FakeRequest(hass, admin=False), *args)


# ── status ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_shows_frame_age_and_cases(tmp_path) -> None:
    hass, (entry,) = _setup(tmp_path)
    _frame_arrives(entry)
    entry.runtime_data.coordinator.mark_dump("Heating ON")

    body = _body(await views.AsekoStatusView().get(FakeRequest(hass)))

    (status,) = body["entries"]
    assert status["entry_id"] == "entry0"
    assert str(SERIAL) in status["seconds_since_last_frame"]
    assert [m["note"] for m in status["markers"]] == ["Heating ON"]
    assert status["not_downloaded"] == 1
    assert body["photos"] == 0


# ── photo upload ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_photo_upload_without_a_loaded_entry_is_refused(tmp_path) -> None:
    hass, _ = _setup(tmp_path, entries=0)
    response = await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"photo": _jpeg()})
    )
    assert response.status == 409


@pytest.mark.asyncio
async def test_photo_upload_without_a_photo_is_refused(tmp_path) -> None:
    hass, _ = _setup(tmp_path)
    response = await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"note": b"nothing attached"})
    )
    assert response.status == 400


@pytest.mark.asyncio
async def test_photo_is_stored_at_once_and_marked_after_the_next_frame(
    tmp_path,
) -> None:
    hass, (entry,) = _setup(tmp_path)
    coordinator = entry.runtime_data.coordinator
    _frame_arrives(entry)  # the unit is known to this entry
    upload = asyncio.ensure_future(
        views.AsekoPhotoView().post(
            FakeRequest(
                hass,
                parts={
                    "note": b"Winter mode ON",
                    "serial_number": str(SERIAL).encode(),
                    "photo": _jpeg(),
                },
            )
        )
    )
    for _ in range(20):  # let the upload reach its wait
        await asyncio.sleep(0)
    assert not upload.done()
    assert len(PhotoStore(tmp_path / "photos").files()) == 1  # stored already
    assert coordinator.frame_log.markers() == []  # but not marked yet

    _frame_arrives(entry)
    body = _body(await asyncio.wait_for(upload, 5))

    (marker,) = body["markers"]
    assert marker["waited_for_frame"] is True
    (case,) = coordinator.frame_log.markers()
    assert case["note"] == "Winter mode ON"
    assert case["photo"] == body["photo"]


@pytest.mark.asyncio
async def test_photo_with_wait_off_is_marked_at_once(tmp_path) -> None:
    hass, (entry,) = _setup(tmp_path)
    body = _body(
        await views.AsekoPhotoView().post(
            FakeRequest(hass, parts={"wait": b"0", "photo": _jpeg()})
        )
    )
    assert body["markers"][0]["waited_for_frame"] is None
    assert len(entry.runtime_data.coordinator.frame_log.markers()) == 1


@pytest.mark.asyncio
async def test_a_fragment_or_another_unit_does_not_release_the_wait(
    tmp_path,
) -> None:
    hass, (entry,) = _setup(tmp_path)
    coordinator = entry.runtime_data.coordinator
    _frame_arrives(entry)  # the unit is known to this entry
    upload = asyncio.ensure_future(
        views.AsekoPhotoView().post(
            FakeRequest(
                hass,
                parts={"serial_number": str(SERIAL).encode(), "photo": _jpeg()},
            )
        )
    )
    for _ in range(20):
        await asyncio.sleep(0)
    coordinator.store_raw_frame(bytes(_make_base_bytes())[:50])  # a fragment
    other = bytearray(_make_base_bytes())
    for start in (0, 40, 80):
        other[start : start + 4] = (9999).to_bytes(4, "big")
    coordinator.store_raw_frame(bytes(other))  # a whole frame, another unit
    coordinator.devices_update_callback(decode(bytes(other)))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not upload.done()

    _frame_arrives(entry)
    assert _body(await asyncio.wait_for(upload, 5))["markers"][0]["waited_for_frame"]


# ── photo file ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_photo_file_refuses_paths_and_unknown_names(tmp_path) -> None:
    hass, _ = _setup(tmp_path)
    view = views.AsekoPhotoFileView()
    assert (await view.get(FakeRequest(hass), "../secrets.yaml")).status == 400
    assert (await view.get(FakeRequest(hass), ".hidden.jpg")).status == 400
    assert (await view.get(FakeRequest(hass), "missing.jpg")).status == 404


@pytest.mark.asyncio
async def test_photo_file_serves_a_stored_photo(tmp_path) -> None:
    hass, _ = _setup(tmp_path)
    body = _body(
        await views.AsekoPhotoView().post(
            FakeRequest(hass, parts={"wait": b"false", "photo": _jpeg()})
        )
    )
    response = await views.AsekoPhotoFileView().get(FakeRequest(hass), body["photo"])
    assert Path(response._path).name == body["photo"]


# ── export, confirmation, clear list ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_marks_nothing_until_the_card_confirms(tmp_path) -> None:
    hass, entries = _setup(tmp_path, entries=2)
    for entry in entries:
        _frame_arrives(entry)
        entry.runtime_data.coordinator.mark_dump("one")
        entry.runtime_data.coordinator.mark_dump("two")

    response = await views.AsekoExportView().get(FakeRequest(hass, query={"new": "1"}))

    assert response.content_type == "application/zip"
    through = json.loads(response.headers[views.EXPORT_THROUGH_HEADER])
    assert through == {"entry0": 2, "entry1": 2}
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert archive.namelist()
    for entry in entries:  # the response may never arrive: nothing marked yet
        assert entry.runtime_data.coordinator.frame_log.not_downloaded() == 2

    confirmed = await views.AsekoExportedView().post(
        FakeRequest(hass, body={"through": {"entry0": 2}})
    )
    assert _body(confirmed) == {"marked": {"entry0": 2}}
    assert entries[0].runtime_data.coordinator.frame_log.not_downloaded() == 0
    assert entries[1].runtime_data.coordinator.frame_log.not_downloaded() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [ValueError("not json"), {}, {"through": 3}, {"through": {"e": "x"}}]
)
async def test_exported_refuses_a_malformed_confirmation(tmp_path, body) -> None:
    hass, _ = _setup(tmp_path)
    response = await views.AsekoExportedView().post(FakeRequest(hass, body=body))
    assert response.status == 400


@pytest.mark.asyncio
async def test_forget_clears_the_cases_but_keeps_frames_and_photos(tmp_path) -> None:
    hass, (entry,) = _setup(tmp_path)
    _frame_arrives(entry)
    await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"wait": b"0", "photo": _jpeg()})
    )
    coordinator = entry.runtime_data.coordinator

    await views.AsekoForgetView().post(FakeRequest(hass))

    assert coordinator.frame_log.markers() == []
    assert coordinator.frame_log.snapshot().records()
    assert len(PhotoStore(tmp_path / "photos").files()) == 1


# ── recording on / off, delete ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recording_is_switched_for_every_entry_and_shown_in_status(
    tmp_path,
) -> None:
    hass, entries = _setup(tmp_path, entries=2)
    view = views.AsekoRecordingView()

    assert _body(await view.post(FakeRequest(hass, body={"enabled": False}))) == {
        "enabled": False
    }
    status = _body(await views.AsekoStatusView().get(FakeRequest(hass)))
    assert [e["recording"] for e in status["entries"]] == [False, False]

    await view.post(FakeRequest(hass, body={"enabled": True}))
    assert all(e.runtime_data.coordinator.frame_log.enabled for e in entries)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [ValueError("not json"), {}, {"enabled": "yes"}])
async def test_recording_refuses_a_malformed_request(tmp_path, body) -> None:
    hass, _ = _setup(tmp_path)
    response = await views.AsekoRecordingView().post(FakeRequest(hass, body=body))
    assert response.status == 400


@pytest.mark.asyncio
async def test_no_photo_is_stored_while_recording_is_off(tmp_path) -> None:
    hass, (entry,) = _setup(tmp_path)
    entry.runtime_data.coordinator.set_recording(enabled=False)

    response = await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"wait": b"0", "photo": _jpeg()})
    )

    assert response.status == 409
    assert PhotoStore(tmp_path / "photos").files() == []


@pytest.mark.asyncio
async def test_delete_removes_frames_cases_and_photos_but_not_the_switch(
    tmp_path,
) -> None:
    hass, (entry,) = _setup(tmp_path)
    _frame_arrives(entry)
    await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"wait": b"0", "photo": _jpeg()})
    )
    coordinator = entry.runtime_data.coordinator

    body = _body(await views.AsekoDeleteRecordingView().post(FakeRequest(hass)))

    assert body == {"photos_deleted": 1}
    assert coordinator.frame_log.records() == []
    assert coordinator.frame_log.markers() == []
    assert PhotoStore(tmp_path / "photos").files() == []
    assert coordinator.frame_log.enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("view", "method"),
    [(views.AsekoRecordingView, "post"), (views.AsekoDeleteRecordingView, "post")],
)
async def test_switch_and_delete_are_admin_only(tmp_path, view, method) -> None:
    hass, _ = _setup(tmp_path)
    with pytest.raises(Unauthorized):
        await getattr(view(), method)(FakeRequest(hass, admin=False))


# ── audit N3: stop / delete while a photo waits; N7: the unit's own entry ───


async def _waiting_upload(hass: MagicMock) -> asyncio.Future:
    upload = asyncio.ensure_future(
        views.AsekoPhotoView().post(
            FakeRequest(
                hass,
                parts={"serial_number": str(SERIAL).encode(), "photo": _jpeg()},
            )
        )
    )
    for _ in range(20):
        await asyncio.sleep(0)
    assert not upload.done()
    return upload


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["stop", "delete"])
async def test_stopping_or_deleting_cancels_a_waiting_photo(tmp_path, action) -> None:
    hass, (entry,) = _setup(tmp_path)
    coordinator = entry.runtime_data.coordinator
    _frame_arrives(entry)
    upload = await _waiting_upload(hass)

    if action == "stop":
        await views.AsekoRecordingView().post(
            FakeRequest(hass, body={"enabled": False})
        )
        coordinator.set_recording(enabled=True)  # and on again before the frame comes
    else:
        await views.AsekoDeleteRecordingView().post(FakeRequest(hass))
    _frame_arrives(entry)
    response = await asyncio.wait_for(upload, 5)

    assert response.status == 409
    assert coordinator.frame_log.markers() == []  # no case from the old recording
    assert PhotoStore(tmp_path / "photos").files() == []  # and no stray photo


@pytest.mark.asyncio
async def test_a_photo_for_a_unit_waits_only_in_the_entry_that_knows_it(
    tmp_path,
) -> None:
    hass, (first, second) = _setup(tmp_path, entries=2)
    _frame_arrives(first)  # only the first entry receives the unit
    upload = await _waiting_upload(hass)

    _frame_arrives(first)
    body = _body(await asyncio.wait_for(upload, 5))

    assert [m["entry"] for m in body["markers"]] == ["Aseko 0"]
    assert body["markers"][0]["waited_for_frame"] is True
    assert second.runtime_data.coordinator.frame_log.markers() == []


@pytest.mark.asyncio
async def test_a_photo_for_a_unit_no_entry_has_seen_is_refused(tmp_path) -> None:
    hass, _ = _setup(tmp_path)
    response = await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"serial_number": b"4242", "photo": _jpeg()})
    )
    assert response.status == 409
    assert PhotoStore(tmp_path / "photos").files() == []


@pytest.mark.asyncio
async def test_a_case_keeps_its_unit_and_that_no_frame_came(
    tmp_path, monkeypatch
) -> None:
    """Audit A3: after a refresh the case still says which unit, and the timeout."""
    monkeypatch.setattr(coordinator_module, "MARK_DUMP_WAIT_TIMEOUT", 0.01)
    hass, (entry,) = _setup(tmp_path)
    _frame_arrives(entry)

    body = _body(
        await views.AsekoPhotoView().post(
            FakeRequest(
                hass, parts={"serial_number": str(SERIAL).encode(), "photo": _jpeg()}
            )
        )
    )
    assert body["markers"][0]["waited_for_frame"] is False

    coordinator = entry.runtime_data.coordinator
    restored = type(coordinator.frame_log)()
    restored.load_store(coordinator.frame_log.to_store())
    (case,) = restored.markers()
    assert case["serial_number"] == SERIAL
    assert case["waited_for_frame"] is False


@pytest.mark.asyncio
async def test_a_case_without_waiting_stores_no_wait_result(tmp_path) -> None:
    hass, (entry,) = _setup(tmp_path)
    await views.AsekoPhotoView().post(
        FakeRequest(hass, parts={"wait": b"0", "photo": _jpeg()})
    )
    (case,) = entry.runtime_data.coordinator.frame_log.markers()
    assert "waited_for_frame" not in case
    assert "serial_number" not in case
