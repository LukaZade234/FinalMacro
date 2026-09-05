"""Advisory calculations: the `$bw` trade and what a key is actually worth.

Both answer only the half of their question the data supports, and say so about
the rest. That is the point of the Advisor pages — a recommendation with no
evidence behind it is worse than a stated gap, because it looks the same as one
with evidence.

**`$bw`** — the cost side has always been exact: ``$bonus`` carries
``rolls_per_hour`` as ``{base, sources, penalties, net}``, and ``penalties.bw``
is the rolls/hour the setting spends. The benefit side used to be unanswerable
because it needs the wishlist. It no longer is — ``$wlsz+z!`` capture ships, so
this module assembles the four sheets into :func:`macro.bw_calc.sweep_bw` and
reports an optimum whenever they are all present, and names the missing one when
they are not.

Converting rolls to *kakera* is still refused, and for a reason that will not go
away with more capture: rolls are not events, so the only denominator available
is the rolls a day theoretically allowed, and the numerator mixes
roll-proportional income with `$daily` / `$p` / claims. Keys per hour is a unit
the model can actually stand behind; kakera per roll is not.

**Keys** — a chaos key is priceable because it halves the reaction-power cost of
a kakera click (:mod:`macro.reaction_power`), so its value is the power saved
converted into extra clicks at the account's own kakera-per-click. Bronze /
silver / gold / omega are claim keys, and their worth is whatever the character
you spend them on returns, which nothing here models. What the `$wl` capture
*did* unblock is the other half — how many keys arrive — so the production model
is now real even though the valuation is not.
"""

from __future__ import annotations

from typing import Any

from macro.bw_calc import (
    DEFAULT_BASE_POOL,
    PERK4_KEY_PCT,
    BwInputs,
    characters_from_wishlist,
    derive_perk1_pct,
    sweep_bw,
)

# A kakera click costs this share of the power bar by default; `$bonus` overrides
# it per account via `macro.sheet_caps`.
DEFAULT_KAKERA_BASE_COST = 30.0

CLAIM_KEY_TYPES = ("bronze", "silver", "gold", "omega")

_KEY_ABSTAIN = (
    "A claim key is worth whatever the character you spend it on returns. The "
    "$wl capture gives each character's per-character perk-4 level, so the rate "
    "is real — but nothing here models what unlocking a character is worth."
)

# The four sheets a $bw answer needs, and what to do when one is missing.
SHEET_PROMPTS: dict[str, str] = {
    "bonus": "Fetch $bonus — rolls per hour, the wish bonuses and the extra-key chance.",
    "settings": "Fetch $settings — only needed when $bonus could not read setrolls.",
    "shop": "Fetch $shop — cross-checks the wishlist's perk-1 figures.",
    "wishlist": "Fetch $wl — every wishlist character's starwish flag and perks.",
}

# Sheets without which no curve exists at all.
REQUIRED_SHEETS = ("bonus", "wishlist")


def _rolls_per_hour(bonus: dict[str, Any] | None) -> dict[str, Any] | None:
    """``$bonus.rolls_per_hour`` as a dict, or ``None``.

    One stored channel still holds the pre-dict shape (a bare int), which
    ``macro.sheet_caps.rolls_max_from_sheets`` guards against; anything reading
    this field has to do the same.
    """
    raw = (bonus or {}).get("rolls_per_hour")
    return raw if isinstance(raw, dict) else None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _gross_rolls(rolls: dict[str, Any], settings: dict[str, Any] | None) -> int:
    """Rolls an hour before `$bw` and `$bk`, i.e. setrolls plus every source.

    Mudae's own ``net`` is preferred: adding the penalties back to it reverses
    exactly the subtraction the sheet performed, so it cannot disagree with the
    figure on screen. When `$bonus` could not resolve ``net`` — its `$settings`
    cache was cold, and the shape degrades to ``unresolved`` with no ``base`` —
    rebuild it from the stored `$settings` sheet instead.
    """
    taken_off = sum(int(_number(v)) for v in (rolls.get("penalties") or {}).values())
    if rolls.get("net") is not None:
        return int(_number(rolls.get("net"))) + taken_off

    base = rolls.get("base")
    if base is None:
        base = (settings or {}).get("setrolls")
    if base is None:
        return 0
    if rolls.get("bonus") is not None:
        return int(_number(base)) + int(_number(rolls.get("bonus")))
    # `unresolved` is the bonus with the penalties already taken off it.
    if rolls.get("unresolved") is not None:
        return int(_number(base)) + int(_number(rolls.get("unresolved"))) + taken_off
    return int(_number(base))


def _shop_perk1_share(shop: dict[str, Any] | None) -> float | None:
    """`$shop` OP1's ``spawn_share_pct`` — how much of perk 1 feeds back."""
    perks = (shop or {}).get("perks")
    if not isinstance(perks, dict):
        return None
    perk = perks.get("1") or perks.get(1)
    if not isinstance(perk, dict) or "spawn_share_pct" not in perk:
        return None
    return _number(perk.get("spawn_share_pct"))


def _perk1_check(
    wishlist: dict[str, Any] | None, shop: dict[str, Any] | None
) -> dict[str, Any]:
    """Re-derive each row's ``+N%`` from the roster and see if it still holds.

    The `+N%` a `$wl` row carries is the character's perk-1 spawn bonus, and it
    is reproducible from the neighbours' rosters plus the `$shop` OP1 share (see
    :func:`macro.bw_calc.derive_perk1_pct`). Re-deriving it is a freshness check
    on the two sheets together: buy an OP1 level after capturing the wishlist and
    every stored figure is stale, which the sweep would otherwise use silently.
    """
    share = _shop_perk1_share(shop)
    entries = (wishlist or {}).get("entries") or []
    if share is None or not entries:
        return {
            "available": False,
            "why": "Needs both a $wl capture and $shop." if not entries else "Fetch $shop.",
        }

    levels: list[int] = []
    reported: list[int] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        upgrades = row.get("upgrades") if isinstance(row.get("upgrades"), dict) else {}
        if row.get("upgrades_full"):
            level = 6
        else:
            level = int(_number(upgrades.get("1") or upgrades.get(1)))
        levels.append(level)
        reported.append(
            int(_number(row.get("sphere_percent") or row.get("perk1_spawn_pct")))
        )

    derived = derive_perk1_pct(levels, share_pct=share)
    matches = sum(1 for a, b in zip(derived, reported) if a == b)
    return {
        "available": True,
        "share_pct": share,
        "matches": matches,
        "total": len(reported),
        "agrees": matches == len(reported),
    }


def _sheet_inputs(
    *,
    bonus: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    shop: dict[str, Any] | None,
    wishlist: dict[str, Any] | None,
    sheet_meta: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Per-sheet readiness, which is what the page's fetch row renders."""
    rolls = _rolls_per_hour(bonus)
    present = {
        "bonus": bool(bonus),
        # Only actually needed when $bonus could not resolve setrolls itself.
        "settings": bool((settings or {}).get("setrolls") is not None),
        "shop": _shop_perk1_share(shop) is not None,
        "wishlist": bool((wishlist or {}).get("entries")),
    }
    needed = {
        "bonus": True,
        "settings": rolls is not None and rolls.get("base") is None,
        "shop": True,
        "wishlist": True,
    }
    meta = sheet_meta if isinstance(sheet_meta, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for kind, prompt in SHEET_PROMPTS.items():
        info = meta.get(kind) if isinstance(meta.get(kind), dict) else {}
        out[kind] = {
            "ready": present[kind],
            "required": kind in REQUIRED_SHEETS,
            "needed": bool(needed[kind]),
            "why": "" if present[kind] else prompt,
            "read_at": str(info.get("read_at") or ""),
            "inferred": bool(info.get("inferred")),
        }
    return out


def bw_advisory(
    bonus: dict[str, Any] | None,
    *,
    settings: dict[str, Any] | None = None,
    shop: dict[str, Any] | None = None,
    wishlist: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    sheet_meta: dict[str, Any] | None = None,
    kakera_per_roll: float | None = None,
    wishlist_size: int | None = None,
) -> dict[str, Any]:
    """What `$bw` costs, what it buys, and where the two cross."""
    rolls = _rolls_per_hour(bonus)
    if rolls is None:
        return {
            "available": False,
            "reason": "No $bonus yet — fetch it to read rolls per hour.",
            "inputs": _sheet_inputs(
                bonus=bonus,
                settings=settings,
                shop=shop,
                wishlist=wishlist,
                sheet_meta=sheet_meta,
            ),
        }

    penalties = rolls.get("penalties") or {}
    bw_penalty = int(_number(penalties.get("bw")))
    net = int(_number(rolls.get("net")))
    gross = net + sum(int(_number(v)) for v in penalties.values())

    rolls_lost_per_day = bw_penalty * 24
    kakera_forgone = (
        round(rolls_lost_per_day * kakera_per_roll)
        if kakera_per_roll is not None and bw_penalty > 0
        else None
    )

    opts = options if isinstance(options, dict) else {}
    listing = wishlist if isinstance(wishlist, dict) else {}
    source_tags = (bonus or {}).get("source_tags") or {}
    slash_in_sheet = "slash" in str(source_tags.get("wish_spawn_bonus_pct") or "").lower()

    sweep = sweep_bw(
        BwInputs(
            gross_rolls=_gross_rolls(rolls, settings),
            bk=int(_number(penalties.get("bk"))),
            observed_bw=bw_penalty,
            observed_wish_pct=_number((bonus or {}).get("wish_spawn_bonus_pct")),
            observed_starwish_extra_pct=_number(
                (bonus or {}).get("starwish_spawn_bonus_pct")
            ),
            extra_key_pct=_number((bonus or {}).get("extra_key_wish_chance_pct")),
            characters=characters_from_wishlist(listing.get("entries")),
            base_pool=int(_number(opts.get("base_pool"), DEFAULT_BASE_POOL)),
            persrare_n=int(_number(opts.get("persrare_n"), 1)),
            claimed_pool=int(_number(opts.get("claimed_pool"))),
            uses_slash=bool(opts.get("uses_slash")),
            slash_in_sheet=slash_in_sheet,
        ),
        focus_name=str(opts.get("focus_name") or "") or None,
    )

    notes: list[str] = []
    # Mudae prints the combined wish + starwish figure after the starwish
    # bullet. The sweep treats `starwish_spawn_bonus_pct` as the extra on top of
    # wish, and this is the one check on that reading that does not come from
    # the same place. Silent when it agrees; loud when it does not, because
    # then every starwish weight in the curve is wrong.
    printed_total = (bonus or {}).get("starwish_spawn_bonus_total_pct")
    if printed_total is not None:
        our_total = _number((bonus or {}).get("wish_spawn_bonus_pct")) + _number(
            (bonus or {}).get("starwish_spawn_bonus_pct")
        )
        if abs(our_total - _number(printed_total)) > 0.5:
            notes.append(
                f"$bonus prints a combined wish + starwish bonus of "
                f"{_number(printed_total):.0f}%, but its two fields add to "
                f"{our_total:.0f}% — starwish weights in the curve are suspect."
            )
    if bw_penalty <= 0:
        notes.append("$bw is not costing any rolls right now.")
    if kakera_per_roll is None:
        notes.append(
            "Not converted to kakera: rolls are not logged, so the marginal "
            "kakera a roll yields cannot be separated from income that is not "
            "roll-proportional ($daily, $p, claims). Keys per hour is the unit "
            "this page can stand behind."
        )
    notes.extend(sweep.notes)

    return {
        "available": True,
        "bw_penalty": bw_penalty,
        "net": net,
        "gross": gross,
        "base": int(_number(rolls.get("base"))),
        "sources": dict(rolls.get("sources") or {}),
        "penalties": {str(k): int(_number(v)) for k, v in penalties.items()},
        "rolls_lost_per_day": rolls_lost_per_day,
        "kakera_per_roll": round(kakera_per_roll, 1) if kakera_per_roll is not None else None,
        "kakera_forgone_per_day": kakera_forgone,
        "optimum": sweep.best_total_bw,
        "optimum_blocked_by": sweep.blocked_by,
        "wishlist_size": (
            wishlist_size if wishlist_size is not None else listing.get("wl_used")
        ),
        "wishlist_complete": bool(listing.get("complete")) if listing else None,
        "sweep": sweep.to_dict(),
        "perk1_check": _perk1_check(listing, shop),
        "inputs": _sheet_inputs(
            bonus=bonus,
            settings=settings,
            shop=shop,
            wishlist=wishlist,
            sheet_meta=sheet_meta,
        ),
        "options": {
            "base_pool": int(_number(opts.get("base_pool"), DEFAULT_BASE_POOL)),
            "persrare_n": int(_number(opts.get("persrare_n"), 1)),
            "claimed_pool": int(_number(opts.get("claimed_pool"))),
            "uses_slash": bool(opts.get("uses_slash")),
            "focus_name": str(opts.get("focus_name") or ""),
        },
        "notes": notes,
    }


def _key_production(
    wishlist: dict[str, Any] | None, extra_key_pct: float | None
) -> dict[str, Any]:
    """How many keys a wish spawn yields, which the `$wl` capture unblocked.

    ``1`` guaranteed, plus the account-wide extra-key chance from `$bonus`, plus
    the character's own perk 4. All three are independent, so expectations add.
    """
    characters = characters_from_wishlist((wishlist or {}).get("entries"))
    if not characters:
        return {
            "available": False,
            "why": "No $wlsz+z! capture for this account and server yet.",
        }

    global_extra = max(_number(extra_key_pct), 0.0) / 100.0
    by_level: dict[str, int] = {}
    for character in characters:
        key = str(character.perk4_level)
        by_level[key] = by_level.get(key, 0) + 1

    per_spawn = [
        1.0 + global_extra + character.keys_per_spawn_from_perk4
        for character in characters
    ]
    return {
        "available": True,
        "characters": len(characters),
        "with_perk4": sum(1 for c in characters if c.perk4_level > 0),
        "by_level": by_level,
        "perk4_pct_by_level": list(PERK4_KEY_PCT),
        "global_extra_key_pct": round(global_extra * 100.0, 1),
        "mean_keys_per_spawn": round(sum(per_spawn) / len(per_spawn), 3),
        "best_keys_per_spawn": round(max(per_spawn), 3),
        "extra_key_pct_known": extra_key_pct is not None,
    }


def key_advisory(
    *,
    rates_by_type: dict[str, float] | None = None,
    kakera_per_click: float | None = None,
    kakera_base_cost: float | None = None,
    wishlist: dict[str, Any] | None = None,
    extra_key_pct: float | None = None,
) -> dict[str, Any]:
    """Per-key-type daily rate, and a value only where one is defensible."""
    rates = {str(k).lower(): float(v) for k, v in (rates_by_type or {}).items()}
    base_cost = float(kakera_base_cost or DEFAULT_KAKERA_BASE_COST)

    chaos_value: float | None = None
    chaos_note = ""
    if kakera_per_click is None:
        chaos_note = (
            "No logged kakera clicks yet, so the power a chaos key saves is not priced."
        )
    elif base_cost <= 0:
        chaos_note = "Kakera click cost is unknown — fetch $bonus."
    else:
        # Halving a click's cost frees half a click's worth of power per use.
        saved_pp = base_cost / 2.0
        extra_clicks = saved_pp / base_cost
        chaos_value = round(extra_clicks * kakera_per_click, 1)
        chaos_note = (
            f"Halves a {base_cost:.0f}% click to {saved_pp:.0f}%, freeing "
            f"{extra_clicks:.2f} of a click at {kakera_per_click:,.0f} kakera each."
        )

    rows: list[dict[str, Any]] = []
    for key_type in ("bronze", "silver", "gold", "chaos", "omega"):
        is_chaos = key_type == "chaos"
        rows.append(
            {
                "key_type": key_type,
                "per_day": round(rates.get(key_type, 0.0), 2),
                "value_kakera": chaos_value if is_chaos else None,
                "unit": "kakera per use" if is_chaos else "",
                "priced": bool(is_chaos and chaos_value is not None),
                "note": chaos_note if is_chaos else _KEY_ABSTAIN,
            }
        )

    return {
        "available": bool(rates),
        "rows": rows,
        "kakera_per_click": round(kakera_per_click, 1) if kakera_per_click is not None else None,
        "kakera_base_cost": base_cost,
        "production": _key_production(wishlist, extra_key_pct),
    }
