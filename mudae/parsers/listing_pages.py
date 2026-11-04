"""What Mudae's paged listings share: the ``Page x / y`` footer and the merge.

``$dl``/``$dld`` and ``$adl`` (and ``$wl``, which keeps its own merge for its
sphere fields) arrive as one embed per page, edited in place as the arrows are
clicked. Each page is parsed on its own; joining them is the same job for
every list, so it lives here.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# "Page 1 / 3" — the footer of every paged Mudae listing.
PAGE_RE = re.compile(r"^Page\s+(?P<page>\d+)\s*/\s*(?P<pages>\d+)\s*$", re.IGNORECASE)


def to_int(raw: Any) -> int | None:
    """``"133,775"`` → ``133775``; anything unreadable → ``None``."""
    if raw is None:
        return None
    try:
        return int(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def strip_bold(text: str) -> str:
    return str(text or "").replace("**", "")


def match_page(line: str) -> tuple[int, int] | None:
    match = PAGE_RE.match(line.strip())
    if not match:
        return None
    return int(match.group("page")), int(match.group("pages"))


def merge_listing_pages(
    pages: Iterable[dict[str, Any]],
    *,
    scalar_keys: Iterable[str],
    list_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Join the pages of one listing.

    Scalars take the first page that has them (the summary lines sit on page 1;
    later pages may or may not repeat them). ``entries`` and every key in
    ``list_keys`` are joined in first-seen order and de-duplicated by name
    (case-insensitively), so paging back and forth cannot double a row.

    ``complete`` is about **pages**, not counts: a listing is complete when
    every page from 1 to N was read, or when it never had a footer at all
    (a one-page listing). Whether the header count agrees is reported
    separately as ``count_matches``, because what Mudae counts in its header
    (rows, or rows plus toggles) is not something the app has to guess at to
    know whether it read everything.
    """
    scalar_keys = tuple(scalar_keys)
    list_keys = tuple(list_keys)
    merged: dict[str, Any] = {key: None for key in scalar_keys}
    merged["pages"] = None
    merged["entries"] = []
    for key in list_keys:
        merged[key] = []
    seen_names: dict[str, set[str]] = {"entries": set(), **{k: set() for k in list_keys}}
    seen_pages: set[int] = set()
    any_page = False

    for page in pages:
        any_page = True
        for key in scalar_keys:
            if merged[key] is None and page.get(key) is not None:
                merged[key] = page[key]
        if merged["pages"] is None and page.get("pages") is not None:
            merged["pages"] = page["pages"]
        if page.get("page") is not None:
            seen_pages.add(int(page["page"]))
        for key in ("entries", *list_keys):
            for item in page.get(key) or []:
                name = item.get("name") if isinstance(item, dict) else item
                folded = str(name or "").strip().lower()
                if not folded or folded in seen_names[key]:
                    continue
                seen_names[key].add(folded)
                merged[key].append(item)

    total = merged["pages"]
    if total:
        merged["complete"] = seen_pages >= set(range(1, int(total) + 1))
    else:
        merged["complete"] = any_page
    merged["seen_pages"] = sorted(seen_pages)
    return merged
