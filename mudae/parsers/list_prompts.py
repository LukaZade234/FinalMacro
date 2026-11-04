"""What Mudae says back while a list is being rebuilt.

**Clearing** a list asks for the word ``confirm``, worded per list::

    Type confirm to confirm the clean of your $disablelist.
    Type confirm to confirm the clean of all YOUR wishes (characters and series).

so only the shared opening is matched. Once ``confirm`` is typed, Mudae reacts with a **tick on the original
clear command** (``$eall`` / ``$aeall`` / ``$wrall``), not on the ``confirm``.

**Adding a starwish** with no starwish slot left asks to trade wishlist slots
for one::

    You reached your limit of 9 $starwish!
    Would you like to sacrifice 8 wishlist slots to upgrade this limit by +1? (y/n/yes/no)

``y`` accepts, and Mudae ticks the ``$sw`` command. That costs wishlist slots
for good, so the macro only answers ``y`` when the user allowed it.

No other add asks anything (captured 2026-11-04).

**A toggle** gets **no tick** — only a reply saying which way it went::

    Western animanga series are now DISABLED for YOUR rolls! ($ima western)
    Use $disable western INSTEAD OF $togglewestern if you want …
    Real Life People series are now ENABLED for YOUR rolls!

DISABLED means the toggle is now **on** (the category is switched off).
"""

from __future__ import annotations

import re
from typing import Any

from mudae.types import MessageKind, ParseResult

_CLEAR_RE = re.compile(
    r"type\s+confirm\s+to\s+confirm\s+the\s+clean\s+of\s+(?P<what>[^\n]*)",
    re.IGNORECASE,
)
_TOGGLE_RE = re.compile(
    r"(?P<label>[^\n]+?)\s+series\s+are\s+now\s+(?P<state>disabled|enabled)\s+for\s+your\s+rolls",
    re.IGNORECASE,
)
_SW_LIMIT_RE = re.compile(
    r"reached\s+your\s+limit\s+of\s+(?P<limit>[\d,]+)\s+\$starwish", re.IGNORECASE
)
_SW_SACRIFICE_RE = re.compile(
    r"sacrifice\s+(?P<slots>[\d,]+)\s+wishlist\s+slots?.*?\+\s*(?P<gain>\d+)",
    re.IGNORECASE | re.DOTALL,
)


def _int(raw: str | None) -> int | None:
    try:
        return int(str(raw).replace(",", "")) if raw else None
    except ValueError:
        return None


def _clean(text: str) -> str:
    return str(text or "").replace("**", "")


def is_list_clear_prompt(text: str) -> bool:
    return bool(_CLEAR_RE.search(_clean(text)))


def is_starwish_limit_prompt(text: str) -> bool:
    return bool(_SW_LIMIT_RE.search(_clean(text)))


def toggle_result(text: str) -> bool | None:
    """``True`` when a toggle reply says the category is now disabled (toggle
    on), ``False`` when enabled (off), ``None`` when it is not a toggle reply."""
    match = _TOGGLE_RE.search(_clean(text))
    if not match:
        return None
    return match.group("state").lower() == "disabled"


def is_toggle_result(text: str) -> bool:
    return toggle_result(text) is not None


def is_list_prompt(text: str) -> bool:
    return is_list_clear_prompt(text) or is_starwish_limit_prompt(text) or is_toggle_result(text)


def parse_list_prompt(text: str) -> ParseResult:
    clean = _clean(text)
    fields: dict[str, Any] = {"prompt": None}
    clear = _CLEAR_RE.search(clean)
    toggle = _TOGGLE_RE.search(clean)
    if clear:
        fields.update(prompt="clear", what=clear.group("what").strip().rstrip("."))
        summary = f"clear {fields['what']} — waiting for confirm"
    elif toggle:
        on = toggle.group("state").lower() == "disabled"
        fields.update(prompt="toggle", label=toggle.group("label").strip(), toggle_on=on)
        summary = f"{fields['label']} series {'disabled (toggle on)' if on else 'enabled (toggle off)'}"
    else:
        limit = _SW_LIMIT_RE.search(clean)
        sacrifice = _SW_SACRIFICE_RE.search(clean)
        fields.update(
            prompt="starwish_limit",
            starwish_limit=_int(limit.group("limit")) if limit else None,
            sacrifice_slots=_int(sacrifice.group("slots")) if sacrifice else None,
            gain=_int(sacrifice.group("gain")) if sacrifice else None,
        )
        summary = (
            f"$starwish limit {fields['starwish_limit']} reached — "
            f"sacrifice {fields['sacrifice_slots']} wishlist slots? (y/n)"
        )
    return ParseResult(kind=MessageKind.LIST_PROMPT, summary=summary, fields=fields, warnings=[])
