"""Parse Mudae's server disablelist (``$sdl``, ``$sdls`` by DM).

The server disablelist disables up to 1,000 more characters for the whole
server and overrides the ``$limroul`` pool floor (2,000 → 1,000). ``$sdl``
lists it 15 characters a page — up to 67 pages — so ``$sdls``, which mails the
whole list as several DMs, is the better route::

    Disabled characters for this server ($sdl) (1,000/1,000)
    1,000 disabled

    'Her' 💞 - Veil
    「Shiki Ryougi」 💞 - Kara no Kyoukai: The Garden of Sinners
    Abra - Pokédex
    Awesome Face -
    …
    Page 1 / 67          (channel only)

An empty list answers ``$sdl`` with one line, in the channel::

    List empty! ($serverdisable)

``💞`` only says the character is claimed and is dropped. `` - `` ends the name
and starts the series; only the **name** is kept, cut at the first `` - `` (a
series can contain one, a name rarely does). Later DM parts carry no header.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.listing_pages import match_page, merge_listing_pages, strip_bold, to_int
from mudae.types import MessageKind, ParseResult

_HEADER_RE = re.compile(
    r"disabled\s+characters\s+for\s+this\s+server\s*\(\s*\$sdl\s*\)\s*"
    r"\(\s*(?P<used>[\d,]+)\s*/\s*(?P<max>[\d,]+)\s*\)",
    re.IGNORECASE,
)
_EMPTY_RE = re.compile(r"list\s+empty!?\s*\(\s*\$serverdisable\s*\)", re.IGNORECASE)
_COUNT_RE = re.compile(r"^(?P<n>[\d,]+)\s+disabled\s*$", re.IGNORECASE)
# "<name> [💞] - <series>" — the series may be empty ("Awesome Face - ").
_ROW_RE = re.compile(r"^(?P<name>.+?)\s+-(?:\s+(?P<series>.*))?$")
# Marks that can follow a name and are not part of it.
_NAME_MARKS_RE = re.compile(r"[\U0001f49e❤️]+")


def is_sdl_empty(content: str) -> bool:
    """Mudae's answer to ``$sdl`` when the server disablelist is empty."""
    return bool(_EMPTY_RE.search(strip_bold(content or "")))


def is_serverdisablelist_message(content: str) -> bool:
    """A page, a first DM part, or the empty answer — keyed on the header."""
    text = strip_bold(content or "")
    return bool(_HEADER_RE.search(text)) or is_sdl_empty(text)


def parse_sdl_row(line: str) -> str | None:
    """The character name on one row, or ``None`` when the line is not one."""
    clean = strip_bold(line).strip()
    if not clean or _HEADER_RE.search(clean) or _COUNT_RE.match(clean) or match_page(clean):
        return None
    match = _ROW_RE.match(clean)
    if not match:
        return None
    name = " ".join(_NAME_MARKS_RE.sub("", match.group("name")).split())
    return name or None


def parse_sdl_page(content: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "used": None,
        "max": None,
        "total": None,
        "entries": [],
        "page": None,
        "pages": None,
        "empty": is_sdl_empty(content),
    }
    if fields["empty"]:
        fields.update(used=0, total=0)
        return fields
    for raw in (content or "").splitlines():
        line = strip_bold(raw).strip()
        if not line:
            continue
        header = _HEADER_RE.search(line)
        if header:
            fields["used"] = to_int(header.group("used"))
            fields["max"] = to_int(header.group("max"))
            continue
        count = _COUNT_RE.match(line)
        if count:
            fields["total"] = to_int(count.group("n"))
            continue
        page = match_page(line)
        if page:
            fields["page"], fields["pages"] = page
            continue
        name = parse_sdl_row(line)
        if name:
            fields["entries"].append(name)
    return fields


def merge_sdl_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Join pages or DM parts.

    The DM has no page footer, so there ``complete`` comes from the count: as
    many names as the header says are disabled.
    """
    merged = merge_listing_pages(pages, scalar_keys=("used", "max", "total"))
    merged["empty"] = any(page.get("empty") for page in pages)
    expected = merged.get("used") if merged.get("used") is not None else merged.get("total")
    if not merged.get("pages") and expected is not None:
        merged["complete"] = len(merged["entries"]) >= int(expected)
    merged["count_matches"] = expected is not None and len(merged["entries"]) == int(expected)
    return merged


def parse_serverdisablelist(content: str) -> ParseResult:
    fields = parse_sdl_page(content)
    if fields["empty"]:
        return ParseResult(
            kind=MessageKind.SERVERDISABLELIST, summary="$sdl · empty", fields=fields, warnings=[]
        )
    bits = [f"{len(fields['entries'])} characters"]
    if fields["used"] is not None:
        bits.append(f"{fields['used']}/{fields['max']}")
    if fields["page"] is not None:
        bits.append(f"page {fields['page']}/{fields['pages']}")
    return ParseResult(
        kind=MessageKind.SERVERDISABLELIST,
        summary="$sdl · " + " · ".join(bits),
        fields=fields,
        warnings=[],
    )
