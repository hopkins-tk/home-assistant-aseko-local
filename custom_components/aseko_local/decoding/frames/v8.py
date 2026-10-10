"""v8: the text frame, firmware 8.x.

A ``V8Frame`` wraps the frame's parsed sections; features read individual
values off it and never touch the transport again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...const import UNSPECIFIED_V8
from ..presence import NOT_PRESENT, NotPresent
from .protocol import Protocol

# The sections the features read; a frame without one of them is reported.
EXPECTED_SECTIONS = ("ins", "ains", "outs", "areqs")
# Every section a v8 frame is known to carry.  A problem in any other section
# is reported once per frame without its name, so an odd stream cannot make
# a new kind of problem with every frame.
KNOWN_SECTIONS = (*EXPECTED_SECTIONS, "reqs", "fncs", "mods", "flags", "crc16")

# ``fncs[6]`` names the chemical the third pump port is set up for: the same
# unit read 10 with algicide configured and 18 after it was switched to
# flocculant (Issue #131, 2026-07-19).
THIRD_PUMP_ALGICIDE = 10
THIRD_PUMP_FLOCCULANT = 18
THIRD_PUMP_SECTION = "fncs"
THIRD_PUMP_INDEX = 6

# Matches "sectionname: <values>" up to the next section keyword or the end.
_SECTION_RE = re.compile(r"(\w+):\s*(.*?)(?=\s+\w+:|$)", re.DOTALL)
_HEADER_RE = re.compile(r"v1\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)")


@dataclass(frozen=True)
class V8Frame:
    """Read-only view over a parsed v8 text frame.

    Frame format::

        {v1 <serial> <f2> <f3> <f4>
         ins: <i0> <i1> ... <iN>
         ains: <a0> <a1> ... <aN>
         outs: <o0> <o1> ... <oN>
         areqs: <r0> <r1> ... <rN>
         reqs: ...
         fncs: ...
         mods: ...
         flags: ...
         crc16: XXXX}

    ``get(section, i)`` returns the integer at ``i`` or None when the section
    is shorter; ``value(section, i)`` additionally maps the ``-500`` sentinel
    (absent / unreadable probe) to None.
    """

    raw: bytes
    serial_number: int
    header_type: int
    sections: dict[str, list[int | None]]
    #: What the parser could not read, e.g. ``ains[3]: 'x7' is not a number``.
    #: The value at that position is None; the rest of the section stands.
    problems: tuple[str, ...] = ()
    protocol: Protocol = field(default=Protocol.V8, init=False)

    def get(self, section: str, index: int) -> int | None:
        """Return ``sections[section][index]``, or None if out of range or unreadable."""
        values = self.sections.get(section, [])
        return values[index] if index < len(values) else None

    def unspecified(self, section: str, index: int) -> bool:
        """Return True when the unit sent the -500 "not fitted / not measured" marker."""
        return self.get(section, index) == UNSPECIFIED_V8

    def value(self, section: str, index: int) -> int | None:
        """Like ``get`` but also None for the v8 sentinel (-500)."""
        v = self.get(section, index)
        return None if v is None or v == UNSPECIFIED_V8 else v

    def flag(self, section: str, index: int) -> bool | None:
        """Return ``get`` as a bool (non-zero is on), or None when it is unreadable or not sent."""
        v = self.get(section, index)
        return None if v is None else bool(v)

    def third_pump_is(self, chemical: int) -> bool | None:
        """Whether the third pump port is set up for ``chemical`` (``fncs[6]``).

        None while the unit did not send the section, so a reading can tell
        "another chemical" from "not said".
        """
        code = self.get(THIRD_PUMP_SECTION, THIRD_PUMP_INDEX)
        return None if code is None else code == chemical

    def measurement(
        self, section: str, index: int, divisor: int
    ) -> float | NotPresent | None:
        """Return the value divided by ``divisor``.

        NOT_PRESENT for -500, which marks a probe that is not fitted; None
        when the value is unreadable or not sent.
        """
        if self.unspecified(section, index):
            return NOT_PRESENT
        v = self.value(section, index)
        return None if v is None else v / divisor


@dataclass(frozen=True)
class V8Section:
    """One ``name: values`` part of a v8 frame as the parser read it."""

    name: str
    text: str
    #: None where a token is not a number
    values: list[int | None]
    #: indexes of the tokens that are not numbers
    unreadable: tuple[int, ...]


def parse_v8_sections(body: str) -> list[V8Section]:
    """Every section of a v8 frame body, header excluded.

    ``crc16`` is hexadecimal, every other section decimal.  One unreadable
    token reads None and leaves the rest of its section standing.  Shared by
    the decoder and the diagnostics download, so both read a frame alike.
    """
    sections: list[V8Section] = []
    for m in _SECTION_RE.finditer(body):
        name = m.group(1)
        if name == "v1":
            continue  # header
        base = 16 if name == "crc16" else 10
        values: list[int | None] = []
        unreadable: list[int] = []
        for index, token in enumerate(m.group(2).split()):
            try:
                values.append(int(token, base))
            except ValueError:
                values.append(None)
                unreadable.append(index)
        sections.append(V8Section(name, m.group(2).strip(), values, tuple(unreadable)))
    return sections


def parse_v8(raw: bytes) -> V8Frame:
    """Parse a v8 text frame.  Raises ValueError if it cannot be parsed."""
    try:
        text = raw.decode("ascii", errors="replace").strip()
    except Exception as exc:
        msg = f"v8 frame is not ASCII: {exc}"
        raise ValueError(msg) from exc

    if not text.startswith("{") or not text.endswith("}"):
        msg = f"v8 frame missing braces: {text[:40]!r}"
        raise ValueError(msg)
    body = text[1:-1].strip()

    header_match = _HEADER_RE.match(body)
    if not header_match:
        msg = f"v8 frame header not recognised: {body[:60]!r}"
        raise ValueError(msg)
    serial_number = int(header_match.group(1))
    header_type = int(header_match.group(2))

    sections: dict[str, list[int | None]] = {}
    problems: list[str] = []
    unexpected = False
    for section in parse_v8_sections(body):
        name = section.name
        if name not in KNOWN_SECTIONS:
            unexpected = True
        elif section.unreadable:
            # the place only: a changing bad token must not make a new kind
            # of problem every frame (the raw frame keeps the token)
            problems.extend(f"{name}[{i}] is not a number" for i in section.unreadable)
        sections[name] = section.values
    if unexpected:
        problems.append("unexpected section")
    problems.extend(
        f"section {name!r} is missing"
        for name in EXPECTED_SECTIONS
        if name not in sections
    )

    return V8Frame(
        raw=bytes(raw),
        serial_number=serial_number,
        header_type=header_type,
        sections=sections,
        problems=tuple(problems),
    )
