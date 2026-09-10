"""Process-wide pause switch, flipped by the owner from Telegram."""

from __future__ import annotations

_paused = False


def is_paused() -> bool:
    return _paused


def set_paused(value: bool) -> None:
    global _paused
    _paused = value
