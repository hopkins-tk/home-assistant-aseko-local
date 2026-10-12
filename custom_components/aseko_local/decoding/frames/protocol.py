"""The two wire formats an Aseko unit can speak, and how to tell them apart."""

from __future__ import annotations

from enum import Enum


class Protocol(Enum):
    """The two wire formats an Aseko unit can speak."""

    V7 = "v7"  # 120-byte binary frame, firmware <= 7.x, port 47524
    V8 = "v8"  # text frame starting with "{v1 ", firmware 8.x, port 51050


# Signature that opens every v8 text frame.
V8_SIGNATURE = b"{v1 "
