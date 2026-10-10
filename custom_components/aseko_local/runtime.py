"""The config entries of this integration that are set up and running.

Shared by the domain services and the recording views: both act on every
running entry.  Running means Home Assistant finished setting it up
(``ConfigEntryState.LOADED``): ``runtime_data`` is put in place early in the
set-up, before the stores are loaded and the server listens, and stays on an
entry whose set-up failed and waits for a retry, so on its own it is no sign
of a running entry.  A module of its own so the views need not import the
package ``__init__``, which imports them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import AsekoLocalConfigEntry


def loaded_entries(hass: HomeAssistant) -> list[AsekoLocalConfigEntry]:
    """Return every Aseko Local entry that is loaded and has its runtime data."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and getattr(entry, "runtime_data", None)
    ]
