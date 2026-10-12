"""Set-up, unload and set-up again of real config entries (audit R1).

The TCP listener is the only stand-in: the ``listeners`` fixture (conftest)
makes ``asyncio.start_server`` return a server object that reports whether it
was closed, so the tests see exactly what the integration's own ``running``
check sees.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aseko_local import async_setup_entry, async_unload_entry
from custom_components.aseko_local.config_flow import _remove_entry_server
from custom_components.aseko_local.const import DOMAIN
from custom_components.aseko_local.server import AsekoDeviceServer


def _entry(hass, entry_id: str, port: int) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port},
        entry_id=entry_id,
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)
    return entry


def _server(port: int) -> AsekoDeviceServer | None:
    return AsekoDeviceServer._instances.get(f"127.0.0.1:{port}")


async def test_setup_unload_setup_on_the_same_port_listens_again(
    hass, listeners
) -> None:
    await AsekoDeviceServer.remove_all()
    entry = _entry(hass, "one", 12401)

    assert await async_setup_entry(hass, entry)
    assert _server(12401).running

    assert await async_unload_entry(hass, entry)
    assert _server(12401) is None  # removed, not left stopped in the registry
    assert listeners[0][1].closed

    assert await async_setup_entry(hass, entry)
    assert _server(12401).running
    assert len(listeners) == 2  # a new listener, not the stopped one

    assert await async_unload_entry(hass, entry)


async def test_unloading_one_entry_leaves_the_other_listening(hass, listeners) -> None:
    await AsekoDeviceServer.remove_all()
    first = _entry(hass, "first", 12402)
    second = _entry(hass, "second", 12403)
    assert await async_setup_entry(hass, first)
    assert await async_setup_entry(hass, second)

    assert await async_unload_entry(hass, first)

    assert _server(12402) is None
    assert _server(12403).running
    assert second.runtime_data.server.running

    assert await async_unload_entry(hass, second)


async def test_changing_one_entrys_options_stops_only_its_server(
    hass, listeners
) -> None:
    await AsekoDeviceServer.remove_all()
    first = _entry(hass, "first", 12404)
    second = _entry(hass, "second", 12405)
    assert await async_setup_entry(hass, first)
    assert await async_setup_entry(hass, second)

    await _remove_entry_server(first)  # what the options flow does before reload

    assert _server(12404) is None
    assert _server(12405).running

    assert await async_unload_entry(hass, first)
    assert await async_unload_entry(hass, second)
