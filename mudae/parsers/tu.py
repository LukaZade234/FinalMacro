"""Parse Mudae $tu plain-text responses."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import extract_bold_minutes, parse_hours_minutes
from mudae.types import MessageKind, ParseResult


def _minutes_after_phrase(content: str, phrase: str, *, window: int = 72) -> int | None:
    lower = content.lower()
    idx = lower.find(phrase.lower())
    if idx < 0:
        return None
    return extract_bold_minutes(content, start=idx, window=window)


def parse_tu(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {}
    lower = content.lower()

    # 1. Claim available now
    if re.search(r"you __can__ claim(?:\s+right now)?!?", lower):
        fields["claim_available"] = True
    elif re.search(r"você __pode__ se casar", lower):
        fields["claim_available"] = True
    else:
        cant_claim_en = re.search(
            r"can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min", lower
        )
        cant_claim_pt = re.search(
            r"calma aí.*\*\*(\d+h)?\s*(\d+)\*\* min", lower
        )
        if cant_claim_en or cant_claim_pt:
            match = cant_claim_en or cant_claim_pt
            h, m = parse_hours_minutes(match)
            fields["claim_available"] = False
            fields["claim_cooldown_minutes"] = h * 60 + m
        else:
            fields["claim_available"] = None
            warnings.append("Could not determine claim availability")

    # 2. Next claim reset — "The next claim reset is in **26** min."
    claim_reset = _minutes_after_phrase(content, "next claim reset")
    if claim_reset is not None:
        fields["next_claim_reset_minutes"] = claim_reset

    # 3. Rolls (+ optional $mk / $smk bonus)
    rolls_match = re.search(
        r"(?:you have|você tem)\s*\*{0,2}([\d,.]+)\*{0,2}\s*rolls?"
        r"(?:\s*\(\+\*{0,2}([\d,.]+)\*{0,2}\s*\$(?:mk|smk)\))?"
        r"\s*(?:left|restantes)",
        lower,
    )
    if rolls_match:
        fields["rolls_left"] = int(re.sub(r"[^\d]", "", rolls_match.group(1)))
        if rolls_match.group(2):
            fields["rolls_mk_bonus"] = int(re.sub(r"[^\d]", "", rolls_match.group(2)))
    else:
        warnings.append("Could not parse rolls left")

    # 4. Next rolls reset — "Next rolls reset in **26** min."
    roll_reset = _minutes_after_phrase(content, "next rolls reset")
    if roll_reset is None:
        roll_reset = _minutes_after_phrase(content, "próxima reinicialização")
    if roll_reset is not None:
        fields["rolls_reset_minutes"] = roll_reset

    # 5. Power — "Power: **88%**"
    power_match = re.search(r"power:\s*\*\*(\d+)%\*\*", lower)
    if power_match:
        fields["power_percent"] = int(power_match.group(1))

    consumption_match = re.search(
        r"(?:each kakera reaction consumes|cada reação de kakera consume)\s*(\d+)%",
        lower,
    )
    if consumption_match:
        fields["power_consumption_percent"] = int(consumption_match.group(1))

    # 6. $rt — only set when explicitly mentioned
    if "$rt is available" in lower or "$rt está pronto" in lower:
        fields["rt_available"] = True

    # Kakera react (keep existing behaviour)
    if "you __can__ react to kakera" in lower or (
        "você __pode__" in lower and "kakera" in lower
    ):
        fields["kakera_react_available"] = True
    else:
        kakera_wait = re.search(
            r"can't react to kakera.*\*\*(\d+h)?\s*(\d+)\*\* min", lower
        )
        if kakera_wait:
            h, m = parse_hours_minutes(kakera_wait)
            fields["kakera_react_available"] = False
            fields["kakera_cooldown_minutes"] = h * 60 + m

    # 7. $dk — "**1** $dk available. Next in **8h 37** min."
    dk_count = re.search(r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|dispon)", lower)
    if dk_count:
        fields["dk_stock"] = int(dk_count.group(1))
    elif re.search(r"\$dk\s+(?:is\s+)?available", lower) or re.search(
        r"\$dk\s+dispon", lower
    ):
        fields["dk_stock"] = 1

    dk_idx = lower.find("$dk")
    if dk_idx >= 0:
        next_idx = lower.find("next in", dk_idx)
        if next_idx > dk_idx:
            dk_next = extract_bold_minutes(content, start=next_idx, window=72)
            if dk_next is not None:
                fields["dk_next_minutes"] = dk_next

    summary = _build_summary(fields)
    return ParseResult(kind=MessageKind.TU, summary=summary, fields=fields, warnings=warnings)


def _build_summary(fields: dict[str, Any]) -> str:
    parts: list[str] = ["$tu"]

    rolls = fields.get("rolls_left")
    if rolls is not None:
        roll_txt = f"{rolls} rolls"
        mk = fields.get("rolls_mk_bonus")
        if mk is not None:
            roll_txt += f" (+{mk} mk)"
        parts.append(roll_txt)

    claim = fields.get("claim_available")
    if claim is True:
        parts.append("can claim")
    elif claim is False:
        cd = fields.get("claim_cooldown_minutes")
        parts.append(f"claim cd {cd}m" if cd is not None else "claim on cooldown")

    if (reset := fields.get("next_claim_reset_minutes")) is not None:
        parts.append(f"claim reset {reset}m")

    if (reset := fields.get("rolls_reset_minutes")) is not None:
        parts.append(f"rolls reset {reset}m")

    if (power := fields.get("power_percent")) is not None:
        parts.append(f"power {power}%")

    if fields.get("rt_available"):
        parts.append("$rt ready")

    dk = fields.get("dk_stock")
    if dk is not None:
        dk_txt = f"{dk} dk"
        if (dk_next := fields.get("dk_next_minutes")) is not None:
            h, m = divmod(dk_next, 60)
            dk_txt += f" (next {h}h {m}m)" if h else f" (next {m}m)"
        parts.append(dk_txt)

    return " · ".join(parts)
