"""Extract Mudae character names from pasted list text."""

from __future__ import annotations

import re

# Split before each list entry (#rank or points-rank style).
# The points branch must not match rank digits inside "#10 - …".
_ENTRY_SPLIT = re.compile(r"(?=#\d+\s*-\s*|(?<![#\d])\d+\s*-\s*)")

# Per-entry name extractors (first match wins).
_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    # #1 - Name · ($wa) · stats…
    re.compile(r"#\d+\s*-\s*(.+?)\s*[·•]", re.UNICODE),
    # 82 - Name ~ Series#1 -
    re.compile(r"^\d+\s*-\s*(.+?)\s*~\s*.+", re.UNICODE),
    # #1 - Name 💞? - Series
    re.compile(r"#\d+\s*-\s*(.+?)(?:\s*💞)?\s*-\s*", re.UNICODE),
    # #1 - Name (trailing metadata / end of chunk)
    re.compile(r"#\d+\s*-\s*(.+?)(?:\s*[·•-]|$)", re.UNICODE),
)

_SKIP_LINES = frozenset({"image"})


def _clean_name(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"\s*💞\s*$", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _split_entries(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    entries: list[str] = []
    for line in normalized.split("\n"):
        line = line.strip()
        if not line or line.lower() in _SKIP_LINES:
            continue
        for chunk in _ENTRY_SPLIT.split(line):
            chunk = chunk.strip()
            if chunk and chunk.lower() not in _SKIP_LINES:
                entries.append(chunk)
    return entries


def _extract_name(entry: str) -> str | None:
    for pattern in _NAME_PATTERNS:
        match = pattern.search(entry)
        if not match:
            continue
        name = _clean_name(match.group(1))
        if name:
            return name
    return None


def extract_character_names(text: str) -> list[str]:
    """Return character names found in Mudae list text, in source order."""
    if not text or not text.strip():
        return []

    names: list[str] = []
    seen: set[str] = set()
    for entry in _split_entries(text):
        name = _extract_name(entry)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def format_mudae_character_list(text: str) -> str:
    """Join extracted character names with ``$`` for Mudae command input."""
    return "$".join(extract_character_names(text))
