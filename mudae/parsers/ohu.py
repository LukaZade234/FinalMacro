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

# First $oh of the day can grant bonus $oq (and spheres) from invested stock:
# ``+2 $oq and +5,344 <:sp:…> from your invested spheres!``
_INVESTED_BONUS_RE = re.compile(
    r"\*{0,2}\+\*{0,2}(\d+)\*{0,2}\s*\$oq"
    r"(?:\s+and\s+\*{0,2}\+\*{0,2}([\d,]+)\*{0,2})?"
    r".*?from your invested spheres",
    re.IGNORECASE | re.DOTALL,
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


def parse_oh_invested_bonus(content: str) -> dict[str, int]:
    """Parse ``+N $oq and +M sp from your invested spheres!`` on an ``$oh`` grid."""
    match = _INVESTED_BONUS_RE.search(content or "")
    if match is None:
        return {"oq_bonus": 0, "spheres_bonus": 0}
    oq_bonus = int(match.group(1))
    spheres_raw = match.group(2)
    spheres_bonus = int(spheres_raw.replace(",", "")) if spheres_raw else 0
    return {"oq_bonus": oq_bonus, "spheres_bonus": spheres_bonus}


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
