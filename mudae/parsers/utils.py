"""Shared parsing helpers."""

from __future__ import annotations

import re
from typing import Match


def parse_hours_minutes(match: Match[str] | None) -> tuple[int, int]:
    if not match:
        return 0, 0
    groups = match.groups()
    h_str = groups[0] if len(groups) > 0 else ""
    m_str = groups[1] if len(groups) > 1 else ""
    h = int(re.sub(r"\D", "", h_str or "0") or "0")
    m = int(re.sub(r"\D", "", m_str or "0") or "0")
    return h, m


def extract_bold_minutes(text: str, *, start: int = 0, window: int = 72) -> int | None:
    """Parse **26** min or **8h 37** min starting at `start` in `text`."""
    chunk = text[start : start + window]
    hours_min = re.search(r"\*\*(\d+)h\s*(\d+)\*\*\s*min", chunk, re.IGNORECASE)
    if hours_min:
        return int(hours_min.group(1)) * 60 + int(hours_min.group(2))
    minutes_only = re.search(r"\*\*(\d+)\*\*\s*min", chunk, re.IGNORECASE)
    if minutes_only:
        return int(minutes_only.group(1))
    return None


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
