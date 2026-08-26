"""Parse Mudae sphere button click confirmations."""

from __future__ import annotations

import re
from typing import Any

from mudae.constants import SPHERE_EMOJI_NAME_PATTERN, canonical_sphere_emoji
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

# Custom ``<:spD:id>`` / animated ``<a:spW:id>``, or Discord copy-paste ``:spD:``.
_SPHERE_EMOJI_RE = re.compile(
    rf"(?:<a?:({SPHERE_EMOJI_NAME_PATTERN}):\d+>|(?<!<):({SPHERE_EMOJI_NAME_PATTERN}):)",
    re.IGNORECASE,
)
_USER_AMOUNT_PATTERNS = (
    re.compile(
        r"\*\*([^*+]+?)\s*\+([\d,]+)\*\*",
        re.IGNORECASE,
    ),
    re.compile(
        r"([A-Za-z0-9_.]+)\s*\+([\d,]+)",
        re.IGNORECASE,
    ),
)
_DAILY_LIMIT_RE = re.compile(r"\((\d+)/(\d+)\)")


def _sphere_emoji_name(match: re.Match[str]) -> str:
    return canonical_sphere_emoji(match.group(1) or match.group(2))


def _payout_sphere_type(content: str) -> str | None:
    """Emoji on the payout line (with ``+amount`` / ``(n/n)``), not a transform header."""
    for line in content.splitlines():
        if not line.strip():
            continue
        has_payout = any(pattern.search(line) for pattern in _USER_AMOUNT_PATTERNS)
        has_daily = bool(_DAILY_LIMIT_RE.search(line))
        if not (has_payout or has_daily):
            continue
        match = _SPHERE_EMOJI_RE.search(line)
        if match:
            return _sphere_emoji_name(match)
    return None


def is_sphere_click_message(content: str) -> bool:
    """Sphere button payout, e.g. ``<:spB:...> **user +72** (1/15)``."""
    if not content or "($k)" in content.lower():
        return False
    if not _SPHERE_EMOJI_RE.search(content):
        return False
    return bool(_DAILY_LIMIT_RE.search(content))


def parse_sphere_click(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {}

    type_match = _SPHERE_EMOJI_RE.search(content)
    payout_type = _payout_sphere_type(content)
    if payout_type:
        fields["sphere_type"] = payout_type
    elif type_match:
        fields["sphere_type"] = _sphere_emoji_name(type_match)

    claimed_by: str | None = None
    amount: int | None = None
    for text in (content, strip_markdown(content)):
        for pattern in _USER_AMOUNT_PATTERNS:
            match = pattern.search(text)
            if match:
                claimed_by = match.group(1).strip()
                amount = int(match.group(2).replace(",", ""))
                break
        if amount is not None:
            break

    if amount is not None:
        fields["amount"] = amount
    if claimed_by:
        fields["claimed_by"] = claimed_by

    daily_match = _DAILY_LIMIT_RE.search(content)
    if daily_match:
        fields["daily_used"] = int(daily_match.group(1))
        fields["daily_max"] = int(daily_match.group(2))

    if amount is None:
        return ParseResult(
            kind=MessageKind.SPHERE_CLICK,
            summary="Sphere click (unparsed)",
            fields=fields,
            warnings=["Could not parse sphere amount"],
        )
    if not claimed_by:
        warnings.append("Could not extract username from sphere line")

    sphere_label = fields.get("sphere_type", "sp")
    user_label = claimed_by or "?"
    summary = f"Sphere click · {sphere_label} · +{amount} · {user_label}"
    if daily_match:
        summary += f" · {fields['daily_used']}/{fields['daily_max']} today"
    return ParseResult(
        kind=MessageKind.SPHERE_CLICK,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
