"""The writable last scheduled backwash: platform set-up and the entity itself."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.aseko_local import datetime as datetime_module
from custom_components.aseko_local import entity as entity_module
from custom_components.aseko_local.coordinator import AsekoLocalDataUpdateCoordinator
from custom_components.aseko_local.datetime import (
    LAST_SCHEDULED_BACKWASH,
    AsekoLastScheduledBackwashEntity,
)
from custom_components.aseko_local.decoding import decode
from custom_components.aseko_local.models import AsekoDevice

from .test_entity_growth import SERIAL, _coordinator, _loaded, _salt_frame


def _coordinator_with_salt() -> AsekoLocalDataUpdateCoordinator:
    coordinator = _coordinator()
    coordinator.config_entry.options = {}
    coordinator.devices_update_callback(decode(_salt_frame(0xD3)))
    return _loaded(coordinator)


def _entity(coordinator) -> AsekoLastScheduledBackwashEntity:
    return AsekoLastScheduledBackwashEntity(
        coordinator.get_device(SERIAL), coordinator, LAST_SCHEDULED_BACKWASH
    )


@pytest.mark.asyncio
async def test_setup_adds_entities_now_and_for_devices_seen_later(monkeypatch) -> None:
    enabled: list[list[str]] = []
    monkeypatch.setattr(
        entity_module,
        "async_enable_entities",
        lambda hass, platform, unique_ids: enabled.append(list(unique_ids)),
    )
    coordinator = _coordinator_with_salt()
    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    added: list[AsekoLastScheduledBackwashEntity] = []

    await datetime_module.async_setup_entry(MagicMock(), entry, added.extend)

    assert [e.unique_id for e in added] == [f"{SERIAL}last_scheduled_backwash"]
    assert entry.async_on_unload.call_count == 2
    (new_device,) = coordinator._new_device_listeners
    (new_features,) = coordinator._new_features_listeners

    # a unit without a backwash valve adds nothing
    new_device(AsekoDevice(serial_number=42))
    assert len(added) == 1

    other = decode(_salt_frame(0xD3))
    other.serial_number = 5678
    new_device(other)
    assert [e.unique_id for e in added][1:] == ["5678last_scheduled_backwash"]

    # the valve showing up on a known unit enables the entity created disabled
    enabled.clear()
    new_features(other, frozenset({"ph"}))
    new_features(other, frozenset({"backwash_running"}))
    assert enabled == [[], ["5678last_scheduled_backwash"]]


def test_the_value_and_its_source_follow_the_device() -> None:
    coordinator = _coordinator_with_salt()
    entity = _entity(coordinator)
    assert entity.native_value is None
    assert entity.extra_state_attributes is None  # no source for no value

    moment = dt_util.now() - timedelta(days=2)
    coordinator.set_last_scheduled_backwash(moment, SERIAL)
    assert entity.native_value == moment
    assert entity.extra_state_attributes == {"source": "manual"}


@pytest.mark.asyncio
async def test_setting_a_past_date_records_it() -> None:
    coordinator = _coordinator_with_salt()
    entity = _entity(coordinator)
    # judged on the unit's clock, which the test frame sets far in the past
    unit_now = coordinator.unit_clock_now(SERIAL)
    assert unit_now < dt_util.now() - timedelta(days=1)
    moment = unit_now - timedelta(days=1)

    await entity.async_set_value(moment)

    assert coordinator.get_device(SERIAL).last_scheduled_backwash == moment


@pytest.mark.asyncio
async def test_a_date_in_the_future_is_refused() -> None:
    coordinator = _coordinator_with_salt()
    entity = _entity(coordinator)

    # an hour ago for Home Assistant is still ahead of this unit's clock
    with pytest.raises(ServiceValidationError, match="is in the future"):
        await entity.async_set_value(dt_util.now() - timedelta(hours=1))
    assert coordinator.get_device(SERIAL).last_scheduled_backwash is None


@pytest.mark.asyncio
async def test_without_a_unit_clock_any_date_is_passed_on() -> None:
    coordinator = _coordinator()  # no tracker for this unit: no clock to judge by
    device = decode(_salt_frame(0xD3))
    entity = AsekoLastScheduledBackwashEntity(
        device, coordinator, LAST_SCHEDULED_BACKWASH
    )
    passed: list[tuple] = []
    coordinator.set_last_scheduled_backwash = lambda *args: passed.append(args)

    future = dt_util.now() + timedelta(days=1)
    await entity.async_set_value(future)

    assert passed == [(future, SERIAL)]
