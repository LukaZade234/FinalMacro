"""Parse Mudae server claim-interval rejection (user pinged on failed claim)."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import extract_bold_minutes, strip_markdown
from mudae.types import MessageKind, ParseResult

_MENTION_RE = re.compile(r"<@!?(\d+)>")
_INTERVAL_HOURS_RE = re.compile(
    r"interval of\s+(\d+)\s*h(?:ou)?r?s?",
    re.IGNORECASE,
)
_NEXT_INTERVAL_MIN_RE = re.compile(
    r"next interval begins in\s+(\d+)\s*min",
    re.IGNORECASE,
)


def is_claim_interval_message(content: str) -> bool:
    lower = (content or "").lower()
    return (
        "once per interval" in lower
        and "next interval begins" in lower
        and "for this server" in lower
    )


def parse_claim_interval(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {"raw_content": content}

    mention = _MENTION_RE.search(content)
    if mention:
        fields["user_id"] = int(mention.group(1))
    else:
        warnings.append("Could not parse pinged user id")

    interval_match = _INTERVAL_HOURS_RE.search(content)
    if interval_match:
        fields["interval_hours"] = int(interval_match.group(1))
    else:
        warnings.append("Could not parse claim interval hours")

    clean = strip_markdown(content)
    minutes = extract_bold_minutes(clean, start=clean.lower().find("next interval begins"))
    if minutes is None:
        minutes_match = _NEXT_INTERVAL_MIN_RE.search(clean)
        if minutes_match:
            minutes = int(minutes_match.group(1))
    if minutes is not None:
        fields["next_interval_minutes"] = minutes
    else:
        warnings.append("Could not parse minutes until next interval")

    user_label = str(fields.get("user_id", "?"))
    interval = fields.get("interval_hours")
    wait = fields.get("next_interval_minutes")
    summary = f"Claim interval · user {user_label}"
    if interval is not None:
        summary += f" · 1 per {interval}h"
    if wait is not None:
        summary += f" · next in {wait}m"

    return ParseResult(
        kind=MessageKind.CLAIM_INTERVAL,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
