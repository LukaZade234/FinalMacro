"""Parse Mudae's ``$kl`` (kakera loots) exchange.

``$kl N`` spends ``N`` loots of kakera (500 each by default) and answers with
one line per reward::

    :rollstack: +9,628.8 rolls stacked (Stock: 3,469,817.8)
    :morekakera: +1,195,387 kakera
    :disablemore: $limroul limits pushed away by 66 $wa, 66 $ha, 44 $wg, 44 $hg
    :wishprotect: +5,742 LVL of wish protection!
    :bku: +32% bku reset on starwishes

Now and then Mudae asks first, and only spends once ``y`` is sent back::

    Do you want to spend 6,000,000:kakera:? (y/n/yes/no)

Only the ``:morekakera:`` line is read: it is the refund the macro adds back to
its running balance. The other rewards are left alone.

**Classified ahead of ``$bonus`` and ``$us``.** ``is_bonus_response`` matches
any ``<:morekakera:`` and ``is_us_response`` any "rolls stacked", so before this
module a hand-typed ``$kl`` result was parsed as a ``$bonus`` sheet. A chaos
kakera claim also prints loot lines, but it carries ``($k)`` and is parsed as a
claim before command detection runs.

``$lk`` (not a bare ``$kl``, which fails) shows the Kakeraloots profile; nothing
here reads it.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.chaos import flatten_chaos_text
from mudae.types import MessageKind, ParseResult

_SPEND_PROMPT_RE = re.compile(
    r"do\s+you\s+want\s+to\s+spend\s+([\d,]+)\s*(?::kakera:)?\s*\?", re.IGNORECASE
)
_CONFIRM_RE = re.compile(r"\(\s*y\s*/\s*n\b", re.IGNORECASE)
_MORE_KAKERA_RE = re.compile(r":morekakera:\s*\+\s*([\d,]+)\s*kakera", re.IGNORECASE)
# Any one of these marks a loot result. A bare ``$us`` reads "You have N rolls
# stacked" with no ``+``, so the signed form does not take it.
_RESULT_MARKERS = (
    _MORE_KAKERA_RE,
    re.compile(r"\+\s*[\d,.]+\s*rolls?\s+stacked", re.IGNORECASE),
    re.compile(r"limits\s+pushed\s+away", re.IGNORECASE),
    re.compile(r"LVL\s+of\s+wish\s+protection", re.IGNORECASE),
    re.compile(r"bku\s+reset\s+on\s+starwishes", re.IGNORECASE),
)


def is_kakeraloot_prompt(content: str) -> bool:
    """The "Do you want to spend …? (y/n)" question."""
    flat = flatten_chaos_text(content)
    return bool(_SPEND_PROMPT_RE.search(flat) and _CONFIRM_RE.search(flat))


def is_kakeraloot_result(content: str) -> bool:
    if not content or "($k)" in content.lower():
        return False
    flat = flatten_chaos_text(content)
    if is_kakeraloot_prompt(content):
        return False
    return any(marker.search(flat) for marker in _RESULT_MARKERS)


def is_kakeraloot_message(content: str) -> bool:
    return is_kakeraloot_prompt(content) or is_kakeraloot_result(content)


def parse_kakeraloot(content: str) -> ParseResult:
    flat = flatten_chaos_text(content)
    fields: dict[str, Any] = {}

    if is_kakeraloot_prompt(content):
        fields["kl_outcome"] = "prompt"
        spend = _SPEND_PROMPT_RE.search(flat)
        if spend:
            fields["kl_spend"] = int(spend.group(1).replace(",", ""))
        amount = fields.get("kl_spend")
        return ParseResult(
            kind=MessageKind.KAKERALOOT_PROMPT,
            summary=f"$kl · confirm {amount:,}?" if amount else "$kl · confirm?",
            fields=fields,
        )

    if is_kakeraloot_result(content):
        more = _MORE_KAKERA_RE.search(flat)
        gained = int(more.group(1).replace(",", "")) if more else 0
        fields["kl_outcome"] = "result"
        fields["kl_kakera_gained"] = gained
        return ParseResult(
            kind=MessageKind.KAKERALOOT_RESULT,
            summary=f"$kl · +{gained:,} kakera",
            fields=fields,
        )

    # Paired with a ``$kl`` we sent but neither shape: a refusal, a syntax
    # reply, or someone else's message that arrived first.
    fields["kl_outcome"] = "unknown"
    return ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary="$kl · unrecognised reply",
        fields=fields,
        warnings=["Unrecognised $kl reply"],
    )
