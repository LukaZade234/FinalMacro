"""Parse Mudae's ``$wlz+z!`` / ``$wlsz+z!`` wishlist listing.

One line per wished character, carrying three things nothing else in the app
captures:

* the **wishlist sizes** in the header (``160/162 $wl, 16/16 $sw``), which is
  what the ``$bw`` optimum has always been blocked on;
* the **spheres invested** per character;
* the **ouroperk upgrades** on each character — the OP-character roster that
  ``macro/sphere_upgrades.py`` abstains on for perk 1, and that the Spheres →
  Characters page needs.

The same body arrives two ways. ``$wlsz+z!`` (the ``s`` flag) is DM'd whole,
across several messages sent back to back with no page footer;  ``$wlz+z!``
is posted in the channel 20 rows at a time with a ``Page 1 / 8`` footer and
reaction arrows. This module parses **one message** either way and leaves
stitching them to the caller, which is the only part that differs.

A row looks like::

    Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full
    Nazuna Nanakusa ✅ 🔐 +125% · 7,000 sp - 5 (x5), 6, 8, 9, 10
    Tanya Degurechaff ✅ 🔐 · 7,600 sp - 4 (x2), 5 (x5), 6, 8, 9, 10

``⭐`` is a starwish (they are a subset of the ``$wl`` count, not additional:
16 starred rows against ``16/16 $sw``, and 160 rows over 8 pages of 20 against
``160/162 $wl``). ``+N%`` is that character's sphere value bonus and is absent
on most rows. ``Full`` means every upgrade is maxed; otherwise the list is
perk numbers with an optional ``(xN)`` multiplicity.

Bold is stripped rather than trusted: Mudae's own output applies ``**`` to
some rows and not others, and mid-row (``**7,000** sp``) at that.
"""

from __future__ import annotations

import re
from typing import Any

# "lukazade234's Wishlist - 160/162 $wl, 16/16 $sw"
_HEADER_RE = re.compile(
    r"^(?P<owner>.+?)'s\s+Wishlist\s*-\s*"
    r"(?P<wl_used>[\d,]+)\s*/\s*(?P<wl_max>[\d,]+)\s*\$wl"
    r"(?:\s*,\s*(?P<sw_used>[\d,]+)\s*/\s*(?P<sw_max>[\d,]+)\s*\$sw)?",
    re.IGNORECASE,
)

# "Page 1 / 8" — channel listing only; the DM has no footer.
_PAGE_RE = re.compile(r"^Page\s+(?P<page>\d+)\s*/\s*(?P<pages>\d+)\s*$", re.IGNORECASE)

# The structural anchor of a row: "· 30,000 sp - <upgrades>". Everything left
# of the "·" is the name plus its flags, which is the fuzzy half.
_ROW_RE = re.compile(
    r"^(?P<head>.*?)·\s*(?P<spheres>[\d,]+)\s*sp\s*-\s*(?P<upgrades>.+?)\s*$"
)

# Flags that follow the name. The first one found ends the name.
_FLAG_RE = re.compile(r"[✅⭐\U0001f510]|\+\d+%")
_PERCENT_RE = re.compile(r"\+(\d+)%")

# "5 (x5)" / "6"
_UPGRADE_RE = re.compile(r"^(?P<perk>\d+)(?:\s*\(x(?P<count>\d+)\))?$")

STARWISH_EMOJI = "⭐"
_FULL = "full"


def _int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def strip_bold(text: str) -> str:
    """Remove Discord bold markers, which Mudae applies inconsistently here."""
    return str(text or "").replace("**", "")


def parse_upgrades(text: str) -> dict[str, Any]:
    """``Full``, or perk numbers with multiplicity, as ``{perk: count}``.

    ``full`` is kept as its own flag rather than expanded into a perk map:
    Mudae does not say which perks "Full" covers, and inventing that would be
    a guess in exactly the place the roster is supposed to be evidence.
    """
    body = strip_bold(text).strip()
    if body.lower() == _FULL:
        return {"full": True, "perks": {}}
    perks: dict[int, int] = {}
    for chunk in body.split(","):
        match = _UPGRADE_RE.match(chunk.strip())
        if not match:
            continue
        perk = _int(match.group("perk"))
        if perk is None:
            continue
        perks[perk] = perks.get(perk, 0) + (_int(match.group("count")) or 1)
    return {"full": False, "perks": perks}


def parse_wishlist_row(line: str) -> dict[str, Any] | None:
    """One character row, or ``None`` when the line is not one."""
    clean = strip_bold(line).strip()
    if not clean:
        return None
    match = _ROW_RE.match(clean)
    if not match:
        return None
    head = match.group("head")
    flag_match = _FLAG_RE.search(head)
    name = (head[: flag_match.start()] if flag_match else head).strip()
    if not name:
        return None
    flags = head[flag_match.start():] if flag_match else ""
    percent_match = _PERCENT_RE.search(flags)
    spheres = _int(match.group("spheres"))
    if spheres is None:
        return None
    upgrades = parse_upgrades(match.group("upgrades"))
    return {
        "name": name,
        "starwish": STARWISH_EMOJI in flags,
        "sphere_percent": _int(percent_match.group(1)) if percent_match else None,
        "spheres": spheres,
        "upgrades_full": upgrades["full"],
        "upgrades": upgrades["perks"],
    }


def is_wishlist_message(content: str) -> bool:
    """True for any page or DM part of a wishlist listing.

    Later DM parts carry no header, so a row on its own has to be enough —
    but a bare row is a specific enough shape (``· N sp - …``) that this does
    not widen into other Mudae output.
    """
    text = strip_bold(content or "")
    for line in text.splitlines():
        stripped = line.strip()
        if _HEADER_RE.match(stripped):
            return True
        if parse_wishlist_row(stripped) is not None:
            return True
    return False


def parse_wishlist_page(content: str) -> dict[str, Any]:
    """Header, rows and page footer from **one** message.

    Every field is optional on purpose: a continuation DM has rows but no
    header, and a DM has no page footer at all.
    """
    fields: dict[str, Any] = {
        "owner": None,
        "wl_used": None,
        "wl_max": None,
        "sw_used": None,
        "sw_max": None,
        "page": None,
        "pages": None,
        "entries": [],
    }
    for raw_line in strip_bold(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header = _HEADER_RE.match(line)
        if header:
            fields["owner"] = header.group("owner").strip()
            fields["wl_used"] = _int(header.group("wl_used"))
            fields["wl_max"] = _int(header.group("wl_max"))
            fields["sw_used"] = _int(header.group("sw_used"))
            fields["sw_max"] = _int(header.group("sw_max"))
            continue

        page = _PAGE_RE.match(line)
        if page:
            fields["page"] = _int(page.group("page"))
            fields["pages"] = _int(page.group("pages"))
            continue

        row = parse_wishlist_row(line)
        if row is not None:
            fields["entries"].append(row)

    return fields


def merge_wishlist_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Join the parts of one listing into a single result.

    Works for both capture routes: several DM messages, or several channel
    pages. Rows are de-duplicated by name — paging back and forth, or a DM
    part arriving twice, must not double-count a character. ``complete``
    reports whether as many rows arrived as the header said to expect, so a
    caller can refuse to act on a listing that was cut short.
    """
    merged: dict[str, Any] = {
        "owner": None,
        "wl_used": None,
        "wl_max": None,
        "sw_used": None,
        "sw_max": None,
        "pages": None,
        "entries": [],
        "complete": False,
    }
    seen: set[str] = set()
    seen_pages: set[int] = set()
    for page in pages:
        for key in ("owner", "wl_used", "wl_max", "sw_used", "sw_max", "pages"):
            if merged[key] is None and page.get(key) is not None:
                merged[key] = page[key]
        if page.get("page") is not None:
            seen_pages.add(int(page["page"]))
        for entry in page.get("entries") or []:
            key = str(entry.get("name") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged["entries"].append(entry)

    expected = merged["wl_used"]
    if expected is not None:
        merged["complete"] = len(merged["entries"]) >= int(expected)
    elif merged["pages"]:
        merged["complete"] = seen_pages == set(range(1, int(merged["pages"]) + 1))
    merged["seen_pages"] = sorted(seen_pages)
    return merged


def wishlist_text(snapshot: Any) -> str:
    """All the listing text on a message, whichever form it arrived in.

    The DM is plain content; the channel reply is an **embed** — header in
    ``author``, rows in ``description``, ``Page 1 / 8`` in ``footer`` — and
    carries no content at all. Reading only ``content`` is why the channel
    route parsed nothing.
    """
    parts: list[str] = [str(getattr(snapshot, "content", "") or "")]
    for embed in getattr(snapshot, "embeds", None) or []:
        if not isinstance(embed, dict):
            continue
        for key in ("author", "title", "description", "footer"):
            value = embed.get(key)
            if value:
                parts.append(str(value))
    return "\n".join(part for part in parts if part.strip())


def parse_wishlist_text_result(content: str) -> Any:
    """Same as :func:`parse_wishlist_result` for a plain-text body.

    The command dispatcher hands some parsers text rather than a snapshot;
    the DM route is plain text, so this is a real path, not a stub.
    """
    return parse_wishlist_result(_TextOnly(content))


class _TextOnly:
    """Minimal snapshot stand-in: content, no embeds."""

    __slots__ = ("content", "embeds")

    def __init__(self, content: str) -> None:
        self.content = content or ""
        self.embeds: list[Any] = []


def parse_wishlist_result(snapshot: Any) -> Any:
    """Pipeline entry point: one message's fields as a ``ParseResult``.

    The summary names what this part carried rather than the whole listing,
    because a listing is several messages and only the caller stitching them
    knows how far along it is.
    """
    from mudae.types import MessageKind, ParseResult

    fields = parse_wishlist_page(wishlist_text(snapshot))
    count = len(fields["entries"])
    bits = [f"{count} character{'' if count == 1 else 's'}"]
    if fields["page"] is not None and fields["pages"] is not None:
        bits.append(f"page {fields['page']}/{fields['pages']}")
    if fields["wl_used"] is not None:
        bits.append(f"{fields['wl_used']}/{fields['wl_max']} $wl")
    if fields["sw_used"] is not None:
        bits.append(f"{fields['sw_used']}/{fields['sw_max']} $sw")
    return ParseResult(
        kind=MessageKind.WISHLIST,
        summary="$wl · " + " · ".join(bits),
        fields=fields,
        warnings=[],
    )
