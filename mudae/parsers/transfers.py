"""Mudae's ``$give`` / ``$givek`` / ``$givesp`` exchanges.

Captured live on 2026-11-05 (alt ``lukijade`` → main ``<@554009750375890945>``),
saved in ``data/alts_log.json``.

**A character** — the *receiver* confirms::

    $give <@554009750375890945> Anna (PC)
    <@554009750375890945>, **lukijade** wants to give you **Anna (PC)**. Do you confirm? (y/n/yes/no)
    (Enhanced multitrade: this gift is free)
    y                                   ← typed by the receiver
    **Anna (PC)** given to <@554009750375890945>

**Kakera / spheres** — the *giver* confirms::

    $givek <@554009750375890945> 1000
    **lukijade**, do you really want to give **1,000<:kakera:469835869059153940>**? (y/n/yes/no)
    y                                   ← typed by the giver
    <@1410311771092422777> just gifted **1,000**<:kakera:469835869059153940>to <@554009750375890945>

    $givesp <@554009750375890945> 100
    **lukijade**, do you really want to give **100 <:sp:1437140700604137554> **? (y/n/yes/no)
    <@1410311771092422777> just gifted **100** <:sp:1437140700604137554> to <@554009750375890945>

Note the names: the prompts use the giver's Discord **username** (``lukijade``), the
results use Discord **ids**. The giver's Discord display name
("you guys played sekiro?") appears nowhere.

**None of these are claims.** The ``$give`` prompt carries two bold runs, and
two bold runs is all ``claim.is_custom_claim`` asks for — before this module
it classified as ``CLAIM`` with ``winner="lukijade"``, which could satisfy a
waiter that expects a real claim confirmation.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

_CONFIRM_RE = re.compile(r"\(\s*y\s*/\s*n\b", re.IGNORECASE)
_GIVE_PROMPT_RE = re.compile(
    r"<@!?(?P<to>\d+)>\s*,\s*\*\*(?P<giver>[^*\n]+?)\*\*\s+wants\s+to\s+give\s+you\s+"
    r"\*\*(?P<character>[^*\n]+?)\*\*",
    re.IGNORECASE,
)
_AMOUNT_PROMPT_RE = re.compile(
    r"\*\*(?P<giver>[^*\n]+?)\*\*\s*,\s*do\s+you\s+really\s+want\s+to\s+give\s+"
    r"\*\*\s*(?P<amount>[\d,]+)\s*(?P<emoji><a?:(?P<name>\w+):\d+>)",
    re.IGNORECASE,
)
_GIVE_RESULT_RE = re.compile(
    r"\*\*(?P<character>[^*\n]+?)\*\*\s+given\s+to\s+<@!?(?P<to>\d+)>",
    re.IGNORECASE,
)
_GIFT_RESULT_RE = re.compile(
    r"<@!?(?P<from>\d+)>\s+just\s+gifted\s+\*\*\s*(?P<amount>[\d,]+)\s*\*\*\s*"
    r"(?P<emoji><a?:(?P<name>\w+):\d+>)\s*to\s+<@!?(?P<to>\d+)>",
    re.IGNORECASE,
)
_FREE_RE = re.compile(r"this\s+gift\s+is\s+free", re.IGNORECASE)

KIND_CHARACTER = "character"
KIND_KAKERA = "kakera"
KIND_SPHERES = "spheres"


def _currency(emoji_name: str) -> str | None:
    name = (emoji_name or "").lower()
    if name == "kakera":
        return KIND_KAKERA
    if name == "sp":
        return KIND_SPHERES
    return None


def _int(raw: str) -> int:
    return int(raw.replace(",", ""))


def is_transfer_prompt(content: str) -> bool:
    text = content or ""
    if not _CONFIRM_RE.search(text):
        return False
    if _GIVE_PROMPT_RE.search(text):
        return True
    match = _AMOUNT_PROMPT_RE.search(text)
    return bool(match and _currency(match.group("name")))


def is_transfer_result(content: str) -> bool:
    text = content or ""
    if _GIVE_RESULT_RE.search(text):
        return True
    match = _GIFT_RESULT_RE.search(text)
    return bool(match and _currency(match.group("name")))


def is_transfer_message(content: str) -> bool:
    return is_transfer_prompt(content) or is_transfer_result(content)


def parse_transfer(content: str) -> ParseResult:
    """``transfer`` is character / kakera / spheres.

    Prompt fields: ``giver_name``, and ``recipient_id`` + ``character`` (+
    ``free``) for a character, ``amount`` for kakera and spheres.
    Result fields: ``recipient_id``, and ``character`` or ``giver_id`` +
    ``amount``.
    """
    text = content or ""
    fields: dict[str, Any] = {}

    if is_transfer_prompt(text):
        give = _GIVE_PROMPT_RE.search(text)
        if give:
            character = strip_markdown(give.group("character")).strip()
            fields.update(
                transfer=KIND_CHARACTER,
                recipient_id=give.group("to"),
                giver_name=give.group("giver").strip(),
                character=character,
                free=bool(_FREE_RE.search(text)),
            )
            summary = f"$give · {fields['giver_name']} → {character}? (receiver confirms)"
        else:
            amount = _AMOUNT_PROMPT_RE.search(text)
            assert amount is not None
            fields.update(
                transfer=_currency(amount.group("name")),
                giver_name=amount.group("giver").strip(),
                amount=_int(amount.group("amount")),
            )
            summary = f"$give{'k' if fields['transfer'] == KIND_KAKERA else 'sp'} · {fields['giver_name']} gives {fields['amount']:,}? (giver confirms)"
        return ParseResult(kind=MessageKind.TRANSFER_PROMPT, summary=summary, fields=fields)

    give = _GIVE_RESULT_RE.search(text)
    if give:
        fields.update(
            transfer=KIND_CHARACTER,
            character=strip_markdown(give.group("character")).strip(),
            recipient_id=give.group("to"),
        )
        summary = f"$give · {fields['character']} given"
        return ParseResult(kind=MessageKind.TRANSFER_RESULT, summary=summary, fields=fields)

    gift = _GIFT_RESULT_RE.search(text)
    if gift and _currency(gift.group("name")):
        fields.update(
            transfer=_currency(gift.group("name")),
            giver_id=gift.group("from"),
            recipient_id=gift.group("to"),
            amount=_int(gift.group("amount")),
        )
        summary = f"gift · {fields['amount']:,} {fields['transfer']}"
        return ParseResult(kind=MessageKind.TRANSFER_RESULT, summary=summary, fields=fields)

    return ParseResult(
        kind=MessageKind.UNKNOWN,
        summary="Unknown transfer message",
        fields={"content": text},
        warnings=["Not a transfer prompt or result"],
    )
