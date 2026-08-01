"""Parse Mudae ``$rt`` (reset timer) responses and ``$tu`` rt status lines."""

from __future__ import annotations

from typing import Any

from mudae.commands import is_tu_response
from mudae.parsers.tu import _minutes_after_phrase, parse_tu
from mudae.types import MessageKind, ParseResult


def extract_rt_fields(content: str) -> dict[str, Any]:
    """Parse ``$rt`` outcome fields from a Mudae message."""
    fields: dict[str, Any] = {}
    if not content:
        return fields

    lower = content.lower()

    if is_tu_response(content):
        tu_fields = parse_tu(content).fields
        fields.update(tu_fields)
        if tu_fields.get("claim_available") is True:
            fields["rt_used"] = True
        return fields

    next_rt = _minutes_after_phrase(content, "next $rt in")
    if next_rt is None:
        next_rt = _minutes_after_phrase(content, "próximo $rt")
    if next_rt is not None:
        fields["rt_next_minutes"] = next_rt
        fields["rt_available"] = False
        fields["rt_failed"] = True
    elif "can't use" in lower and "$rt" in lower:
        fields["rt_failed"] = True

    return fields


def is_rt_response(content: str) -> bool:
    """True when a message looks like feedback from ``$rt``."""
    if not content:
        return False
    if is_tu_response(content):
        return True
    lower = content.lower()
    return "next $rt" in lower or ("$rt" in lower and ("can't" in lower or "cannot" in lower))


def parse_rt(content: str) -> ParseResult:
    fields = extract_rt_fields(content)
    warnings: list[str] = []
    summary_parts = ["$rt"]
    if fields.get("rt_used"):
        summary_parts.append("claim reset")
    elif fields.get("rt_failed"):
        summary_parts.append("failed")
    if (minutes := fields.get("rt_next_minutes")) is not None:
        h, m = divmod(int(minutes), 60)
        summary_parts.append(f"next {h}h {m}m" if h else f"next {m}m")
    if fields.get("claim_available") is True:
        summary_parts.append("can claim")
    return ParseResult(
        kind=MessageKind.TU,
        summary=" · ".join(summary_parts),
        fields=fields,
        warnings=warnings,
    )
