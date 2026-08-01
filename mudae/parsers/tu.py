"""Parse Mudae $tu plain-text responses."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.dk import extract_dk_fields
from mudae.parsers.reaction_power import parse_reaction_power_fields
from mudae.parsers.utils import extract_bold_minutes, parse_hours_minutes
from mudae.parsers.ohu8 import parse_refill_minutes
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

    # 3. Rolls (+ optional bonus pool: $mk / $smk monthly, or $us / $ru stacked).
    # Bonus rolls are usable immediately; "$us"/"$ru" come from the $us stack and
    # are wiped on the next rolls reset.
    rolls_match = re.search(
        r"(?:you have|você tem)\s*\*{0,2}([\d,.]+)\*{0,2}\s*rolls?"
        r"(?:\s*\(\+\*{0,2}([\d,.]+)\*{0,2}\s*\$(mk|smk|us|ru)\))?"
        r"\s*(?:left|restantes)?",
        lower,
    )
    if rolls_match:
        fields["rolls_left"] = int(re.sub(r"[^\d]", "", rolls_match.group(1)))
        bonus_raw = rolls_match.group(2)
        currency = rolls_match.group(3)
        if bonus_raw and currency:
            bonus = int(re.sub(r"[^\d]", "", bonus_raw))
            if currency in {"us", "ru"}:
                fields["rolls_us_bonus"] = bonus
            else:
                fields["rolls_mk_bonus"] = bonus
    else:
        warnings.append("Could not parse rolls left")

    # 4. Next rolls reset — "Next rolls reset in **26** min."
    roll_reset = _minutes_after_phrase(content, "next rolls reset")
    if roll_reset is None:
        roll_reset = _minutes_after_phrase(content, "próxima reinicialização")
    if roll_reset is not None:
        fields["rolls_reset_minutes"] = roll_reset

    refill = parse_refill_minutes(content)
    if refill is not None:
        fields["perk8_refill_minutes"] = refill

    fields.update(parse_reaction_power_fields(content))

    # 6. $rt — available line or cooldown timer (mutually exclusive in $tu).
    if "$rt is available" in lower or "$rt está pronto" in lower:
        fields["rt_available"] = True
    next_rt = _minutes_after_phrase(content, "next $rt in")
    if next_rt is None:
        next_rt = _minutes_after_phrase(content, "próximo $rt")
    if next_rt is not None:
        fields["rt_next_minutes"] = next_rt
        fields["rt_available"] = False

    # 7. $dk stock / recharge timer
    dk_count = re.search(r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|dispon)", lower)
    if dk_count:
        fields["dk_stock"] = int(dk_count.group(1))
    elif re.search(r"\$dk\s+(?:is\s+)?available", lower) or re.search(
        r"\$dk\s+dispon", lower
    ):
        fields["dk_stock"] = 1

    next_dk = _minutes_after_phrase(content, "next $dk in")
    if next_dk is not None:
        fields["dk_next_minutes"] = next_dk
        if "dk_stock" not in fields:
            fields["dk_stock"] = 0
    else:
        dk_idx = lower.find("$dk")
        if dk_idx >= 0:
            next_idx = lower.find("next in", dk_idx)
            if next_idx > dk_idx and "dk_stock" in fields:
                dk_next = extract_bold_minutes(content, start=next_idx, window=72)
                if dk_next is not None:
                    fields["dk_next_minutes"] = dk_next

    # Embedded ``$dk`` payout line (Mudae sometimes combines with ``$tu``).
    fields.update(extract_dk_fields(content))

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
    elif (rt_next := fields.get("rt_next_minutes")) is not None:
        h, m = divmod(rt_next, 60)
        parts.append(f"rt next {h}h {m}m" if h else f"rt next {m}m")

    dk = fields.get("dk_stock")
    if dk is not None:
        dk_txt = f"{dk} dk"
        if (dk_next := fields.get("dk_next_minutes")) is not None:
            h, m = divmod(dk_next, 60)
            dk_txt += f" (next {h}h {m}m)" if h else f" (next {m}m)"
        parts.append(dk_txt)
    elif (dk_next := fields.get("dk_next_minutes")) is not None:
        h, m = divmod(dk_next, 60)
        parts.append(f"dk next {h}h {m}m" if h else f"dk next {m}m")

    return " · ".join(parts)
