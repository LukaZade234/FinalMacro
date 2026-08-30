"""Parse Mudae sphere button click confirmations."""

from __future__ import annotations

import re
from typing import Any

from mudae.constants import (
    SPHERE_EMOJI_NAME_PATTERN,
    SPHERE_TRANSFORM_EMOJIS,
    canonical_sphere_emoji,
)
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
# ``<:spD:1> turns into <:spW:2>`` / ``:spL: breaks down into :spB: + :spT:``.
# The source has to sit directly before the verb: kakera lines and the ``$op 8``
# note ("💎/2 turns into 2x 🔴") also say "turns into" and must not match.
_TRANSFORM_RE = re.compile(
    rf"(?:<a?:(?P<src1>{SPHERE_EMOJI_NAME_PATTERN}):\d+>"
    rf"|(?<!<):(?P<src2>{SPHERE_EMOJI_NAME_PATTERN}):)"
    r"\s*(?P<verb>turns\s+into|breaks\s+down\s+into)",
    re.IGNORECASE,
)


def _sphere_emoji_name(match: re.Match[str]) -> str:
    return canonical_sphere_emoji(match.group(1) or match.group(2))


def _transform(content: str) -> tuple[str, list[str]] | None:
    """``(clicked colour, what it paid out as)`` for a dark/light click.

    Dark and light spend the click and then pay under the *result*, so the
    payout line names a colour that was never on the button. Only the header
    carries the sphere that was actually clicked.
    """
    match = _TRANSFORM_RE.search(content)
    if match is None:
        return None
    source = canonical_sphere_emoji(match.group("src1") or match.group("src2"))
    if source not in SPHERE_TRANSFORM_EMOJIS:
        return None
    # Stop at the payout: the line below repeats dark's outcome, and light's
    # fragment list ends at the ``=>`` total.
    rest = re.split(r"\n|=>", content[match.end():], maxsplit=1)[0]
    outcomes = [_sphere_emoji_name(m) for m in _SPHERE_EMOJI_RE.finditer(rest)]
    if "breaks" not in match.group("verb").lower():
        outcomes = outcomes[:1]
    return source, outcomes


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
    transform = _transform(content)
    payout_type = _payout_sphere_type(content)
    if transform is not None:
        fields["sphere_type"], resolved = transform
        if resolved:
            fields["sphere_resolved"] = resolved
    elif payout_type:
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
    resolved = fields.get("sphere_resolved") or []
    if resolved:
        sphere_label += " \u2192 " + "+".join(resolved)
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
