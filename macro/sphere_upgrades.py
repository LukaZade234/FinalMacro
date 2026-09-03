"""What the next ouroperk level is worth, for the perks we can actually price.

The full spcalc income model is deliberately out of scope (`docs/TODO.md` calls
it a multi-day transcription). This answers the narrower question — *which
single upgrade pays back fastest* — and **abstains** on every perk whose return
we cannot compute from data the app holds, rather than filling the column with a
plausible-looking number.

Only perk 9 is priced today, because only perk 9's return is already implemented:

* **sphere value %** scales every perk-9 click, so the gain is the account's own
  observed perk-9 SP/day times ``(next - now) / (100 + now)``. Measured, not
  modelled — it comes from logged ``sphere_click`` events.
* **extra clicks** is the marginal value of one more click at the day's spawn
  count, which is exactly ``V[r][c+1] - V[r][c]`` from the perk-9 DP
  (:func:`macro.perk9_threshold.build_value_table`). Needs a spawn estimate; with
  no ``$ohu9`` behind it the component abstains instead of guessing.

Perks 1–8 and 10 need things the app does not capture — OP-character roster
counts, megasphere chains, a kakera balance — so they are listed with the reason
and no number.
"""

from __future__ import annotations

from typing import Any

from macro.perk9_threshold import build_ev_table, build_value_table, normalize_frequency

# The sheet says "Each bonus has 10 levels (cost increased by +4,000 per level)",
# so level N costs N steps and the next level costs (level + 1) steps. Mudae
# never prints the resulting figure, so this stays derived — the UI labels it.
COST_IS_DERIVED = True

# Why each unpriceable perk abstains. Keyed by perk number.
_NO_MODEL: dict[int, str] = {
    1: "Needs OP-character roster counts — the shop reports levels, not how many characters carry them.",
    2: "Megasphere rewards need the claimed-rolls-per-day chain, which is not aggregated.",
    3: "Skipping blue kakera changes kakera income; the app tracks no kakera balance.",
    4: "Omega key value depends on the character it targets; only the account aggregate exists.",
    5: "Extra $ot chance needs a per-board SP model tied to spawn rate.",
    6: "Wishlist claim % and owned-omega % are claim-side, not sphere income.",
    7: "Chaos doubling is kakera income; the app tracks no kakera balance.",
    8: "Perk-8 kakera boost is kakera income; the app tracks no kakera balance.",
    10: "$ot spawn chance needs a per-board SP model tied to spawn rate.",
}


def next_level_cost(level: int, level_cost_step: int) -> int:
    """Spheres to buy the level after ``level``."""
    return max(0, int(level) + 1) * max(0, int(level_cost_step))


def _perk9_gain(
    perk: dict[str, Any],
    *,
    perk9_sp_per_day: float | None,
    spawns_per_day: int | None,
    ev_by_emoji: dict[str, float],
    freq_by_emoji: dict[str, float],
) -> tuple[float | None, list[str], str]:
    """``(sp_per_day, notes, confidence)`` for one perk-9 level."""
    gain = 0.0
    notes: list[str] = []
    priced = False
    modelled = False

    now_pct = perk.get("sphere_value_pct")
    next_pct = perk.get("next_sphere_value_pct")
    if now_pct is not None and next_pct is not None:
        if perk9_sp_per_day is None:
            notes.append("No logged perk-9 spheres yet — value % not priced.")
        else:
            step = (float(next_pct) - float(now_pct)) / (100.0 + float(now_pct))
            share = perk9_sp_per_day * step
            gain += share
            priced = True
            notes.append(
                f"+{float(next_pct) - float(now_pct):.0f}pp sphere value on "
                f"{perk9_sp_per_day:,.0f} SP/day of perk-9 clicks = +{share:,.0f} SP/day."
            )

    now_clicks = perk.get("extra_clicks")
    next_clicks = perk.get("next_extra_clicks")
    if now_clicks is not None and next_clicks is not None:
        added = int(next_clicks) - int(now_clicks)
        if added <= 0:
            pass
        elif not spawns_per_day or not ev_by_emoji:
            notes.append(
                "No spawn estimate yet ($ohu9 not read) — the extra click is not priced."
            )
        else:
            cap_now = 10 + int(now_clicks)
            table = build_value_table(
                int(spawns_per_day), cap_now + added, ev_by_emoji, freq_by_emoji
            )
            if table:
                row = table[min(int(spawns_per_day), len(table)) - 1]
                hi = row[min(cap_now + added, len(row) - 1)]
                lo = row[min(cap_now, len(row) - 1)]
                marginal = max(0.0, hi - lo)
                gain += marginal
                priced = True
                modelled = True
                notes.append(
                    f"+{added} click at {spawns_per_day} spawns/day is worth "
                    f"+{marginal:,.0f} SP/day (perk-9 DP)."
                )

    if not priced:
        return None, notes, "unknown"
    return gain, notes, "modelled" if modelled else "measured"


def next_upgrades(
    shop: dict[str, Any] | None,
    *,
    perk9_sp_per_day: float | None = None,
    spawns_per_day: int | None = None,
    double_chance_pct: float = 0.0,
    additional_spheres: float = 0.0,
    freq_by_emoji: dict[str, float] | None = None,
    base_values: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """One row per perk that still has a level to buy, best payback first.

    Rows we cannot price keep ``sp_per_day``/``payback_days`` as ``None`` and
    carry the reason, so the page can show the gap instead of a fake ranking.
    """
    shop = dict(shop or {})
    perks = shop.get("perks")
    if not isinstance(perks, dict):
        return []

    step = int(shop.get("level_cost_step") or 0)
    shop9_pct = float(shop.get("perk9_sphere_value_pct") or 0.0)
    ev_by_emoji = build_ev_table(
        base_values,
        double_chance_pct=double_chance_pct,
        additional_spheres=additional_spheres,
        shop9_bonus_pct=shop9_pct,
    )
    # The DP is an expectation, so the weights have to sum to 1 — percentages
    # straight off a preset would compound into nonsense (1e236 at 120 spawns).
    freq_normalized = normalize_frequency(freq_by_emoji)

    rows: list[dict[str, Any]] = []
    for raw_number, perk in perks.items():
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            continue
        if not isinstance(perk, dict) or perk.get("maxed"):
            continue
        level = int(perk.get("level") or 0)

        if number == 9:
            gain, notes, confidence = _perk9_gain(
                perk,
                perk9_sp_per_day=perk9_sp_per_day,
                spawns_per_day=spawns_per_day,
                ev_by_emoji=ev_by_emoji,
                freq_by_emoji=freq_normalized,
            )
        else:
            gain, notes, confidence = None, [_NO_MODEL.get(number, "No model yet.")], "unknown"

        cost = next_level_cost(level, step)
        payback = round(cost / gain, 1) if gain and gain > 0 else None
        rows.append(
            {
                "perk": number,
                "id": f"OP{number}",
                "level": level,
                "next_level": level + 1,
                "cost": cost,
                "cost_derived": COST_IS_DERIVED,
                "sp_per_day": round(gain, 1) if gain is not None else None,
                "payback_days": payback,
                "confidence": confidence,
                "notes": notes,
            }
        )

    # Priced rows first, fastest payback first; unpriced keep a stable order.
    rows.sort(
        key=lambda row: (
            row["payback_days"] is None,
            row["payback_days"] if row["payback_days"] is not None else 0,
            row["perk"],
        )
    )
    return rows
