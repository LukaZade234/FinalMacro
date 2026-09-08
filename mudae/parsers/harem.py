"""Parse a page of Mudae's harem listing (``$mm``, ``$mmk``, …).

``$mmk=`` sorts the harem by kakera value, highest first, which is the one
thing the force-divorce farm needs: the top row of page 1 is the most valuable
character the account owns, and re-claiming that character is what the farm
banks over and over.

The page is an **embed**, not plain text::

    author:      lukazade234's harem
    description: ​
                 Total value: **4,865,155**<:kakera:469835869059153940>

                 Lucy **271,065** ka
                 Reze **125,670** ka
                 ...
    footer:      Page 1 / 155

Two reasons this module exists beyond reading the top name. Mudae sends the
same shape for every ``$mm*`` spelling, and — more importantly — an unrecognised
listing is a *roll* to the rest of the app: ``detect_command_from_snapshot``
answers ``"roll"`` for anything with a character-shaped embed, so before the
``mmk`` alias existed this page parsed as a claimable character worth
4,865,155 kakera, with the page arrows typed as claim buttons. That is the
exact failure the ``$wl`` listing hit first; see ``mudae/commands.py``.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

# The embed author, and the only line that names the owner: "X's harem".
# Mudae uses the same wording for every sort flag.
_HEADER_RE = re.compile(r"^(?P<owner>.+?)'s\s+harem\b", re.IGNORECASE)

# "Total value: 4,865,155" once bold is stripped.
_TOTAL_RE = re.compile(r"total\s+value\s*:\s*(?P<total>[\d,]+)", re.IGNORECASE)

# "Page 1 / 155" — the footer, same shape as the wishlist listing's.
_PAGE_RE = re.compile(r"^Page\s+(?P<page>\d+)\s*/\s*(?P<pages>\d+)\s*$", re.IGNORECASE)

# One character: "Lucy 271,065 ka" once bold is stripped. Anchored on the
# trailing " ka" so a roll card's kakera line cannot be mistaken for a row.
_ROW_RE = re.compile(r"^(?P<name>\S.*?)\s+(?P<kakera>[\d,]+)\s*ka\s*$")


def _int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(str(raw).replace(",", ""))
    except ValueError:
        return None


def _clean_lines(content: str) -> list[str]:
    # A zero-width space leads the description, and Mudae pads with blank
    # lines between the total and the first character.
    return [line.strip().strip("​").strip() for line in (content or "").splitlines()]


def is_harem_message(content: str) -> bool:
    """True for any page of a harem listing.

    Deliberately anchored on the header or the total rather than on rows
    alone: a bare ``Name 12,345 ka`` line is a shape other Mudae output could
    wander into, while ``X's harem`` and ``Total value:`` are this listing's
    own.
    """
    text = strip_markdown(content or "")
    for line in _clean_lines(text):
        if _HEADER_RE.match(line) or _TOTAL_RE.search(line):
            return True
    return False


def parse_harem_page(content: str) -> dict[str, Any]:
    """Owner, total, page numbers and every character row on one message."""
    fields: dict[str, Any] = {
        "owner": None,
        "total_value": None,
        "page": None,
        "pages": None,
        "entries": [],
        "top_name": None,
        "top_kakera": None,
    }
    text = strip_markdown(content or "")
    for line in _clean_lines(text):
        if not line:
            continue
        if fields["owner"] is None:
            header = _HEADER_RE.match(line)
            if header:
                fields["owner"] = header.group("owner").strip()
                continue
        if fields["total_value"] is None:
            total = _TOTAL_RE.search(line)
            if total:
                fields["total_value"] = _int(total.group("total"))
                continue
        page = _PAGE_RE.match(line)
        if page:
            fields["page"] = _int(page.group("page"))
            fields["pages"] = _int(page.group("pages"))
            continue
        row = _ROW_RE.match(line)
        if row:
            name = row.group("name").strip()
            value = _int(row.group("kakera"))
            if name and value is not None:
                fields["entries"].append({"name": name, "kakera": value})

    if fields["entries"]:
        fields["top_name"] = fields["entries"][0]["name"]
        fields["top_kakera"] = fields["entries"][0]["kakera"]
    return fields


def parse_harem(content: str) -> ParseResult:
    fields = parse_harem_page(content)
    warnings: list[str] = []
    if not fields["entries"]:
        warnings.append("No harem rows found")

    owner = fields["owner"] or "?"
    summary = f"Harem · {owner}"
    if fields["page"] is not None:
        summary += f" · page {fields['page']}/{fields['pages']}"
    if fields["top_name"]:
        summary += f" · top {fields['top_name']} ({fields['top_kakera']:,} ka)"
    return ParseResult(
        kind=MessageKind.HAREM,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
