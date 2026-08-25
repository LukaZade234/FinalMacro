"""Parse Mudae ``$shop`` ouroperk upgrade sheets.

``$shop`` is a Components V2 message (empty classic content/embeds). The
snapshot layer flattens TextDisplay bodies before this parser runs.

One sheet, ten perks (OP1–OP10), each 0–10. ``[MAX]`` is level 10. Continuation
lines without a ``[LVL]`` / ``[MAX]`` tag belong to the previous perk (perk 6
omega-key chance, perk 9 sphere-value %).

Storage only. Do not change perk-9 click caps or send ``$shoprefund``.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.message_text import snapshot_visible_text
from mudae.parsers.shop_catalog import perk9_click_max
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

_ZW_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_HEAD_RE = re.compile(
    r"^\[\s*(?:\*\*)?\s*(?:LVL\s+(\d+)|MAX)\s*(?:\*\*)?\s*\]\s*(.*)$",
    re.IGNORECASE,
)
_PERK_RE = re.compile(r"\bperk\s+(\d+)\b", re.IGNORECASE)
_SPHERES_RE = re.compile(
    r"You have\s+([\d,]+)\s*(?::sp:|sp\b)?",
    re.IGNORECASE,
)
_COST_RE = re.compile(
    r"cost increased by \+?([\d,]+)\s*per level",
    re.IGNORECASE,
)
_LEVELS_RE = re.compile(r"Each bonus has\s+(\d+)\s+levels", re.IGNORECASE)
_PAIR_RE = re.compile(
    r"([+\-]?\d[\d,]*(?:\.\d+)?)(%)?\s*>\s*([+\-]?\d[\d,]*(?:\.\d+)?)(%)?"
)
_TAIL_RE = re.compile(r":\s*([+\-]?\d[\d,]*(?:\.\d+)?)(%)?\s*$")

SHOP_MAX_LEVEL = 10
SHOP_LEVEL_COST_STEP = 4000


def _normalize_shop_text(content: str) -> str:
    """Strip Discord chrome so ``[**LVL 5**]`` and ``**15,660** <:sp:id>`` parse."""
    text = _ZW_RE.sub("", content or "").replace("\r\n", "\n")
    text = strip_markdown(text)
    text = _CUSTOM_EMOJI_RE.sub(r":\1:", text)
    return text


def is_shop_response(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    if "upgrade bonuses given by ouroperks" in lower:
        return True
    if "$shoprefund" in lower and "perk 9" in lower:
        return True
    return ("[lvl" in lower or "[max]" in lower) and "perk 9" in lower


def _num(raw: str) -> int | float:
    text = raw.replace(",", "").replace("+", "").strip()
    if text.startswith("-"):
        signed = text[1:]
        if "." in signed:
            return -float(signed)
        return -int(signed)
    if "." in text:
        return float(text)
    return int(text)


def _values_from_block(block: str) -> list[tuple[int | float, int | float | None, bool]]:
    found: list[tuple[int | float, int | float | None, bool]] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pair = _PAIR_RE.search(line)
        if pair:
            found.append(
                (
                    _num(pair.group(1)),
                    _num(pair.group(3)),
                    bool(pair.group(2) or pair.group(4)),
                )
            )
            continue
        tail = _TAIL_RE.search(line)
        if tail:
            found.append((_num(tail.group(1)), None, bool(tail.group(2))))
    return found


def _level_from_head(match: re.Match[str]) -> tuple[int, bool]:
    if match.group(1) is None:
        return SHOP_MAX_LEVEL, True
    level = int(match.group(1))
    return level, level >= SHOP_MAX_LEVEL


def _perk_number(body: str) -> int | None:
    found = {int(match.group(1)) for match in _PERK_RE.finditer(body)}
    if len(found) == 1:
        return next(iter(found))
    if len(found) > 1:
        # Prefer the higher perk id when a line cross-references another perk.
        return max(found)
    lower = body.lower()
    if "first $oh" in lower or "120 characters max" in lower:
        return 10
    return None


def _split_perk_blocks(text: str) -> list[tuple[int, bool, str]]:
    blocks: list[tuple[int, bool, str]] = []
    current_level: int | None = None
    current_maxed = False
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_level, current_lines
        if current_level is None:
            current_lines = []
            return
        body = "\n".join(current_lines).strip()
        if body:
            blocks.append((current_level, current_maxed, body))
        current_lines = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = _HEAD_RE.match(line)
        if head:
            flush()
            current_level, current_maxed = _level_from_head(head)
            rest = (head.group(2) or "").strip()
            current_lines = [rest] if rest else []
            continue
        if current_level is None:
            continue
        current_lines.append(line)
    flush()
    return blocks


def _perk_payload(
    number: int,
    *,
    level: int,
    maxed: bool,
    values: list[tuple[int | float, int | float | None, bool]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"level": level, "maxed": maxed}
    current = [item[0] for item in values]
    nxt = [item[1] for item in values]

    def put(key: str, index: int) -> None:
        if index >= len(current):
            return
        payload[key] = current[index]
        next_key = f"next_{key}"
        if not maxed and index < len(nxt) and nxt[index] is not None:
            payload[next_key] = nxt[index]

    if number == 6:
        put("wishlist_claim_pct", 0)
        put("owned_omega_key_pct", 1)
    elif number == 9:
        put("extra_clicks", 0)
        put("sphere_value_pct", 1)
    elif number == 2:
        put("megasphere_rewards", 0)
    elif number == 1:
        put("spawn_share_pct", 0)
    elif number == 3:
        put("skip_blue_kakera_pct", 0)
    elif number == 4:
        put("omega_key_pct", 0)
    elif number == 5:
        put("ot_chance_pct", 0)
    elif number == 7:
        put("chaos_double_pct", 0)
    elif number == 8:
        put("kakera_boost_pct", 0)
    elif number == 10:
        put("ot_chance_pct", 0)
    else:
        put("value", 0)
    return payload


def parse_shop(content: str) -> ParseResult:
    text = _normalize_shop_text(content)
    fields: dict[str, Any] = {}
    warnings: list[str] = []

    spheres = _SPHERES_RE.search(text)
    if spheres:
        fields["spheres"] = int(spheres.group(1).replace(",", ""))
    cost = _COST_RE.search(text)
    fields["level_cost_step"] = (
        int(cost.group(1).replace(",", "")) if cost else SHOP_LEVEL_COST_STEP
    )
    levels = _LEVELS_RE.search(text)
    fields["max_level"] = int(levels.group(1)) if levels else SHOP_MAX_LEVEL

    perks: dict[str, dict[str, Any]] = {}
    used: set[int] = set()
    unparsed: list[str] = []
    for level, maxed, body in _split_perk_blocks(text):
        match_num = _perk_number(body)
        if match_num is None:
            unparsed.append(body.splitlines()[0][:80])
            continue
        number = match_num
        values = _values_from_block(body)
        if not values:
            warnings.append(f"perk {number}: no current/next values")
        perks[str(number)] = _perk_payload(
            number, level=level, maxed=maxed, values=values
        )
        used.add(number)

    missing = [n for n in range(1, 11) if n not in used]
    if missing:
        warnings.append("missing perks: " + ", ".join(str(n) for n in missing))
    if unparsed:
        fields["unparsed_lines"] = unparsed
        warnings.append(f"{len(unparsed)} shop line(s) had no perk number")

    fields["perks"] = perks
    fields["perk_count"] = len(perks)

    p9 = perks.get("9") or {}
    extra = p9.get("extra_clicks")
    if extra is not None:
        fields["perk9_level"] = p9.get("level")
        fields["perk9_extra_clicks"] = extra
        fields["perk9_click_max"] = perk9_click_max(extra)
        if p9.get("sphere_value_pct") is not None:
            fields["perk9_sphere_value_pct"] = p9["sphere_value_pct"]

    p2 = perks.get("2") or {}
    if p2.get("megasphere_rewards") is not None:
        fields["perk2_megasphere_rewards"] = p2["megasphere_rewards"]
    p8 = perks.get("8") or {}
    if p8.get("kakera_boost_pct") is not None:
        fields["perk8_kakera_boost_pct"] = p8["kakera_boost_pct"]
    p10 = perks.get("10") or {}
    if p10.get("ot_chance_pct") is not None:
        fields["perk10_ot_chance_pct"] = p10["ot_chance_pct"]

    extra_txt = extra if extra is not None else "?"
    cap = fields.get("perk9_click_max", "?")
    spheres_txt = f"{fields['spheres']:,} SP" if "spheres" in fields else "SP ?"
    summary = (
        f"$shop · {len(perks)} perks · perk 9 +{extra_txt} clicks "
        f"({cap}/day) · {spheres_txt}"
    )
    return ParseResult(
        kind=MessageKind.SHOP,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def parse_shop_snapshot(snapshot: Any) -> ParseResult:
    return parse_shop(snapshot_visible_text(snapshot))
