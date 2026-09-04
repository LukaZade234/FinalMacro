"""Match a parsed roll against the app-only wishlist.

Separate from Mudae's own ``$wish``/``$wl`` (`gui/wishlist_store.py` holds the
two name lists; this module only answers "does this roll match one of them").
A hit is treated exactly like a Mudae wish ping — claimed immediately, `$rt`
spent if the slot needs it — via the same ``code="wish_ping"`` interrupt
`macro/roll_interrupts.py` already produces for a real one, so every
downstream behaviour (interrupting the roll loop, `$rt`, "stop after wish
claim") is shared rather than reimplemented.

Matching is exact, case- and whitespace-insensitive — not substring — so a
character named "Mari" does not fire on a roll for "Marin". Character and
series are matched independently: a name only needs to be on one list.
"""

from __future__ import annotations

import re
from typing import Any

# ``$`` is what ``mudae.list_formatter.format_mudae_character_list`` joins with,
# so its output pastes straight in here; commas and newlines are accepted too
# because that is what a hand-typed or copied list usually looks like.
_INPUT_SPLIT = re.compile(r"[$,\n\r]+")


def normalize_wishlist_name(name: str) -> str:
    """Fold a name to a comparison key: trimmed, lowercase, collapsed spaces."""
    return " ".join(str(name or "").strip().lower().split())


def parse_wishlist_input(text: str) -> list[str]:
    """Split one input box into names, in source order, without duplicates.

    Accepts ``Rem$Alice$Audrey``, ``Rem $Alice $Audrey``, ``Rem, Alice`` and
    newline-separated text interchangeably — a single name is just the case
    where nothing splits.
    """
    names: list[str] = []
    seen: set[str] = set()
    for chunk in _INPUT_SPLIT.split(str(text or "")):
        name = " ".join(chunk.strip().split())
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def match_wishlist(
    fields: dict[str, Any],
    characters: list[str],
    series: list[str],
) -> str | None:
    """Human-readable match reason, or ``None``.

    Callers are responsible for ``claimed``/``can_claim`` gating — this only
    answers whether the name matches, the same split of concerns the real
    wish-ping check uses.
    """
    if not characters and not series:
        return None

    character_name = fields.get("character_name")
    if character_name:
        target = normalize_wishlist_name(character_name)
        for entry in characters:
            if normalize_wishlist_name(entry) == target:
                return f"{character_name} (wishlist)"

    series_name = fields.get("series")
    if series_name:
        target = normalize_wishlist_name(series_name)
        for entry in series:
            if normalize_wishlist_name(entry) == target:
                return f"{series_name} (series wishlist)"

    return None
