"""Parse Mudae ``$us`` (use stacked rolls) responses.

Sending ``$us`` on its own reports how many rolls are *stacked* in the pool,
e.g. ``You have **7,872.8** rolls stacked.``. ``$us <n>`` (1-20) then moves
that many into the usable roll count until the next rolls reset.
"""

from __future__ import annotations

import re

from mudae.types import MessageKind, ParseResult

_STACK_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*\*{0,2}\s*rolls?\s+stacked",
    re.IGNORECASE,
)


def parse_us_stacked(content: str) -> float | None:
    """Return the stacked-roll pool size from a bare ``$us`` response."""
    if not content:
        return None
    match = _STACK_RE.search(content)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def is_us_stack_response(content: str) -> bool:
    return parse_us_stacked(content) is not None


def parse_us(content: str) -> ParseResult:
    stacked = parse_us_stacked(content)
    fields = {"us_stacked": stacked}
    if stacked is None:
        return ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="$us",
            fields=fields,
            warnings=["Could not parse $us stacked rolls"],
        )
    return ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary=f"$us · {stacked:g} stacked",
        fields=fields,
        warnings=[],
    )
