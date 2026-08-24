"""Shared parsing helpers."""

from __future__ import annotations

import re
from typing import Match

_NON_DIGIT_RE = re.compile(r"\D")
_BOLD_HM_MIN_RE = re.compile(r"\*\*(\d+)h\s*(\d+)\*\*\s*min", re.IGNORECASE)
_BOLD_MIN_RE = re.compile(r"\*\*(\d+)\*\*\s*min", re.IGNORECASE)


def parse_hours_minutes(match: Match[str] | None) -> tuple[int, int]:
    if not match:
        return 0, 0
    groups = match.groups()
    h_str = groups[0] if len(groups) > 0 else ""
    m_str = groups[1] if len(groups) > 1 else ""
    h = int(_NON_DIGIT_RE.sub("", h_str or "0") or "0")
    m = int(_NON_DIGIT_RE.sub("", m_str or "0") or "0")
    return h, m


def extract_bold_minutes(text: str, *, start: int = 0, window: int = 72) -> int | None:
    """Parse **26** min or **8h 37** min starting at `start` in `text`.

    When several bold durations appear in the window (e.g. rolls reset then
    ``$daily`` reset on the next line), return the *first* one — not a later
    ``**7h 57** min`` that would otherwise win the hours pattern.
    """
    chunk = text[start : start + window]
    best_pos: int | None = None
    best_minutes: int | None = None

    def consider(pos: int, minutes: int) -> None:
        nonlocal best_pos, best_minutes
        if best_pos is None or pos < best_pos:
            best_pos = pos
            best_minutes = minutes

    for match in _BOLD_HM_MIN_RE.finditer(chunk):
        consider(match.start(), int(match.group(1)) * 60 + int(match.group(2)))

    for match in _BOLD_MIN_RE.finditer(chunk):
        consider(match.start(), int(match.group(1)))

    return best_minutes


def strip_markdown(text: str) -> str:
    return (
        text.replace("**", "")
        .replace("__", "")
        .replace("~~", "")
        .replace("*", "")
    )


_DISCORD_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")


def strip_discord_emojis(text: str) -> str:
    """Remove <:name:id> and <a:name:id> tokens from text."""
    return _DISCORD_EMOJI_RE.sub("", text).strip()
