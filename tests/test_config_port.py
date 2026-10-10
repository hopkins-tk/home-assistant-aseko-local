"""The port a user picks from the list or types in the config flow."""

import pytest

from custom_components.aseko_local.config_flow import parse_port


@pytest.mark.parametrize(
    ("value", "port"),
    [("47524", 47524), ("51050", 51050), (" 12345 ", 12345), (8080, 8080)],
)
def test_a_picked_or_typed_port_becomes_a_number(value, port) -> None:
    assert parse_port(value) == port


@pytest.mark.parametrize("value", ["", "abc", "0", "65536", "-1"])
def test_anything_else_is_refused(value) -> None:
    with pytest.raises(ValueError, match=r"invalid literal|out of range"):
        parse_port(value)
