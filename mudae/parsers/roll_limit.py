"""Parse Mudae's hourly roll-limit rejection (rolling with 0 rolls left)."""

from __future__ import annotations

import re
from typing import Any

from mudae.types import MessageKind, ParseResult

_HOURLY_LIMIT_RE = re.compile(
    r"roulette is limited to\s+(\d+)\s+uses per hour",
    re.IGNORECASE,
)
_MINUTES_LEFT_RE = re.compile(
    r"(\d+)\s*min(?:ute)?s?\s+left",
    re.IGNORECASE,
)


def is_roll_limit_message(content: str) -> bool:
    """True when Mudae rejects a roll because the hourly pool is empty."""
    lower = (content or "").lower()
    return "roulette is limited" in lower or (
        "uses per hour" in lower and "min left" in lower
    )


def parse_roll_limit(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {
        "rolls_left": 0,
        "rolls_exhausted": True,
        "raw_content": content,
    }

    limit_match = _HOURLY_LIMIT_RE.search(content or "")
    if limit_match:
        fields["hourly_roll_limit"] = int(limit_match.group(1))
    else:
        warnings.append("Could not parse hourly roll limit")

    minutes_match = _MINUTES_LEFT_RE.search(content or "")
    if minutes_match:
        fields["rolls_reset_minutes"] = int(minutes_match.group(1))
    else:
        warnings.append("Could not parse minutes until refill")

    summary_parts = ["Hourly roll limit reached"]
    if (reset := fields.get("rolls_reset_minutes")) is not None:
        summary_parts.append(f"refill in {reset}m")
    summary = " · ".join(summary_parts)

    return ParseResult(
        kind=MessageKind.ROLL_LIMIT,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
