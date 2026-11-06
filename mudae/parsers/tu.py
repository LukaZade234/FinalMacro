"""Parse Mudae $tu plain-text responses."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.dk import extract_dk_fields
from mudae.parsers.reaction_power import parse_reaction_power_fields
from mudae.parsers.utils import extract_bold_minutes, parse_hours_minutes
from mudae.parsers.ohu import parse_minigame_availability
from mudae.parsers.ohu8 import parse_refill_minutes
from mudae.types import MessageKind, ParseResult

_CLAIM_CAN_RE = re.compile(r"you __can__ claim(?:\s+right now)?!?", re.IGNORECASE)
_CLAIM_CAN_PT_RE = re.compile(r"você __pode__ se casar", re.IGNORECASE)
_CANT_CLAIM_EN_RE = re.compile(
    r"can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min",
    re.IGNORECASE,
)
_CANT_CLAIM_PT_RE = re.compile(
    r"calma aí.*\*\*(\d+h)?\s*(\d+)\*\* min",
    re.IGNORECASE,
)
_ROLLS_LEFT_RE = re.compile(
    r"(?:you have|você tem)\s*\*{0,2}([\d,.]+)\*{0,2}\s*rolls?"
    r"(?:\s*\(\+\*{0,2}([\d,.]+)\*{0,2}\s*\$(mk|smk|us|ru)\))?"
    r"\s*(?:left|restantes)?",
    re.IGNORECASE,
)
_DIGITS_ONLY_RE = re.compile(r"[^\d]")
# "**lukazade234**, you __can__ claim…" — whose $tu this is: the account's
# Discord *username* (not its display name). With alts in the channel several
# accounts' $tu replies arrive in the same place.
_TU_USER_RE = re.compile(r"^\s*\*\*(?P<user>[^*\n]+?)\*\*\s*,")
_TU_USER_PLAIN_RE = re.compile(r"^\s*(?P<user>[^\s*,][^,\n]{0,40}?)\s*,\s*you\b", re.IGNORECASE)
_DK_COUNT_RE = re.compile(
    r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|ready|dispon)",
    re.IGNORECASE,
)
# The wording follows the account's $dk capacity: an account that can hold
# several says "**2** $dk available" (the main), one that holds a single
# use says "$dk is ready!" (the alts, 2026-11-05) — stock 1.
_DK_AVAILABLE_RE = re.compile(r"\$dk\s+(?:is\s+)?(?:available|ready)", re.IGNORECASE)
# A full $tu (one not trimmed with $tuarrange) also carries both balances,
# each on a "Stock:" line — kakera under the power block, spheres under the
# minigame counts — plus $daily and vote status. Rolled-up stacks print
# "(Stock: 22,946.4)" in parentheses; those are not balances.
_STOCK_LINE_RE = re.compile(
    r"(?<!\()\bstock:\s*\*{0,2}(?P<n>[\d,]+)(?![\d.])\*{0,2}\s*(?P<emoji><a?:(?P<name>\w+):\d+>|:(?P<short>\w+):)?",
    re.IGNORECASE,
)
_DAILY_READY_RE = re.compile(r"\$daily\s+is\s+available", re.IGNORECASE)
_VOTE_READY_RE = re.compile(r"you\s+may\s+vote\s+right\s+now", re.IGNORECASE)
_DK_DISPON_RE = re.compile(r"\$dk\s+dispon", re.IGNORECASE)


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
    user = _TU_USER_RE.match(content or "") or _TU_USER_PLAIN_RE.match(content or "")
    if user:
        fields["tu_user"] = user.group("user").strip()

    # 1. Claim available now
    if _CLAIM_CAN_RE.search(lower):
        fields["claim_available"] = True
    elif _CLAIM_CAN_PT_RE.search(lower):
        fields["claim_available"] = True
    else:
        cant_claim_en = _CANT_CLAIM_EN_RE.search(lower)
        cant_claim_pt = _CANT_CLAIM_PT_RE.search(lower)
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
    rolls_match = _ROLLS_LEFT_RE.search(lower)
    if rolls_match:
        fields["rolls_left"] = int(_DIGITS_ONLY_RE.sub("", rolls_match.group(1)))
        bonus_raw = rolls_match.group(2)
        currency = rolls_match.group(3)
        if bonus_raw and currency:
            bonus = int(_DIGITS_ONLY_RE.sub("", bonus_raw))
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

    daily_reset = _minutes_after_phrase(content, "next $daily reset")
    if daily_reset is not None:
        fields["daily_reset_minutes"] = daily_reset

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
    dk_count = _DK_COUNT_RE.search(lower)
    if dk_count:
        fields["dk_stock"] = int(dk_count.group(1))
    elif _DK_AVAILABLE_RE.search(lower) or _DK_DISPON_RE.search(lower):
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

    # 8. The full layout's extras: balances, minigames, $daily, vote.
    fields.update(_parse_stocks(content))
    if "$oh left for today" in lower:
        fields.update(parse_minigame_availability(content))
    if _DAILY_READY_RE.search(content):
        fields["daily_available"] = True
    elif "daily_reset_minutes" in fields:
        fields["daily_available"] = False
    if _VOTE_READY_RE.search(content):
        fields["vote_available"] = True

    summary = _build_summary(fields)
    return ParseResult(kind=MessageKind.TU, summary=summary, fields=fields, warnings=warnings)


def _parse_stocks(content: str) -> dict[str, int]:
    """``kakera_stock`` / ``sphere_stock`` from the full ``$tu``'s Stock lines.

    The emoji says which is which. Copied text loses custom emojis, so without
    one the position decides: a Stock line after the minigame counts is the
    sphere balance, one after the power line is the kakera balance.
    """
    fields: dict[str, int] = {}
    lower = (content or "").lower()
    games_at = lower.find("$oh left for today")
    power_at = lower.find("power:")
    for match in _STOCK_LINE_RE.finditer(content or ""):
        name = (match.group("name") or match.group("short") or "").lower()
        if name == "kakera":
            key = "kakera_stock"
        elif name == "sp":
            key = "sphere_stock"
        elif name:
            continue
        elif games_at >= 0 and match.start() > games_at:
            key = "sphere_stock"
        elif power_at >= 0 and match.start() > power_at:
            key = "kakera_stock"
        else:
            continue
        fields.setdefault(key, int(match.group("n").replace(",", "")))
    return fields


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
