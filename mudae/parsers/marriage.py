"""Parse Mudae marriage confirmation lines (delegates to claim parser)."""

from __future__ import annotations

from mudae.parsers.claim import is_marriage_claim, parse_claim
from mudae.types import ParseResult


def parse_marriage(content: str) -> ParseResult:
    return parse_claim(content)
