"""Parse a page of Mudae's disablelist (``$dl`` / ``$dld``).

The reply is an embed, paged with the usual ``wleft``/``wright`` arrows::

    author:      lukazade234's Disablelist (42/62)
    description: **133,775** disabled (45,920 $wa, 47,768 $ha, 30,870 $wg, 25,315 $hg)
                 **Pool limits:** 46,309 $wa, 47,739 $ha, 34,887 $wg, 29,960 $hg

                 Can't be reduced below **3,052** characters available for …
                 ⚠️ Pool limit reached: **47,739 $ha** (series above this limit are not disabled)

                 **Western animanga series are completely disabled** ($togglewestern)

                 **Kadokawa Corporation** (13,449 ~ 8,300 $wa, 4,203 $ha, 2,175 $wg, 912 $hg)
                 **Shueisha** (10,925 ~ 4,538 $wa, 6,684 $ha, 171 $wg, 555 $hg)
                 …
    footer:      Page 1 / 3

Two kinds of entry, deliberately kept apart:

* a **toggle** — a whole category switched off by its own command
  (``$togglewestern``), printed as "… are completely disabled (``$toggleX``)".
  There can be several, and they are undone by their command, not by
  ``$enable``;
* a **disable** — a bundle or series. Only the **name** is kept: the counts
  beside it describe today's pool, not the choice, and the editing step
  re-adds by name.

Without this parser (and its alias in ``mudae/commands.py``) the page is a
roll to the rest of the app: ``character_name`` came out as
"lukazade234's Disablelist (42/62)".
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.listing_pages import match_page, merge_listing_pages, strip_bold, to_int
from mudae.types import MessageKind, ParseResult

POOLS = ("wa", "ha", "wg", "hg")

# "lukazade234's Disablelist (42/62)". Anchored on "'s " so the
# Antidisablelist header ("'s Antidisablelist") can never match.
_HEADER_RE = re.compile(
    r"^(?P<owner>.+?)'s\s+Disable\s*list\s*\(\s*(?P<used>[\d,]+)\s*/\s*(?P<max>[\d,]+)\s*\)",
    re.IGNORECASE,
)
# "133,775 disabled (45,920 $wa, 47,768 $ha, 30,870 $wg, 25,315 $hg)"
_TOTAL_RE = re.compile(r"^(?P<total>[\d,]+)\s+disabled\s*\((?P<pools>[^)]*)\)", re.IGNORECASE)
# "Pool limits: 46,309 $wa, 47,739 $ha, …"
_LIMITS_RE = re.compile(r"^Pool\s+limits\s*:\s*(?P<pools>.+)$", re.IGNORECASE)
# "45,920 $wa"
_POOL_RE = re.compile(r"(?P<n>[\d,]+)\s*\$(?P<pool>wa|ha|wg|hg)\b", re.IGNORECASE)
# "Western animanga series are completely disabled ($togglewestern)"
_TOGGLE_RE = re.compile(
    r"^(?P<label>.+?)\s+(?:are|is)\s+completely\s+disabled\s*\(\s*(?P<command>\$[a-z0-9]+)\s*\)",
    re.IGNORECASE,
)
# "**Kadokawa Corporation** (13,449 ~ 8,300 $wa, …)" — on the raw line, since
# the bold run is what bounds the name.
_BOLD_ROW_RE = re.compile(r"^\*\*(?P<name>[^*]+?)\*\*\s*(?:\((?P<detail>.*)\))?\s*$")
# The same row with the bold dropped, which Mudae does now and then.
_PLAIN_ROW_RE = re.compile(r"^(?P<name>[^()]+?)\s*\(\s*[\d,]+\s*~")

_FLOOR_PREFIX = "can't be reduced below"
_LIMIT_HIT = "pool limit reached"


def _pools(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for match in _POOL_RE.finditer(text or ""):
        value = to_int(match.group("n"))
        if value is not None:
            found[match.group("pool").lower()] = value
    return found


def is_disablelist_message(content: str) -> bool:
    """True for any page of a disablelist listing.

    Keyed on the header and the total line only — never on the rows, which
    are bold names in brackets and far too common a shape on their own.
    """
    for raw in (content or "").splitlines():
        line = strip_bold(raw).strip()
        if _HEADER_RE.match(line) or _TOTAL_RE.match(line):
            return True
    return False


def parse_disablelist_page(content: str) -> dict[str, Any]:
    """Every field one page carries. All optional: later pages may hold rows only."""
    fields: dict[str, Any] = {
        "owner": None,
        "used": None,
        "max": None,
        "total": None,
        "pools": None,
        "pool_limits": None,
        "floor": None,
        "limit_warnings": [],
        "toggles": [],
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
        total = _TOTAL_RE.match(line)
        if total:
            fields["total"] = to_int(total.group("total"))
            fields["pools"] = _pools(total.group("pools"))
            continue
        limits = _LIMITS_RE.match(line)
        if limits:
            fields["pool_limits"] = _pools(limits.group("pools"))
            continue
        lowered = line.lower()
        if lowered.startswith(_FLOOR_PREFIX):
            fields["floor"] = line
            continue
        if _LIMIT_HIT in lowered:
            fields["limit_warnings"].append(line.lstrip("⚠️ ").strip())
            continue
        toggle = _TOGGLE_RE.match(line)
        if toggle:
            fields["toggles"].append(
                {"name": toggle.group("label").strip(), "command": toggle.group("command")}
            )
            continue
        row = _BOLD_ROW_RE.match(raw_line) or _PLAIN_ROW_RE.match(line)
        if row:
            name = row.group("name").strip()
            if name:
                fields["entries"].append(name)
    return fields


_SCALARS = ("owner", "used", "max", "total", "pools", "pool_limits", "floor")


def merge_disablelist_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    merged = merge_listing_pages(pages, scalar_keys=_SCALARS, list_keys=("toggles",))
    warnings: list[str] = []
    for page in pages:
        for line in page.get("limit_warnings") or []:
            if line not in warnings:
                warnings.append(line)
    merged["limit_warnings"] = warnings
    used = merged.get("used")
    merged["count_matches"] = used is not None and used in (
        len(merged["entries"]),
        len(merged["entries"]) + len(merged["toggles"]),
    )
    return merged


def parse_disablelist(content: str) -> ParseResult:
    fields = parse_disablelist_page(content)
    bits = [f"{len(fields['entries'])} disables"]
    if fields["toggles"]:
        bits.append(f"{len(fields['toggles'])} toggle{'s' if len(fields['toggles']) != 1 else ''}")
    if fields["used"] is not None:
        bits.append(f"{fields['used']}/{fields['max']}")
    if fields["page"] is not None:
        bits.append(f"page {fields['page']}/{fields['pages']}")
    return ParseResult(
        kind=MessageKind.DISABLELIST,
        summary="$dl · " + " · ".join(bits),
        fields=fields,
        warnings=[],
    )
