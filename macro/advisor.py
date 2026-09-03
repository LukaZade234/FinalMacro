"""Advisory calculations: the `$bw` trade and what a key is actually worth.

Both answer only the half of their question the data supports, and say so about
the rest. That is the point of the Advisor pages — a recommendation with no
evidence behind it is worse than a stated gap, because it looks the same as one
with evidence.

**`$bw`** — the cost side is exact. ``$bonus`` already carries
``rolls_per_hour`` as ``{base, sources, penalties, net}``, and ``penalties.bw``
is the rolls/hour the setting is spending. The *benefit* side is not
computable: where the wish-spawn gain overtakes the roll loss depends on how
many characters are on the wishlist and how contested they are, which is
``$wlsz+z!`` output that nothing in the app captures. So this quantifies the
cost and refuses to name an optimum.

**Keys** — only chaos keys are priceable, and for a reason that has nothing to
do with claiming: a chaos key halves the reaction-power cost of a kakera click
(:mod:`macro.reaction_power`), so its value is the power it saves, converted
into extra clicks at the account's own observed kakera-per-click. Bronze /
silver / gold / omega are claim keys, and their worth is whatever the character
you spend them on returns — which needs a per-character model the app does not
have. They report their observed rate and abstain on value.
"""

from __future__ import annotations

from typing import Any

# A kakera click costs this share of the power bar by default; `$bonus` overrides
# it per account via `macro.sheet_caps`.
DEFAULT_KAKERA_BASE_COST = 30.0

CLAIM_KEY_TYPES = ("bronze", "silver", "gold", "omega")

_KEY_ABSTAIN = (
    "A claim key is worth whatever the character you spend it on returns, and "
    "the app has no per-character perk-4 level — only the account aggregate "
    "from $shop."
)


def _rolls_per_hour(bonus: dict[str, Any] | None) -> dict[str, Any] | None:
    """``$bonus.rolls_per_hour`` as a dict, or ``None``.

    One stored channel still holds the pre-dict shape (a bare int), which
    ``macro.sheet_caps.rolls_max_from_sheets`` guards against; anything reading
    this field has to do the same.
    """
    raw = (bonus or {}).get("rolls_per_hour")
    return raw if isinstance(raw, dict) else None


def bw_advisory(
    bonus: dict[str, Any] | None,
    *,
    kakera_per_roll: float | None = None,
    wishlist_size: int | None = None,
) -> dict[str, Any]:
    """What ``$bw`` currently costs, and why the optimum is not computable."""
    rolls = _rolls_per_hour(bonus)
    if rolls is None:
        return {
            "available": False,
            "reason": "No $bonus yet — fetch it to read rolls per hour.",
        }

    penalties = rolls.get("penalties") or {}
    bw_penalty = int(penalties.get("bw") or 0)
    net = int(rolls.get("net") or 0)
    gross = net + sum(int(v or 0) for v in penalties.values())

    rolls_lost_per_day = bw_penalty * 24
    kakera_forgone = (
        round(rolls_lost_per_day * kakera_per_roll)
        if kakera_per_roll is not None and bw_penalty > 0
        else None
    )

    notes: list[str] = []
    if bw_penalty <= 0:
        notes.append("$bw is not costing any rolls right now.")
    if kakera_per_roll is None:
        notes.append(
            "Not converted to kakera: rolls are not logged, so the marginal "
            "kakera a roll yields cannot be separated from income that is not "
            "roll-proportional ($daily, $p, claims)."
        )

    return {
        "available": True,
        "bw_penalty": bw_penalty,
        "net": net,
        "gross": gross,
        "base": int(rolls.get("base") or 0),
        "sources": dict(rolls.get("sources") or {}),
        "penalties": {str(k): int(v or 0) for k, v in penalties.items()},
        "rolls_lost_per_day": rolls_lost_per_day,
        "kakera_per_roll": round(kakera_per_roll, 1) if kakera_per_roll is not None else None,
        "kakera_forgone_per_day": kakera_forgone,
        # The half we cannot answer, stated rather than guessed.
        "optimum": None,
        "optimum_blocked_by": "$wlsz+z! wishlist sizes are not captured",
        "wishlist_size": wishlist_size,
        "notes": notes,
    }


def key_advisory(
    *,
    rates_by_type: dict[str, float] | None = None,
    kakera_per_click: float | None = None,
    kakera_base_cost: float | None = None,
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
    }
