"""Parse Mudae ``$p`` (pokemon) and ``$daily`` replies.

Both commands are account-global: one send on any server consumes the cooldown
everywhere. Success and cooldown copy is enough — pokemon win details are not
stored.
"""

from __future__ import annotations

import re

from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

_P_COOLDOWN_RE = re.compile(
    r"remaining time before your next\s*\$p:\s*(?:(\d+)\s*h)?\s*(\d+)\s*min",
    re.IGNORECASE,
)
_P_WON_RE = re.compile(r"you won", re.IGNORECASE)
# Shortcodes (`:wooper::wooper:`) or live Discord custom emojis (`<:Shelmet:id>`).
_P_GRID_RE = re.compile(
    r"(?::\w+:|<a?:\w+:\d+>)\s*(?::\w+:|<a?:\w+:\d+>)",
)
_P_BELL = "\U0001f514"
_DAILY_COOLDOWN_RE = re.compile(
    r"next\s*\$daily\s*reset in\s*(?:(\d+)\s*h)?\s*(\d+)\s*min",
    re.IGNORECASE,
)
_TU_MARKERS = ("rolls left", "rolls restantes", "you __can__ claim", "can't claim")


def _plain(content: str) -> str:
    return strip_markdown(content or "")


def _minutes_from_match(match: re.Match[str]) -> int:
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def is_p_response(content: str) -> bool:
    """True for a ``$p`` win grid or the ``$p`` cooldown line."""
    if not content:
        return False
    plain = _plain(content)
    if _P_COOLDOWN_RE.search(plain):
        return True
    if _P_WON_RE.search(plain):
        return True
    if _P_BELL in content or ":pokenew:" in plain.lower():
        return True
    return bool(_P_GRID_RE.search(plain))


def is_daily_cooldown_response(content: str) -> bool:
    """True for the standalone ``$daily`` cooldown reply (not a ``$tu`` blob)."""
    if not content:
        return False
    plain = _plain(content)
    if not _DAILY_COOLDOWN_RE.search(plain):
        return False
    lowered = plain.lower()
    return not any(marker in lowered for marker in _TU_MARKERS)


def parse_p_cooldown_minutes(content: str) -> int | None:
    match = _P_COOLDOWN_RE.search(_plain(content))
    if not match:
        return None
    return _minutes_from_match(match)


def parse_daily_cooldown_minutes(content: str) -> int | None:
    match = _DAILY_COOLDOWN_RE.search(_plain(content))
    if not match:
        return None
    return _minutes_from_match(match)


def parse_p(content: str) -> ParseResult:
    """Classify a ``$p`` reply as success or cooldown."""
    fields: dict[str, object] = {}
    cooldown = parse_p_cooldown_minutes(content)
    if cooldown is not None:
        fields["p_success"] = False
        fields["p_cooldown_minutes"] = cooldown
        hours, minutes = divmod(cooldown, 60)
        summary = f"$p cooldown · {hours}h {minutes:02d} min"
        return ParseResult(kind=MessageKind.P, summary=summary, fields=fields)

    # Anything that is not the cooldown line is a successful send. Live wins
    # use custom emojis + "You won Shelmet"; older copies used :pokenew:.
    won = bool(_P_WON_RE.search(_plain(content)))
    fields["p_success"] = True
    summary = "$p · won" if won else "$p · sent"
    return ParseResult(kind=MessageKind.P, summary=summary, fields=fields)


def parse_daily(content: str) -> ParseResult:
    """Classify a ``$daily`` cooldown reply.

    A successful ``$daily`` is a Mudae tick on the user command, not this text.
    """
    cooldown = parse_daily_cooldown_minutes(content)
    if cooldown is None:
        return ParseResult(
            kind=MessageKind.DAILY,
            summary="$daily",
            fields={},
            warnings=["Could not parse $daily reply"],
        )
    hours, minutes = divmod(cooldown, 60)
    return ParseResult(
        kind=MessageKind.DAILY,
        summary=f"$daily cooldown · {hours}h {minutes:02d} min",
        fields={"daily_success": False, "daily_cooldown_minutes": cooldown},
    )


def is_p_parse_result(parsed: ParseResult) -> bool:
    """True when the parse actually classified a ``$p`` win or cooldown."""
    if parsed.fields.get("p_success") is not None:
        return True
    if parsed.fields.get("p_cooldown_minutes") is not None:
        return True
    return parsed.kind == MessageKind.P and bool(parsed.fields)


def is_daily_parse_result(parsed: ParseResult) -> bool:
    if parsed.kind == MessageKind.DAILY:
        return True
    if parsed.fields.get("daily_cooldown_minutes") is not None:
        return True
    if parsed.kind == MessageKind.COMMAND_RESPONSE:
        cmd = (parsed.fields.get("parser_command") or parsed.fields.get("command") or "").lower()
        return cmd == "daily"
    return False
