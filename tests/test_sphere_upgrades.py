"""Which ouroperk level to buy next — and which ones we refuse to guess at.

The point of this module is as much what it *declines* to price as what it
prices. Only perk 9's return is computable from data the app holds; filling the
other nine rows with plausible numbers would produce a ranking that looks
authoritative and is not.
"""

from __future__ import annotations

from macro.sphere_upgrades import next_level_cost, next_upgrades

FREQ = {"spB": 59.58, "spT": 24.10, "spG": 7.88, "spY": 2.67, "spR": 0.31}


def _shop(perks: dict, *, step: int = 4000, shop9: float = 50.0) -> dict:
    return {
        "level_cost_step": step,
        "max_level": 10,
        "perk9_sphere_value_pct": shop9,
        "perks": perks,
    }


# --- cost ---------------------------------------------------------------------


def test_next_level_cost_scales_with_level():
    """The sheet says "cost increased by +4,000 per level", not a flat 4,000."""
    assert next_level_cost(0, 4000) == 4000
    assert next_level_cost(5, 4000) == 24000
    assert next_level_cost(9, 4000) == 40000


# --- perk 9 is priced ---------------------------------------------------------


def test_sphere_value_step_is_priced_from_observed_perk9_income():
    rows = next_upgrades(
        _shop({"9": {"level": 5, "maxed": False,
                     "sphere_value_pct": 50, "next_sphere_value_pct": 60}}),
        perk9_sp_per_day=3000.0,
        freq_by_emoji=FREQ,
    )
    row = rows[0]
    # +10pp on a base of 100+50 → 3000 * 10/150 = 200 SP/day
    assert row["sp_per_day"] == 200.0
    assert row["confidence"] == "measured"
    assert row["cost"] == 24000
    assert row["payback_days"] == 120.0


def test_value_step_abstains_without_logged_perk9_income():
    rows = next_upgrades(
        _shop({"9": {"level": 5, "maxed": False,
                     "sphere_value_pct": 50, "next_sphere_value_pct": 60}}),
        perk9_sp_per_day=None,
        freq_by_emoji=FREQ,
    )
    assert rows[0]["sp_per_day"] is None
    assert rows[0]["confidence"] == "unknown"
    assert any("not priced" in note for note in rows[0]["notes"])


def test_extra_click_needs_a_spawn_estimate_and_says_so():
    rows = next_upgrades(
        _shop({"9": {"level": 5, "maxed": False,
                     "extra_clicks": 5, "next_extra_clicks": 6}}),
        spawns_per_day=None,
        freq_by_emoji=FREQ,
    )
    assert rows[0]["sp_per_day"] is None
    assert any("$ohu9" in note for note in rows[0]["notes"])


def test_extra_click_is_priced_from_the_perk9_dp_when_spawns_are_known():
    rows = next_upgrades(
        _shop({"9": {"level": 5, "maxed": False,
                     "extra_clicks": 5, "next_extra_clicks": 6}}),
        spawns_per_day=120,
        freq_by_emoji=FREQ,
    )
    row = rows[0]
    assert row["sp_per_day"] is not None and row["sp_per_day"] > 0
    assert row["confidence"] == "modelled"
    assert any("perk-9 DP" in note for note in row["notes"])


def test_a_marginal_click_is_worth_less_when_spawns_are_scarce():
    """More clicks only help if there are spawns to spend them on."""
    def gain(spawns):
        rows = next_upgrades(
            _shop({"9": {"level": 5, "maxed": False,
                         "extra_clicks": 5, "next_extra_clicks": 6}}),
            spawns_per_day=spawns,
            freq_by_emoji=FREQ,
        )
        return rows[0]["sp_per_day"]

    assert gain(8) < gain(200)


# --- abstention ---------------------------------------------------------------


def test_every_other_perk_abstains_with_a_reason():
    perks = {
        str(n): {"level": 3, "maxed": False, "value": 1, "next_value": 2}
        for n in (1, 2, 3, 4, 5, 6, 7, 8, 10)
    }
    rows = next_upgrades(_shop(perks), perk9_sp_per_day=3000.0, freq_by_emoji=FREQ)

    assert len(rows) == 9
    for row in rows:
        assert row["sp_per_day"] is None
        assert row["payback_days"] is None
        assert row["confidence"] == "unknown"
        assert row["notes"] and row["notes"][0].strip()


def test_maxed_perks_are_not_offered():
    rows = next_upgrades(
        _shop({
            "9": {"level": 10, "maxed": True, "extra_clicks": 10, "sphere_value_pct": 100},
            "4": {"level": 6, "maxed": False, "omega_key_pct": 30, "next_omega_key_pct": 35},
        }),
        perk9_sp_per_day=3000.0,
        freq_by_emoji=FREQ,
    )
    assert [row["id"] for row in rows] == ["OP4"]


def test_priced_rows_sort_ahead_of_unpriceable_ones():
    rows = next_upgrades(
        _shop({
            "4": {"level": 6, "maxed": False, "omega_key_pct": 30, "next_omega_key_pct": 35},
            "9": {"level": 5, "maxed": False,
                  "sphere_value_pct": 50, "next_sphere_value_pct": 60},
        }),
        perk9_sp_per_day=3000.0,
        freq_by_emoji=FREQ,
    )
    assert rows[0]["id"] == "OP9"
    assert rows[-1]["payback_days"] is None


def test_a_shop_that_was_never_fetched_yields_nothing():
    assert next_upgrades(None) == []
    assert next_upgrades({}) == []
    assert next_upgrades({"perks": "nonsense"}) == []
