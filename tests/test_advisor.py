"""Advisor calculations, and the questions they refuse to answer.

Both of these are half-answerable. `$bw`'s cost is exact and its optimum is not
computable without `$wlsz+z!`; a chaos key is priceable because it discounts
reaction power, while claim keys are not because their worth is whatever the
character you spend them on returns. Pinning the abstentions matters as much as
pinning the arithmetic — a confident wrong number is worse than a stated gap.
"""

from __future__ import annotations

from macro.advisor import bw_advisory, key_advisory


def _bonus(*, bw=19, bk=40, base=21, net=83, sources=None):
    return {
        "rolls_per_hour": {
            "base": base,
            "net": net,
            "sources": sources or {"k": 6, "kl": 95, "kt": 10, "premium": 10},
            "penalties": {"bw": bw, "bk": bk},
        }
    }


# --- $bw ----------------------------------------------------------------------


def test_bw_cost_comes_straight_off_bonus():
    out = bw_advisory(_bonus())
    assert out["available"] is True
    assert out["bw_penalty"] == 19
    assert out["net"] == 83
    # net + every penalty back = what you would roll without them
    assert out["gross"] == 83 + 19 + 40
    assert out["rolls_lost_per_day"] == 19 * 24


def test_bw_never_names_an_optimum():
    """The crossover needs $wlsz+z! wishlist sizes, which nothing captures."""
    out = bw_advisory(_bonus(), kakera_per_roll=12.0)
    assert out["optimum"] is None
    assert "wlsz" in out["optimum_blocked_by"]


def test_bw_prices_forgone_kakera_only_when_given_a_rate():
    """The module can convert; the app does not supply a rate — see below."""
    priced = bw_advisory(_bonus(), kakera_per_roll=12.0)
    assert priced["kakera_forgone_per_day"] == 19 * 24 * 12


def test_bw_says_why_rolls_are_not_converted_to_kakera():
    """Not "no measurement yet" — the measurement is not obtainable.

    Rolls are not events, so the only denominator available is the rolls a day
    theoretically allowed (rolls/hour x 24), which assumes round-the-clock
    rolling; and total kakera mixes roll-proportional income with $daily, $p and
    claims, which are not. On the live account that produced 499 kakera/roll, a
    number with no defensible meaning.
    """
    out = bw_advisory(_bonus(), kakera_per_roll=None)
    assert out["kakera_forgone_per_day"] is None
    assert any("roll-proportional" in note for note in out["notes"])


def test_bw_says_so_when_the_setting_costs_nothing():
    out = bw_advisory(_bonus(bw=0))
    assert out["bw_penalty"] == 0
    assert out["rolls_lost_per_day"] == 0
    assert any("not costing" in note for note in out["notes"])


def test_bw_needs_bonus_and_tolerates_the_legacy_int_shape():
    assert bw_advisory(None)["available"] is False
    assert bw_advisory({})["available"] is False
    # One stored channel still holds the pre-dict shape.
    assert bw_advisory({"rolls_per_hour": 30})["available"] is False


# --- keys ---------------------------------------------------------------------


def test_only_chaos_keys_are_priced():
    out = key_advisory(
        rates_by_type={"bronze": 8.2, "silver": 3.1, "gold": 0.9, "chaos": 2.4, "omega": 0.2},
        kakera_per_click=500.0,
        kakera_base_cost=30.0,
    )
    priced = {row["key_type"]: row["priced"] for row in out["rows"]}
    assert priced == {
        "bronze": False, "silver": False, "gold": False, "chaos": True, "omega": False
    }


def test_chaos_value_is_the_power_it_saves():
    """Halving a 30% click frees half a click's power, so half a click's kakera."""
    out = key_advisory(
        rates_by_type={"chaos": 2.4}, kakera_per_click=500.0, kakera_base_cost=30.0
    )
    chaos = next(row for row in out["rows"] if row["key_type"] == "chaos")
    assert chaos["value_kakera"] == 250.0
    assert chaos["unit"] == "kakera per use"


def test_chaos_value_does_not_depend_on_the_click_cost_cancelling_out():
    """The saved fraction is half whatever the cost is, so the cost cancels."""
    cheap = key_advisory(rates_by_type={"chaos": 1}, kakera_per_click=500.0, kakera_base_cost=15.0)
    dear = key_advisory(rates_by_type={"chaos": 1}, kakera_per_click=500.0, kakera_base_cost=60.0)
    a = next(r for r in cheap["rows"] if r["key_type"] == "chaos")["value_kakera"]
    b = next(r for r in dear["rows"] if r["key_type"] == "chaos")["value_kakera"]
    assert a == b == 250.0


def test_chaos_abstains_without_a_kakera_click_measurement():
    out = key_advisory(rates_by_type={"chaos": 2.4}, kakera_per_click=None)
    chaos = next(row for row in out["rows"] if row["key_type"] == "chaos")
    assert chaos["value_kakera"] is None
    assert chaos["priced"] is False
    assert "not priced" in chaos["note"]


def test_claim_keys_carry_the_reason_they_are_not_priced():
    out = key_advisory(rates_by_type={"gold": 0.9}, kakera_per_click=500.0)
    gold = next(row for row in out["rows"] if row["key_type"] == "gold")
    assert gold["value_kakera"] is None
    assert "per-character" in gold["note"]


def test_every_key_type_is_listed_even_with_no_history():
    out = key_advisory(rates_by_type={})
    assert [row["key_type"] for row in out["rows"]] == [
        "bronze", "silver", "gold", "chaos", "omega"
    ]
    assert all(row["per_day"] == 0 for row in out["rows"])
    assert out["available"] is False
