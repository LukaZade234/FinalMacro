"""Display catalog for a stored ``$shop`` sheet.

Perk 9 daily click cap is ``10 + extra_clicks`` (Mudae base 10, shop adds
``+1`` per OP9 level, max ``+10`` → 20). Stored for later calculators; the
macro still uses ``PERK9_CLICK_MAX_DEFAULT``.
"""

from __future__ import annotations

from typing import Any

PERK9_BASE_CLICKS = 10

SHOP_META_KEYS: frozenset[str] = frozenset({
    "command",
    "response_label",
    "part",
    "parts",
    "parser_command",
    "detected_command",
    "command_alias",
    "unparsed_lines",
    "perk_count",
})

_PERK_LABELS: dict[str, str] = {
    "1": "OP1 spawn share",
    "2": "OP2 megasphere rewards",
    "3": "OP3 skip blue kakera",
    "4": "OP4 omega key",
    "5": "OP5 +$ot chance",
    "6": "OP6 wish / omega key",
    "7": "OP7 chaos double",
    "8": "OP8 kakera boost",
    "9": "OP9 clicks / SP",
    "10": "OP10 first $oh $ot",
}


def perk9_click_max(extra_clicks: int | float | None) -> int:
    extra = int(extra_clicks or 0)
    return PERK9_BASE_CLICKS + extra


def _fmt_num(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{_fmt_num(value)}%"


def _arrow(current: str, nxt: Any, *, pct: bool = False) -> str:
    if nxt is None:
        return current
    right = _fmt_pct(nxt) if pct else _fmt_num(nxt)
    return f"{current} → {right}"


def format_perk_display(number: str, perk: dict[str, Any]) -> str:
    level = perk.get("level")
    maxed = bool(perk.get("maxed"))
    prefix = "MAX" if maxed else f"Lv {level}"
    if number == "9":
        extra = perk.get("extra_clicks")
        cap = perk9_click_max(extra)
        clicks = _arrow(f"+{_fmt_num(extra)}", perk.get("next_extra_clicks"))
        sp = _arrow(
            _fmt_pct(perk.get("sphere_value_pct")),
            perk.get("next_sphere_value_pct"),
            pct=True,
        )
        return f"{prefix} · {clicks} ({cap}/day) · {sp} SP"
    if number == "6":
        wish = _arrow(
            _fmt_pct(perk.get("wishlist_claim_pct")),
            perk.get("next_wishlist_claim_pct"),
            pct=True,
        )
        omega = _arrow(
            _fmt_pct(perk.get("owned_omega_key_pct")),
            perk.get("next_owned_omega_key_pct"),
            pct=True,
        )
        return f"{prefix} · wish {wish} · Ω {omega}"
    if number == "2":
        rewards = _arrow(
            _fmt_num(perk.get("megasphere_rewards")),
            perk.get("next_megasphere_rewards"),
        )
        return f"{prefix} · {rewards} rewards"
    key_map = {
        "1": ("spawn_share_pct", True),
        "3": ("skip_blue_kakera_pct", True),
        "4": ("omega_key_pct", True),
        "5": ("ot_chance_pct", True),
        "7": ("chaos_double_pct", True),
        "8": ("kakera_boost_pct", True),
        "10": ("ot_chance_pct", True),
    }
    key, is_pct = key_map.get(number, ("value", False))
    current = _fmt_pct(perk.get(key)) if is_pct else _fmt_num(perk.get(key))
    return f"{prefix} · {_arrow(current, perk.get(f'next_{key}'), pct=is_pct)}"


def fields_to_shop_display_dict(fields: dict[str, Any]) -> dict[str, Any]:
    data = dict(fields or {})
    rows: list[dict[str, Any]] = []
    filled = 0

    spheres = data.get("spheres")
    if spheres is not None:
        filled += 1
        rows.append({
            "field": "spheres",
            "label": "Sphere stock",
            "command": "",
            "display": f"{int(spheres):,}",
            "has_value": True,
        })

    perks = data.get("perks") or {}
    perk_rows: list[dict[str, Any]] = []
    for number in (str(n) for n in range(1, 11)):
        perk = perks.get(number)
        has_value = isinstance(perk, dict) and perk.get("level") is not None
        if has_value:
            filled += 1
        perk_rows.append({
            "field": f"perk_{number}",
            "label": _PERK_LABELS.get(number, f"OP{number}"),
            "command": "",
            "display": format_perk_display(number, perk) if has_value else "—",
            "has_value": has_value,
        })

    cap = data.get("perk9_click_max")
    if cap is not None:
        filled += 1
        perk_rows.append({
            "field": "perk9_click_max",
            "label": "Perk 9 daily cap",
            "command": "",
            "display": f"{cap}/day",
            "has_value": True,
        })

    sections = []
    if rows:
        sections.append({"id": "stock", "title": "Stock", "rows": rows})
    if perk_rows:
        sections.append({"id": "perks", "title": "Ouroperks", "rows": perk_rows})
    return {"sections": sections, "field_count": filled}
