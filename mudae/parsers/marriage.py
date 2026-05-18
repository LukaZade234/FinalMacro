"""Parse Mudae marriage confirmation lines."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult


def parse_marriage(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {"raw_content": content}

    match = re.search(
        r"(?:💖\s*)?(.*?)\s+and\s+(.*?)\s+are now married",
        content,
        re.IGNORECASE,
    )
    if match:
        fields["winner"] = strip_markdown(match.group(1)).strip()
        fields["character"] = strip_markdown(match.group(2)).strip()
    else:
        warnings.append("Could not parse marriage participants")

    winner = fields.get("winner", "?")
    character = fields.get("character", "?")
    summary = f"Marriage · {winner} + {character}"
    return ParseResult(
        kind=MessageKind.MARRIAGE,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
