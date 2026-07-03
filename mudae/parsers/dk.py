"""Parse Mudae ``$dk`` (daily kakera) responses."""

from __future__ import annotations

import re
from typing import Any

from mudae.types import MessageKind, ParseResult

_DK_AMOUNT_RE = re.compile(
    r"(?:nice,\s*)?\*\*\+([\d,]+)\*\*\s*<:kakera:",
    re.IGNORECASE,
)
_DK_TOTAL_RE = re.compile(
    r"\(\*\*([\d,]+)\*\*\s*total\)",
    re.IGNORECASE,
)
_DK_LEFT_RE = re.compile(
    r"\*\*(\d+)\*\*\s*\$dk\s+left",
    re.IGNORECASE,
)
_DK_SPHERES_RE = re.compile(
    r"\+\*\*([\d,]+)\*\*\s*<:sp:",
    re.IGNORECASE,
)


def is_dk_claim(content: str) -> bool:
    """True for a ``$dk`` payout line (not a kakera button react ``($k)``)."""
    if not content or "($k)" in content.lower():
        return False
    return "added to your kakera collection" in content.lower()


def extract_dk_fields(content: str) -> dict[str, Any]:
    """Parse ``$dk`` reward fields from a message (standalone or combined with ``$tu``)."""
    fields: dict[str, Any] = {}
    if not is_dk_claim(content):
        return fields

    fields["dk_used"] = True
    fields["earn_method"] = "daily_kakera"

    amount_match = _DK_AMOUNT_RE.search(content)
    if amount_match:
        fields["amount"] = int(amount_match.group(1).replace(",", ""))

    total_match = _DK_TOTAL_RE.search(content)
    if total_match:
        fields["total_kakera"] = int(total_match.group(1).replace(",", ""))

    left_match = _DK_LEFT_RE.search(content)
    if left_match:
        fields["dk_stock"] = int(left_match.group(1))
    else:
        fields["dk_stock"] = 0

    spheres_match = _DK_SPHERES_RE.search(content)
    if spheres_match:
        fields["spheres"] = int(spheres_match.group(1).replace(",", ""))

    return fields


def parse_dk(content: str) -> ParseResult:
    fields = extract_dk_fields(content)
    warnings: list[str] = []
    amount = fields.get("amount")
    if amount is None:
        warnings.append("Could not parse $dk kakera amount")
    summary_parts = ["$dk"]
    if amount is not None:
        summary_parts.append(f"+{amount} kakera")
    if (stock := fields.get("dk_stock")) is not None:
        summary_parts.append(f"{stock} left")
    if (spheres := fields.get("spheres")) is not None:
        summary_parts.append(f"+{spheres} sp")
    return ParseResult(
        kind=MessageKind.DK_CLAIM,
        summary=" · ".join(summary_parts),
        fields=fields,
        warnings=warnings,
    )
