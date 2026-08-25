"""Meaning catalog for Mudae ``$bonus`` lines.

``$bonus`` is a description sheet. Suffixes like ``($kt)`` / ``($kl)`` /
``($op)`` / ``($shop)`` name *where a bonus comes from*. They are not
commands to send. Identity of a field is the meaning key below, not the
suffix.

One bullet → one field. Lines with several numbers keep them in one dict
(rolls/hour net + sources + penalties, $oh daily, megaspheres, random kakera).

``later=True`` marks values the macro will need for decisions. Those stay
stored-only until a later slice wires them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BonusMeaning:
    key: str
    value_type: str
    source_tag: str | None
    later: bool
    description: str


BONUS_MEANINGS: tuple[BonusMeaning, ...] = (
    BonusMeaning(
        "rolls_per_hour",
        "dict",
        None,
        True,
        "Net rolls/hour plus sources and $bw/$bk penalties",
    ),
    BonusMeaning(
        "wishlist_slots",
        "int",
        None,
        False,
        "Wishlist slots",
    ),
    BonusMeaning(
        "wishseries_slots",
        "int",
        None,
        False,
        "Wishseries slots",
    ),
    BonusMeaning(
        "wish_spawn_bonus_pct",
        "percent",
        None,
        False,
        "Spawn bonus for wishes",
    ),
    BonusMeaning(
        "starwish_spawn_bonus_pct",
        "percent",
        None,
        False,
        "Additional % spawn bonus for $starwish",
    ),
    BonusMeaning(
        "starwish_slots",
        "int",
        None,
        False,
        "Starwish slots",
    ),
    BonusMeaning(
        "wishprotect_spawn_chance",
        "ratio",
        "kl",
        False,
        "Wishprotect spawn chance (e.g. 1/499)",
    ),
    BonusMeaning(
        "rt_cooldown",
        "duration",
        None,
        False,
        "Cooldown for $rt",
    ),
    BonusMeaning(
        "limroul_animanga",
        "int",
        None,
        False,
        "$limroul animanga $wa/$ha limits",
    ),
    BonusMeaning(
        "limroul_game",
        "int",
        None,
        False,
        "$limroul game $wg/$hg limits",
    ),
    BonusMeaning(
        "rank_kakera_bonus_pct",
        "percent",
        "kt",
        False,
        "Bronze IV & Silver IV kakera bonus",
    ),
    BonusMeaning(
        "kakera_earned_bonus_pct",
        "dict",
        None,
        False,
        "Bonus for kakera earned (slash/premium + server premium)",
    ),
    BonusMeaning(
        "kakera_gold_keys_bonus",
        "int",
        None,
        False,
        "Kakera gold keys bonus",
    ),
    BonusMeaning(
        "dk_cooldown",
        "duration",
        None,
        False,
        "Cooldown for $dk",
    ),
    BonusMeaning(
        "mk_per_hour",
        "int",
        "mk",
        False,
        "$mk per hour",
    ),
    BonusMeaning(
        "kakera_max_power",
        "percent",
        "kt",
        True,
        "Kakera reaction-power cap (replaces hardcoded 155 later)",
    ),
    BonusMeaning(
        "power_cost_per_kakera_button",
        "percent",
        None,
        True,
        "Power consumed per kakera button",
    ),
    BonusMeaning(
        "kakera_button_bonus_pct",
        "percent",
        "bk",
        False,
        "Additional bonus for kakera buttons",
    ),
    BonusMeaning(
        "kakera_button_starwish_bonus_pct",
        "percent",
        "sw",
        False,
        "Additional bonus for kakera buttons on starwishes",
    ),
    BonusMeaning(
        "random_kakera",
        "range",
        "kt",
        False,
        "Random kakera per light kakera (min/max)",
    ),
    BonusMeaning(
        "kakera_red_rainbow_bonus",
        "int",
        "kt",
        False,
        "Additional kakera on the final value of red and rainbow",
    ),
    BonusMeaning(
        "kakera_chaos_bonus",
        "int",
        "kt",
        False,
        "Additional kakera on the initial value of chaos",
    ),
    BonusMeaning(
        "chaos_kakera_rarity_mult",
        "float",
        "kt",
        False,
        "Chaos kakera reward rarity multiplier",
    ),
    BonusMeaning(
        "bku_complete_chance_pct",
        "dict",
        "kl",
        False,
        "Chance to complete + reset $bku on $sw (value + this interval)",
    ),
    BonusMeaning(
        "extra_key_chance_pct",
        "percent",
        "kt",
        False,
        "Chance to get an additional key",
    ),
    BonusMeaning(
        "extra_key_wish_chance_pct",
        "percent",
        "kt",
        False,
        "Chance to get an additional key on wishes",
    ),
    BonusMeaning(
        "sphere_double_chance_pct",
        "percent",
        "kt",
        True,
        "Chance to get twice the sphere button value (perk 9 EV)",
    ),
    BonusMeaning(
        "additional_sphere_sources",
        "dict",
        "kt",
        False,
        "Extra sphere sources (claims, $dk, rank, $rolls)",
    ),
    BonusMeaning(
        "additional_spheres",
        "int",
        None,
        True,
        "Flat extra spheres (spheres clicked + premium) — perk 9 EV",
    ),
    BonusMeaning(
        "oh_daily",
        "dict",
        None,
        False,
        "$oh daily bonus: spheres, $oq chance, $ot chance",
    ),
    BonusMeaning(
        "megaspheres",
        "dict",
        "shop",
        False,
        "Megasphere rewards and free chance",
    ),
)

BONUS_MEANING_KEYS: tuple[str, ...] = tuple(item.key for item in BONUS_MEANINGS)

LATER_BONUS_KEYS: frozenset[str] = frozenset(
    item.key for item in BONUS_MEANINGS if item.later
)

BONUS_META_KEYS: frozenset[str] = frozenset({
    "part",
    "parts",
    "line_count",
    "cached_settings",
    "source_tags",
    "unparsed_lines",
    "response_label",
})

BONUS_SECTION_ORDER: tuple[str, ...] = ("player", "kakera", "spheres", "timers")
BONUS_SECTION_TITLES: dict[str, str] = {
    "player": "Rolls & wishes",
    "kakera": "Kakera",
    "spheres": "Spheres",
    "timers": "Cooldowns",
}
BONUS_FIELD_SECTION: dict[str, str] = {
    "rolls_per_hour": "player",
    "wishlist_slots": "player",
    "wishseries_slots": "player",
    "wish_spawn_bonus_pct": "player",
    "starwish_spawn_bonus_pct": "player",
    "starwish_slots": "player",
    "wishprotect_spawn_chance": "player",
    "limroul_animanga": "player",
    "limroul_game": "player",
    "rank_kakera_bonus_pct": "kakera",
    "kakera_earned_bonus_pct": "kakera",
    "kakera_gold_keys_bonus": "kakera",
    "kakera_button_bonus_pct": "kakera",
    "kakera_button_starwish_bonus_pct": "kakera",
    "random_kakera": "kakera",
    "kakera_red_rainbow_bonus": "kakera",
    "kakera_chaos_bonus": "kakera",
    "chaos_kakera_rarity_mult": "kakera",
    "bku_complete_chance_pct": "kakera",
    "extra_key_chance_pct": "kakera",
    "extra_key_wish_chance_pct": "kakera",
    "kakera_max_power": "kakera",
    "power_cost_per_kakera_button": "kakera",
    "sphere_double_chance_pct": "spheres",
    "additional_sphere_sources": "spheres",
    "additional_spheres": "spheres",
    "oh_daily": "spheres",
    "megaspheres": "spheres",
    "rt_cooldown": "timers",
    "dk_cooldown": "timers",
    "mk_per_hour": "timers",
}
BONUS_DISPLAY_LABELS: dict[str, str] = {
    "rolls_per_hour": "Rolls per hour",
    "wishlist_slots": "Wishlist slots",
    "wishseries_slots": "Wishseries slots",
    "wish_spawn_bonus_pct": "Wish spawn bonus",
    "starwish_spawn_bonus_pct": "Starwish spawn bonus",
    "starwish_slots": "Starwish slots",
    "wishprotect_spawn_chance": "Wishprotect chance",
    "limroul_animanga": "$limroul animanga",
    "limroul_game": "$limroul game",
    "rank_kakera_bonus_pct": "Bronze/Silver kakera",
    "kakera_earned_bonus_pct": "Kakera earned bonus",
    "kakera_gold_keys_bonus": "Gold keys bonus",
    "kakera_button_bonus_pct": "Kakera button bonus",
    "kakera_button_starwish_bonus_pct": "Starwish kakera buttons",
    "random_kakera": "Random kakera / light",
    "kakera_red_rainbow_bonus": "Red/rainbow kakera",
    "kakera_chaos_bonus": "Chaos kakera",
    "chaos_kakera_rarity_mult": "Chaos rarity",
    "bku_complete_chance_pct": "$bku complete chance",
    "extra_key_chance_pct": "Extra key chance",
    "extra_key_wish_chance_pct": "Extra key on wishes",
    "kakera_max_power": "Kakera max power",
    "power_cost_per_kakera_button": "Power per kakera button",
    "sphere_double_chance_pct": "Double sphere chance",
    "additional_sphere_sources": "Extra sphere sources",
    "additional_spheres": "Additional spheres",
    "oh_daily": "$oh daily bonus",
    "megaspheres": "Megaspheres",
    "rt_cooldown": "$rt cooldown",
    "dk_cooldown": "$dk cooldown",
    "mk_per_hour": "$mk per hour",
}


def format_bonus_value(key: str, value: Any) -> str:
    if value is None:
        return "—"
    if key == "rolls_per_hour" and isinstance(value, dict):
        net = value.get("net", value.get("unresolved"))
        penalties = value.get("penalties") or {}
        text = f"{net}/h" if net is not None else "—"
        if penalties:
            bits = [f"-{amount} ${cmd}" for cmd, amount in penalties.items()]
            text += "  (" + ", ".join(bits) + ")"
        return text
    if key == "oh_daily" and isinstance(value, dict):
        return (
            f"{value.get('spheres', '—')} SP · "
            f"{value.get('oq_pct', '—')}% $oq · "
            f"{value.get('ot_pct', '—')}% $ot"
        )
    if key == "megaspheres" and isinstance(value, dict):
        return f"{value.get('rewards', '—')} rewards · {value.get('free_pct', '—')}% free"
    if key == "random_kakera" and isinstance(value, dict):
        return f"{value.get('min', '—')}–{value.get('max', '—')}"
    if key == "kakera_earned_bonus_pct" and isinstance(value, dict):
        parts = []
        if value.get("premium_slash") is not None:
            parts.append(f"+{value['premium_slash']}%")
        if value.get("server_premium") is not None:
            parts.append(f"+{value['server_premium']}% server")
        return " / ".join(parts) if parts else "—"
    if key == "bku_complete_chance_pct" and isinstance(value, dict):
        text = f"{value.get('value', '—')}%"
        interval = value.get("this_interval_pct")
        if interval is not None:
            text += f" (interval {interval}%)"
        return text
    if key == "additional_sphere_sources" and isinstance(value, dict):
        return " · ".join(f"{name} {amount}" for name, amount in value.items())
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and (
        key.endswith("_pct") or key in {"kakera_max_power", "power_cost_per_kakera_button"}
    ):
        number = int(value) if float(value) == int(value) else value
        return f"{number}%"
    return str(value)


def _source_chip(key: str, fields: dict[str, Any], fallback: str | None) -> str:
    raw = (fields.get("source_tags") or {}).get(key) or fallback or ""
    token = str(raw).split(",")[0].strip()
    if not token:
        return ""
    if token.startswith("$"):
        return token
    return f"${token}"


def fields_to_bonus_display_dict(fields: dict[str, Any]) -> dict[str, Any]:
    """GUI rows for a stored ``channel.bonus`` sheet (same shape as $settings)."""
    data = dict(fields or {})
    by_section: dict[str, list[dict[str, Any]]] = {}
    filled = 0
    for meaning in BONUS_MEANINGS:
        value = data.get(meaning.key)
        has_value = value is not None and value != {}
        if has_value:
            filled += 1
        row = {
            "field": meaning.key,
            "label": BONUS_DISPLAY_LABELS.get(meaning.key, meaning.description),
            "command": _source_chip(meaning.key, data, meaning.source_tag) if has_value else "",
            "display": format_bonus_value(meaning.key, value) if has_value else "—",
            "has_value": has_value,
        }
        section = BONUS_FIELD_SECTION.get(meaning.key, "player")
        by_section.setdefault(section, []).append(row)
    sections: list[dict[str, Any]] = []
    for section in BONUS_SECTION_ORDER:
        rows = by_section.get(section)
        if rows:
            sections.append({
                "id": section,
                "title": BONUS_SECTION_TITLES.get(section, section),
                "rows": rows,
            })
    return {"sections": sections, "field_count": filled}

