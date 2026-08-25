"""Parse extra lines on a chaos-kakera (``kakeraC``) claim.

The kakera payout and bonus SP are handled by ``parse_kakera_claim``. This
module reads the rest of the same Mudae message: extra rolls this hour,
stored minigames, kakeraloots, power discount, omega keys, owned-character
free kakera, and wishlist spawns.

Perk-5 ``(Shop 5) +1 $ot stored!`` can appear on any kakera react and is
recorded separately — it is not a chaos reward.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mudae.parsers.utils import strip_markdown

_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_KAKERA_C_RE = re.compile(r":kakeraC:", re.IGNORECASE)
_ROLLS_HOUR_RE = re.compile(r"\+(\d+)\s+rolls?\s+this hour", re.IGNORECASE)
_STORED_RE = re.compile(r"\+1\s+\$(oh|oc|oq|ot)\s+stored", re.IGNORECASE)
_SHOP5_OT_RE = re.compile(r"\(Shop\s*5\)\s*\+1\s+\$ot\s+stored", re.IGNORECASE)
_LOOT_ONE_RE = re.compile(r"A\s+kakeraloot\s+spawned", re.IGNORECASE)
_LOOT_N_RE = re.compile(r"(\d+)\s+kakeraloots?\s+spawned", re.IGNORECASE)
_DISCOUNT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*kakera power discount",
    re.IGNORECASE,
)
_OMEGA_RE = re.compile(
    r"\+(\d+)\s*:omegakey:\s*\(\$ok\)",
    re.IGNORECASE,
)
_FREE_KAKERA_RE = re.compile(
    r"(\d+)\s+free kakera buttons?",
    re.IGNORECASE,
)
_WISH_SPAWN_RE = re.compile(
    r"A\s+wish\s+from your wishlist spawned",
    re.IGNORECASE,
)
_STACKED_RE = re.compile(
    r"\+([\d.]+)\s+rolls stacked",
    re.IGNORECASE,
)
_LOOT_KA_RE = re.compile(r":morekakera:\s*\+(\d+)\s+kakera", re.IGNORECASE)
_WISHPROTECT_RE = re.compile(
    r"\+(\d+)\s+LVL of wish protection",
    re.IGNORECASE,
)
_KA_PAYOUT_RE = re.compile(r"\+\s*[\d,]+\s*\(\$k\)", re.IGNORECASE)
_SP_LINE_RE = re.compile(r"\+\s*\d+\s*:sp:", re.IGNORECASE)


def flatten_chaos_text(text: str) -> str:
    """``<:kakeraC:id> **+5**`` → ``:kakeraC: +5``."""
    flat = _CUSTOM_EMOJI_RE.sub(r":\1:", text or "")
    return strip_markdown(flat)


def is_chaos_claim_content(content: str) -> bool:
    """True when this ``+$k`` message is a chaos-kakera follow-up."""
    if not content or "($k)" not in content.lower():
        return False
    return bool(_KAKERA_C_RE.search(flatten_chaos_text(content)))


@dataclass
class ChaosRewards:
    rolls_this_hour: int = 0
    minigames: dict[str, int] = field(default_factory=dict)
    shop_perk5_ot: int = 0
    kakeraloots: int = 0
    kakeraloot_stacked: float | None = None
    kakeraloot_kakera: int | None = None
    wish_protect_levels: int | None = None
    loot_rows: list[str] = field(default_factory=list)
    power_discount_pct: float | None = None
    omega_keys: int = 0
    free_kakera: int = 0
    wish_spawn: bool = False
    unparsed: list[str] = field(default_factory=list)

    def has_extras(self) -> bool:
        return bool(
            self.rolls_this_hour
            or self.minigames
            or self.shop_perk5_ot
            or self.kakeraloots
            or self.kakeraloot_stacked
            or self.kakeraloot_kakera
            or self.wish_protect_levels
            or self.loot_rows
            or self.power_discount_pct
            or self.omega_keys
            or self.free_kakera
            or self.wish_spawn
            or self.unparsed
        )

    def to_fields(self) -> dict[str, Any]:
        if not self.has_extras():
            return {}
        out: dict[str, Any] = {}
        if self.rolls_this_hour:
            out["chaos_rolls_this_hour"] = self.rolls_this_hour
        if self.minigames:
            out["chaos_minigames"] = dict(self.minigames)
        if self.shop_perk5_ot:
            out["shop_perk5_ot"] = self.shop_perk5_ot
        if self.kakeraloots:
            out["chaos_kakeraloots"] = self.kakeraloots
        if self.kakeraloot_stacked is not None:
            out["chaos_kakeraloot_stacked"] = self.kakeraloot_stacked
        if self.kakeraloot_kakera is not None:
            out["chaos_kakeraloot_kakera"] = self.kakeraloot_kakera
        if self.wish_protect_levels is not None:
            out["chaos_wish_protect_levels"] = self.wish_protect_levels
        if self.loot_rows:
            out["chaos_loot_rows"] = list(self.loot_rows)
        if self.power_discount_pct is not None:
            out["chaos_power_discount_pct"] = self.power_discount_pct
        if self.omega_keys:
            out["chaos_omega_keys"] = self.omega_keys
        if self.free_kakera:
            out["chaos_free_kakera"] = self.free_kakera
        if self.wish_spawn:
            out["chaos_wish_spawn"] = True
        if self.unparsed:
            out["chaos_unparsed"] = list(self.unparsed)
        return out


def parse_chaos_rewards(content: str) -> ChaosRewards:
    """Extract chaos extras from a kakera-claim body. Empty when not chaos.

    Perk-5 ``(Shop 5) +1 $ot stored!`` is recorded even on non-chaos reacts.
    """
    rewards = ChaosRewards()
    text = flatten_chaos_text(content)
    if not is_chaos_claim_content(content):
        rewards.shop_perk5_ot = len(_SHOP5_OT_RE.findall(text))
        return rewards
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _classify_line(line, rewards):
            continue
        if _KAKERA_C_RE.search(line) and not _KA_PAYOUT_RE.search(line) and not _SP_LINE_RE.search(line):
            rewards.unparsed.append(line)
    return rewards


def _classify_line(line: str, rewards: ChaosRewards) -> bool:
    if _SHOP5_OT_RE.search(line):
        rewards.shop_perk5_ot += 1
        return True
    if _KAKERA_C_RE.search(line):
        hour = _ROLLS_HOUR_RE.search(line)
        if hour:
            rewards.rolls_this_hour += int(hour.group(1))
            return True
        stored = _STORED_RE.search(line)
        if stored:
            key = stored.group(1).lower()
            rewards.minigames[key] = rewards.minigames.get(key, 0) + 1
            return True
        if _LOOT_ONE_RE.search(line):
            rewards.kakeraloots += 1
            return True
        loot_n = _LOOT_N_RE.search(line)
        if loot_n:
            rewards.kakeraloots += int(loot_n.group(1))
            return True
        discount = _DISCOUNT_RE.search(line)
        if discount:
            rewards.power_discount_pct = float(discount.group(1))
            return True
        omega = _OMEGA_RE.search(line)
        if omega:
            rewards.omega_keys += int(omega.group(1))
            return True
        free = _FREE_KAKERA_RE.search(line)
        if free:
            rewards.free_kakera += int(free.group(1))
            return True
        if _WISH_SPAWN_RE.search(line):
            rewards.wish_spawn = True
            return True
        if _KA_PAYOUT_RE.search(line) or _SP_LINE_RE.search(line):
            return True
        return False
    stacked = _STACKED_RE.search(line)
    if stacked:
        rewards.kakeraloot_stacked = float(stacked.group(1))
        return True
    loot_ka = _LOOT_KA_RE.search(line)
    if loot_ka:
        rewards.kakeraloot_kakera = int(loot_ka.group(1))
        return True
    wishprotect = _WISHPROTECT_RE.search(line)
    if wishprotect:
        rewards.wish_protect_levels = int(wishprotect.group(1))
        return True
    if line.startswith(":") and ":" in line[1:]:
        rewards.loot_rows.append(line)
        return True
    return False


def chaos_summary_bits(rewards: ChaosRewards) -> list[str]:
    bits: list[str] = []
    if rewards.rolls_this_hour:
        bits.append(f"+{rewards.rolls_this_hour} rolls")
    for name, count in rewards.minigames.items():
        bits.append(f"+{count} ${name}")
    if rewards.kakeraloots:
        bits.append(f"{rewards.kakeraloots} kakeraloot")
    if rewards.power_discount_pct is not None:
        bits.append(f"{rewards.power_discount_pct:g}% power off")
    if rewards.omega_keys:
        bits.append(f"+{rewards.omega_keys} omega")
    if rewards.free_kakera:
        bits.append(f"{rewards.free_kakera} free kakera")
    if rewards.wish_spawn:
        bits.append("wish spawn")
    if rewards.shop_perk5_ot:
        bits.append("shop5 $ot")
    return bits
