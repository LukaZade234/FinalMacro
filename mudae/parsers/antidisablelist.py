"""Parse a page of Mudae's antidisablelist (``$adl``).

::

    author:      lukazade234's Antidisablelist (4/500)
    description: **134** antidisabled characters

                 **Cyberpunk: Edgerunners**
                 **Lord of Mysteries 2: Circle of Inevitability**
                 **Lord of the Mysteries**
                 **Omniscient Reader's Viewpoint**

The header counts **series** (4 of 500 slots); the first line counts the
characters those series bring back (134). Every other line is one series, kept
in Mudae's order. The captured reply had no footer, but a long list is paged
the same way as ``$dl``, so the footer is read when it is there.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.listing_pages import match_page, merge_listing_pages, strip_bold, to_int
from mudae.types import MessageKind, ParseResult

_HEADER_RE = re.compile(
    r"^(?P<owner>.+?)'s\s+Anti\s*disable\s*list\s*\(\s*(?P<used>[\d,]+)\s*/\s*(?P<max>[\d,]+)\s*\)",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"^(?P<n>[\d,]+)\s+antidisabled\s+characters?\b", re.IGNORECASE)
_BOLD_ROW_RE = re.compile(r"^\*\*(?P<name>[^*]+?)\*\*\s*$")


def is_antidisablelist_message(content: str) -> bool:
    for raw in (content or "").splitlines():
        line = strip_bold(raw).strip()
        if _HEADER_RE.match(line) or _COUNT_RE.match(line):
            return True
    return False


def parse_antidisablelist_page(content: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "owner": None,
        "used": None,
        "max": None,
        "characters": None,
        "entries": [],
        "page": None,
        "pages": None,
    }
    for raw in (content or "").splitlines():
        raw_line = raw.strip()
        if not raw_line:
            continue
        line = strip_bold(raw_line).strip()
        header = _HEADER_RE.match(line)
        if header:
            fields["owner"] = header.group("owner").strip()
            fields["used"] = to_int(header.group("used"))
            fields["max"] = to_int(header.group("max"))
            continue
        page = match_page(line)
        if page:
            fields["page"], fields["pages"] = page
            continue
        count = _COUNT_RE.match(line)
        if count:
            fields["characters"] = to_int(count.group("n"))
            continue
        row = _BOLD_ROW_RE.match(raw_line)
        name = row.group("name").strip() if row else line
        if name:
            fields["entries"].append(name)
    return fields


def merge_antidisablelist_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    merged = merge_listing_pages(pages, scalar_keys=("owner", "used", "max", "characters"))
    used = merged.get("used")
    merged["count_matches"] = used is not None and used == len(merged["entries"])
    return merged


def parse_antidisablelist(content: str) -> ParseResult:
    fields = parse_antidisablelist_page(content)
    bits = [f"{len(fields['entries'])} series"]
    if fields["characters"] is not None:
        bits.append(f"{fields['characters']} characters")
    if fields["used"] is not None:
        bits.append(f"{fields['used']}/{fields['max']}")
    return ParseResult(
        kind=MessageKind.ANTIDISABLELIST,
        summary="$adl · " + " · ".join(bits),
        fields=fields,
        warnings=[],
    )
