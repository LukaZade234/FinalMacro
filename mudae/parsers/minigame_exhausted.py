"""Parse Mudae rejecting a minigame because daily uses are spent."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.ohu8 import parse_refill_minutes
from mudae.types import MessageKind, ParseResult

# ``You don't have enough $oh for today. Time to wait before the refill: 3h 08 min.``
_EXHAUSTED_GAME_RE = re.compile(
    r"don['’]t have enough\s+\*{0,2}\$?(oh|oc|oq|ot)\*{0,2}\s+for today",
    re.IGNORECASE,
)


def is_minigame_exhausted_message(content: str) -> bool:
    """True when Mudae rejects ``$oh`` / ``$oc`` / ``$oq`` / ``$ot`` with no uses left."""
    return _EXHAUSTED_GAME_RE.search(content or "") is not None


def format_refill_wait(minutes: int | None) -> str:
    """Human refill wait, matching Mudae's ``3h 08 min`` style."""
    if minutes is None:
        return ""
    hours, mins = divmod(max(0, int(minutes)), 60)
    if hours and mins:
        return f"{hours}h {mins:02d} min"
    if hours:
        return f"{hours}h"
    return f"{mins} min"


def format_exhausted_activity(fields: dict[str, Any]) -> str:
    """Activity-log / status line for an exhausted minigame attempt."""
    game = str(fields.get("game") or "?").lstrip("$")
    wait = format_refill_wait(fields.get("refill_minutes"))
    if wait:
        return f"${game}: out of minigames for today · refill in {wait}"
    return f"${game}: out of minigames for today"


def parse_minigame_exhausted(content: str) -> ParseResult:
    warnings: list[str] = []
    match = _EXHAUSTED_GAME_RE.search(content or "")
    game = match.group(1).lower() if match else None
    if game is None:
        warnings.append("Could not parse which minigame was exhausted")

    refill = parse_refill_minutes(content)
    if refill is None:
        warnings.append("Could not parse minutes until refill")

    fields: dict[str, Any] = {
        "game": game,
        "exhausted": True,
        "refill_minutes": refill,
    }
    summary = format_exhausted_activity(fields)
    return ParseResult(
        kind=MessageKind.MINIGAME_EXHAUSTED,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
