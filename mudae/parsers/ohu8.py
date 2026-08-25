"""Parse Mudae ``$ohu8`` perk-8 daily status responses."""

from __future__ import annotations

import re

from typing import Any

from mudae.parsers.ohu import (
    parse_megasphere_left,
    parse_minigame_availability,
    parse_perk9_buttons,
    parse_sphere_stock,
)
from mudae.types import MessageKind, ParseResult

_PERK8_CLICKED_RE = re.compile(
    r"\(perk\s*8\)\s*clicked today:\s*\*{0,2}(\d+)\*{0,2}/(\d+)",
    re.IGNORECASE,
)
_PERK8_CLICKED_ALT_RE = re.compile(
    r"(?:\(perk\s*8\)\s*)?clicked today:?\s*\*{0,2}(\d+)\*{0,2}/(\d+)",
    re.IGNORECASE,
)
_PERK8_ROLLED_RE = re.compile(
    r"rolled today:\s*\*{0,2}(\d+)\*{0,2}/(\d+)",
    re.IGNORECASE,
)
_REFILL_HM_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*h\s*\*{0,2}(\d+)\*{0,2}\s*min\s+before the refill",
    re.IGNORECASE,
)
_REFILL_H_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*h(?:ours?)?\s+before the refill",
    re.IGNORECASE,
)
_REFILL_M_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*min(?:ute)?s?\s+before the refill",
    re.IGNORECASE,
)
# Exhausted-minigame form: ``Time to wait before the refill: 3h 08 min.``
_REFILL_AFTER_HM_RE = re.compile(
    r"before the refill:\s*\*{0,2}(\d+)\*{0,2}\s*h\s*\*{0,2}(\d+)\*{0,2}\s*min",
    re.IGNORECASE,
)
_REFILL_AFTER_H_RE = re.compile(
    r"before the refill:\s*\*{0,2}(\d+)\*{0,2}\s*h(?:ours?)?(?!\s*\*{0,2}\d)",
    re.IGNORECASE,
)
_REFILL_AFTER_M_RE = re.compile(
    r"before the refill:\s*\*{0,2}(\d+)\*{0,2}\s*min(?:ute)?s?",
    re.IGNORECASE,
)

_OHU8_NEW_SAMPLE = (
    "0 $oh left for today, 0 $oc, 0 $oq and 0 $ot (+1 stored).\n"
    "8h 28 min before the refill. 3/15 buttons clicked.\n"
    "Next :spM: has 0% chance to be free.\n"
    "Stock: 2,001 :sp:"
)


def parse_refill_minutes(content: str) -> int | None:
    """Minutes until the daily refill, e.g. ``11h 09 min before the refill``."""
    if not content:
        return None
    match = _REFILL_HM_RE.search(content)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = _REFILL_H_RE.search(content)
    if match:
        return int(match.group(1)) * 60
    match = _REFILL_M_RE.search(content)
    if match:
        return int(match.group(1))
    match = _REFILL_AFTER_HM_RE.search(content)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = _REFILL_AFTER_H_RE.search(content)
    if match:
        return int(match.group(1)) * 60
    match = _REFILL_AFTER_M_RE.search(content)
    if match:
        return int(match.group(1))
    return None


def parse_perk8_clicked(content: str) -> tuple[int, int] | None:
    """Return ``(clicked, max)`` from perk-8 click counters."""
    if not content:
        return None
    for pattern in (_PERK8_CLICKED_RE, _PERK8_CLICKED_ALT_RE):
        match = pattern.search(content)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def parse_perk8_rolled_pool(content: str) -> tuple[int, int] | None:
    """Return ``(rolled_today, pool_size)`` from ``Rolled today: **0**/0``."""
    if not content:
        return None
    match = _PERK8_ROLLED_RE.search(content)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_ohu8_response(content: str) -> bool:
    lower = (content or "").lower()
    if "before the refill" in lower and (
        "buttons clicked" in lower
        or "clicked today" in lower
        or "perk 8" in lower
        or "$oh left" in lower
    ):
        return True
    return "clicked today" in lower and "perk 8" in lower


def parse_ohu8(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = dict(parse_minigame_availability(content))

    clicked = parse_perk8_clicked(content)
    if clicked is not None:
        fields["perk8_clicked_today"], fields["perk8_click_max"] = clicked
    else:
        warnings.append("Could not parse perk 8 clicked today")

    rolled = parse_perk8_rolled_pool(content)
    if rolled is not None:
        fields["perk8_rolled_today"], fields["perk8_roll_pool"] = rolled
    else:
        warnings.append("Could not parse perk 8 rolled today")

    refill = parse_refill_minutes(content)
    if refill is not None:
        fields["perk8_refill_minutes"] = refill

    buttons = parse_perk9_buttons(content)
    if buttons is not None:
        fields["perk9_clicked_today"], fields["perk9_click_max"] = buttons
    megasphere_left = parse_megasphere_left(content)
    if megasphere_left is not None:
        fields["megasphere_left"] = megasphere_left
    stock = parse_sphere_stock(content)
    if stock is not None:
        fields["sphere_stock"] = stock

    summary = "$ohu8"
    if fields.get("oh_total") or fields.get("oc_total") or fields.get("oq_total"):
        summary += (
            f" · $oh {fields.get('oh_total', 0)}"
            f" · $oc {fields.get('oc_total', 0)}"
            f" · $oq {fields.get('oq_total', 0)}"
            f" · $ot {fields.get('ot_total', 0)}"
        )
    if clicked is not None:
        summary += f" · clicked {clicked[0]}/{clicked[1]}"
    if rolled is not None:
        summary += f" · rolled {rolled[0]}/{rolled[1]}"
    if refill is not None:
        h, m = divmod(refill, 60)
        summary += f" · refill {h}h {m}m" if h else f" · refill {m}m"

    return ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
