"""Parse Mudae ``$ohu`` / shared ``$ohu8`` header for minigame availability."""

from __future__ import annotations

import re
from typing import Any

from mudae.types import MessageKind, ParseResult

# ``4 $oh left for today (+3 stored)`` or ``4 $oh left for today``
_OH_LEFT_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*\$oh\s+left\s+for\s+today"
    r"(?:\s*\(\+\*{0,2}(\d+)\*{0,2}\s*stored\))?",
    re.IGNORECASE,
)
# ``2 $oc (+2 stored)`` / ``0 $oc``
_OC_LEFT_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*\$oc"
    r"(?:\s*\(\+\*{0,2}(\d+)\*{0,2}\s*stored\))?",
    re.IGNORECASE,
)
_OQ_LEFT_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*\$oq"
    r"(?:\s*\(\+\*{0,2}(\d+)\*{0,2}\s*stored\))?",
    re.IGNORECASE,
)
_OT_LEFT_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*\$ot"
    r"(?:\s*\(\+\*{0,2}(\d+)\*{0,2}\s*stored\))?",
    re.IGNORECASE,
)

# First $oh of the day can grant perk-10 bonuses from invested stock:
# ``+2 $oq and +5,344 <:sp:…> from your invested spheres!``
# ``+2 $oq, +1 $ot and +5,600 :sp: from your invested spheres!``
# Shared header on ``$ohu`` / ``$ohu8`` / ``$ohu9``: ``7/15 buttons clicked``.
_BUTTONS_CLICKED_RE = re.compile(
    r"\*{0,2}(\d+)\*{0,2}\s*/\s*\*{0,2}(\d+)\*{0,2}\s+buttons?\s+clicked",
    re.IGNORECASE,
)
_NO_MEGASPHERE_RE = re.compile(
    r"no\s+(?:<:spm:[^>]+>|:spm:)\s+left\s+today",
    re.IGNORECASE,
)
_STOCK_RE = re.compile(
    r"stock:\s*\*{0,2}([\d,]+)\*{0,2}\s*(?:<:sp:|:sp:)",
    re.IGNORECASE,
)

_INVESTED_ANCHOR_RE = re.compile(
    r"from your invested spheres",
    re.IGNORECASE,
)
_OQ_BONUS_RE = re.compile(
    r"\*{0,2}\+\*{0,2}(\d+)\*{0,2}\s*\$oq",
    re.IGNORECASE,
)
_OT_BONUS_RE = re.compile(
    r"\*{0,2}\+\*{0,2}(\d+)\*{0,2}\s*\$ot",
    re.IGNORECASE,
)
_SP_BONUS_RE = re.compile(
    r"\*{0,2}\+\*{0,2}([\d,]+)\*{0,2}\s*(?:<:sp:|:sp:)",
    re.IGNORECASE,
)


def _pair(match: re.Match[str] | None) -> tuple[int, int] | None:
    if match is None:
        return None
    left = int(match.group(1))
    stored = int(match.group(2)) if match.group(2) is not None else 0
    return left, stored


def parse_minigame_availability(content: str) -> dict[str, int]:
    """Return left/stored/total counts for ``$oh``/``$oc``/``$oq``/``$ot``.

    Totals are ``left + stored`` (what the user can spend with ``$oh N`` etc.).
    Missing games default to 0.
    """
    fields: dict[str, int] = {}
    for game_id, pattern in (
        ("oh", _OH_LEFT_RE),
        ("oc", _OC_LEFT_RE),
        ("oq", _OQ_LEFT_RE),
        ("ot", _OT_LEFT_RE),
    ):
        pair = _pair(pattern.search(content or ""))
        if pair is None:
            fields[f"{game_id}_left"] = 0
            fields[f"{game_id}_stored"] = 0
            fields[f"{game_id}_total"] = 0
            continue
        left, stored = pair
        fields[f"{game_id}_left"] = left
        fields[f"{game_id}_stored"] = stored
        fields[f"{game_id}_total"] = left + stored
    return fields


def parse_perk9_buttons(content: str) -> tuple[int, int] | None:
    """Return ``(clicked, max)`` from ``7/15 buttons clicked`` (perk 9, not perk 8)."""
    if not content:
        return None
    match = _BUTTONS_CLICKED_RE.search(content)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_megasphere_left(content: str) -> bool | None:
    """``False`` when ``$ohu`` says no megaspheres left today; else ``None``."""
    if not content:
        return None
    if _NO_MEGASPHERE_RE.search(content):
        return False
    return None


def parse_sphere_stock(content: str) -> int | None:
    """``:sp:`` inventory from the ``Stock: 3,924 :sp:`` line."""
    if not content:
        return None
    match = _STOCK_RE.search(content)
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


def parse_oh_invested_bonus(content: str) -> dict[str, int]:
    """Parse perk-10 ``$oq`` / ``$ot`` / SP on the first ``$oh`` of the day."""
    empty = {"oq_bonus": 0, "ot_bonus": 0, "spheres_bonus": 0}
    if not content:
        return empty
    anchor = _INVESTED_ANCHOR_RE.search(content)
    if anchor is None:
        return empty
    head = content[: anchor.end()]
    oq = _OQ_BONUS_RE.search(head)
    ot = _OT_BONUS_RE.search(head)
    spheres = _SP_BONUS_RE.search(head)
    return {
        "oq_bonus": int(oq.group(1)) if oq else 0,
        "ot_bonus": int(ot.group(1)) if ot else 0,
        "spheres_bonus": int(spheres.group(1).replace(",", "")) if spheres else 0,
    }


def is_ohu_response(content: str) -> bool:
    """True for ``$ohu`` / the shared availability header on ``$ohu8``."""
    lower = (content or "").lower()
    return "$oh left for today" in lower


def parse_ohu(content: str) -> ParseResult:
    from mudae.parsers.ohu8 import parse_refill_minutes

    warnings: list[str] = []
    fields: dict[str, Any] = dict(parse_minigame_availability(content))

    if not is_ohu_response(content):
        warnings.append("Could not parse minigame availability line")

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

    summary = "$ohu"
    parts = [
        f"$oh {fields['oh_total']}",
        f"$oc {fields['oc_total']}",
        f"$oq {fields['oq_total']}",
        f"$ot {fields['ot_total']}",
    ]
    summary += " · " + " · ".join(parts)
    if refill is not None:
        h, m = divmod(refill, 60)
        summary += f" · refill {h}h {m}m" if h else f" · refill {m}m"

    return ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
