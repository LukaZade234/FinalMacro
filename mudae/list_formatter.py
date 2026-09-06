"""Extract Mudae character names from pasted list text.

Two shapes of input, told apart by whether anything in the text carries a
**rank marker** (``#12 - `` or ``82 - ``):

* A *Mudae listing* — ``$wl``, ``$top``, a kakera ranking — where each entry is
  a rank, a name and a tail of series and stats. The patterns below strip that
  tail, and lines with no rank at all are chrome ("Image", a page header) and
  are dropped.
* A *plain list of names*, one per line, which is what you have when you are
  building a list rather than pasting one back. Nothing to strip: every line is
  a name. This is split the way :func:`macro.wishlist.parse_wishlist_input`
  splits the wishlist boxes — on ``$``, commas and newlines — so the formatter's
  own output pastes back into itself and into those boxes unchanged.

The two are never mixed. If any rank marker is present the text is a listing,
and bare lines in it stay chrome; the fallback would otherwise turn a listing's
header into a character.
"""

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

# What tells a Mudae listing apart from a plain list of names. Same alternation
# ``_ENTRY_SPLIT`` looks ahead for, so the two agree on what counts as an entry.
_RANK_MARKER = re.compile(r"#\d+\s*-\s*|(?<![#\d])\d+\s*-\s*")

# A plain list's separators, matching ``macro.wishlist.parse_wishlist_input``.
_PLAIN_SPLIT = re.compile(r"[$,\n\r]+")


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


def _plain_names(text: str) -> list[str]:
    """Every non-blank chunk of a plain list, as a name."""
    out: list[str] = []
    for chunk in _PLAIN_SPLIT.split(text):
        name = _clean_name(chunk)
        if name and name.lower() not in _SKIP_LINES:
            out.append(name)
    return out


def extract_character_names(text: str) -> list[str]:
    """Return character names found in the pasted text, in source order.

    Handles a Mudae listing and a plain list of names — see the module
    docstring for how the two are told apart.
    """
    if not text or not text.strip():
        return []

    if _RANK_MARKER.search(text):
        found = [
            name
            for name in (_extract_name(entry) for entry in _split_entries(text))
            if name
        ]
    else:
        found = _plain_names(text)

    names: list[str] = []
    seen: set[str] = set()
    for name in found:
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def format_mudae_character_list(text: str) -> str:
    """Join extracted character names with ``$`` for Mudae command input."""
    return "$".join(extract_character_names(text))
