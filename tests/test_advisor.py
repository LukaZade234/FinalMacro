"""Advisor calculations, and the questions they refuse to answer.

`$bw`'s cost has always been exact; its optimum needed the wishlist, and now
that `$wlsz+z!` capture ships it is computed — but only when all the sheets are
there, and the payload names the missing one otherwise. A chaos key is priceable
because it discounts reaction power, while claim keys are not because their
worth is whatever the character you spend them on returns. Pinning the
abstentions matters as much as pinning the arithmetic — a confident wrong number
is worse than a stated gap.
"""

from __future__ import annotations

from macro.advisor import bw_advisory, key_advisory
from tests.bw_wishlist_fixture import LIVE_WISHLIST_ENTRIES


def _bonus(*, bw=19, bk=40, base=21, net=83, bonus=121, sources=None):
    return {
        "rolls_per_hour": {
            "base": base,
            "bonus": bonus,
            "net": net,
            "sources": sources or {"k": 6, "kl": 95, "kt": 10, "premium": 10},
            "penalties": {"bw": bw, "bk": bk},
        },
        "wish_spawn_bonus_pct": 440,
        "starwish_spawn_bonus_pct": 457,
        "extra_key_wish_chance_pct": 79,
    }


def _wishlist(entries=None, **extra):
    listing = {
        "entries": LIVE_WISHLIST_ENTRIES if entries is None else entries,
        "wl_used": 160,
        "wl_max": 162,
        "complete": True,
    }
    listing.update(extra)
    return listing


def _shop(*, share=50):
    return {"perks": {"1": {"level": 5, "spawn_share_pct": share}}}


# --- $bw ----------------------------------------------------------------------


def test_bw_cost_comes_straight_off_bonus():
    out = bw_advisory(_bonus())
    assert out["available"] is True
    assert out["bw_penalty"] == 19
    assert out["net"] == 83
    # net + every penalty back = what you would roll without them
    assert out["gross"] == 83 + 19 + 40
    assert out["rolls_lost_per_day"] == 19 * 24


def test_bw_names_no_optimum_without_the_wishlist():
    """The crossover needs the $wlsz+z! capture, and says so when it is absent."""
    out = bw_advisory(_bonus(), kakera_per_roll=12.0)
    assert out["optimum"] is None
    assert "wlsz" in out["optimum_blocked_by"]
    assert out["sweep"]["available"] is False


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


# --- The sweep, once every sheet is there -------------------------------------


def test_the_optimum_lands_once_the_wishlist_is_supplied():
    """`_bonus()` carries no source tags, so slash stays in — Colblitz's own run.

    Their published answer for this account is `$bw` 18 at 51.695 keys/hr, and
    reproducing it is the point of pinning the number here rather than whatever
    the model happens to say.
    """
    out = bw_advisory(_bonus(), wishlist=_wishlist(), shop=_shop())
    assert out["optimum_blocked_by"] == ""
    assert out["optimum"] == 18
    assert out["sweep"]["available"] is True
    assert out["sweep"]["current_bw"] == 19
    assert out["wishlist_size"] == 160
    assert out["wishlist_complete"] is True


def test_taking_the_slash_bonus_out_moves_the_optimum_by_one():
    """The macro rolls with `$`, so it loses 10 points of wish bonus."""
    bonus = _bonus()
    bonus["source_tags"] = {"wish_spawn_bonus_pct": "k, bw, slash"}
    assert bw_advisory(bonus, wishlist=_wishlist())["optimum"] == 19


def test_the_cost_side_is_unchanged_by_any_of_this():
    """The pre-sweep numbers are the same whether or not the wishlist is there."""
    without = bw_advisory(_bonus())
    with_list = bw_advisory(_bonus(), wishlist=_wishlist())
    for key in ("bw_penalty", "net", "gross", "base", "rolls_lost_per_day"):
        assert without[key] == with_list[key]


def test_setrolls_falls_back_to_the_settings_sheet():
    """A cold `$settings` cache leaves `$bonus` with neither `base` nor `net`."""
    bonus = _bonus()
    bonus["rolls_per_hour"] = {
        "bonus": 121,
        "sources": {"k": 6, "kl": 95, "kt": 10, "premium": 10},
        "penalties": {"bw": 19, "bk": 40},
        "unresolved": 62,
    }
    blind = bw_advisory(bonus, wishlist=_wishlist())
    seeded = bw_advisory(bonus, wishlist=_wishlist(), settings={"setrolls": 21})
    assert blind["sweep"]["available"] is False
    assert "$bonus" in blind["optimum_blocked_by"]
    assert seeded["sweep"]["max_bw"] == 21 + 121 - 40
    assert seeded["inputs"]["settings"]["needed"] is True


def test_each_sheet_reports_its_own_readiness_and_what_to_do():
    out = bw_advisory(_bonus(), wishlist=_wishlist(), shop=_shop())
    inputs = out["inputs"]
    assert set(inputs) == {"bonus", "settings", "shop", "wishlist"}
    assert inputs["bonus"]["ready"] is True
    assert inputs["wishlist"]["ready"] is True
    assert inputs["shop"]["ready"] is True
    # $settings is only wanted when $bonus could not read setrolls for itself.
    assert inputs["settings"]["ready"] is False
    assert inputs["settings"]["needed"] is False
    assert inputs["settings"]["required"] is False


def test_a_missing_sheet_says_which_command_fetches_it():
    out = bw_advisory(_bonus())
    assert out["inputs"]["wishlist"]["ready"] is False
    assert "$wl" in out["inputs"]["wishlist"]["why"]
    assert out["inputs"]["wishlist"]["required"] is True


def test_sheet_provenance_rides_along_for_the_freshness_chips():
    out = bw_advisory(
        _bonus(),
        wishlist=_wishlist(),
        sheet_meta={"bonus": {"read_at": "2026-09-04T20:08:51+00:00", "inferred": True}},
    )
    assert out["inputs"]["bonus"]["read_at"].startswith("2026-09-04")
    assert out["inputs"]["bonus"]["inferred"] is True


def test_no_bonus_still_reports_readiness_so_the_page_can_offer_a_fetch():
    out = bw_advisory(None, wishlist=_wishlist())
    assert out["available"] is False
    assert out["inputs"]["bonus"]["ready"] is False
    assert out["inputs"]["wishlist"]["ready"] is True


def test_the_shop_cross_checks_the_wishlists_perk_one_figures():
    """Buy an OP1 level after capturing `$wl` and every `+N%` goes stale."""
    agrees = bw_advisory(_bonus(), wishlist=_wishlist(), shop=_shop(share=50))
    assert agrees["perk1_check"]["agrees"] is True
    assert agrees["perk1_check"]["matches"] == 160

    moved = bw_advisory(_bonus(), wishlist=_wishlist(), shop=_shop(share=60))
    assert moved["perk1_check"]["agrees"] is False


def test_the_perk_one_check_abstains_without_a_shop_sheet():
    out = bw_advisory(_bonus(), wishlist=_wishlist())
    assert out["perk1_check"]["available"] is False
    assert "$shop" in out["perk1_check"]["why"]


def test_options_come_back_defaulted_and_are_honoured():
    default = bw_advisory(_bonus(), wishlist=_wishlist())
    assert default["options"] == {
        "base_pool": 2000,
        "persrare_n": 1,
        "claimed_pool": 0,
        "uses_slash": False,
        "focus_name": "",
    }
    # A bigger pool dilutes every wishlist character, so more $bw is worth buying.
    bigger = bw_advisory(_bonus(), wishlist=_wishlist(), options={"base_pool": 8000})
    assert bigger["optimum"] > default["optimum"]


def test_a_focus_character_gets_its_own_optimum():
    out = bw_advisory(
        _bonus(), wishlist=_wishlist(), options={"focus_name": "Rebecca"}
    )
    assert out["sweep"]["focus_name"] == "Rebecca"
    assert out["sweep"]["best_focus_bw"] < out["optimum"]
    # Rebecca is a starwish, so the page must not present her spawn bonus as
    # the plain wish-tier figure the wishlist-wide rows use.
    assert out["sweep"]["focus_starwish"] is True


def test_mudaes_own_combined_total_checks_the_starwish_reading():
    """`starwish_spawn_bonus_pct` is the extra on top of wish, not the total.

    `$bonus` closes that bullet with the combined figure, so the two fields
    adding up to it is independent confirmation of how they are read.
    """
    agreeing = _bonus()
    agreeing["starwish_spawn_bonus_total_pct"] = 440 + 457
    assert not any("suspect" in note for note in bw_advisory(agreeing)["notes"])

    disagreeing = _bonus()
    disagreeing["starwish_spawn_bonus_total_pct"] = 457
    notes = bw_advisory(disagreeing)["notes"]
    assert any("suspect" in note for note in notes)


def test_the_slash_bonus_is_removed_when_the_sheet_lists_it():
    bonus = _bonus()
    bonus["source_tags"] = {"wish_spawn_bonus_pct": "k, bw, slash"}
    out = bw_advisory(bonus, wishlist=_wishlist())
    assert out["sweep"]["slash_removed"] is True
    assert any("rolls with $" in note for note in out["notes"])


# --- Key production ------------------------------------------------------------


def test_keys_per_spawn_is_modelled_off_the_capture():
    out = key_advisory(rates_by_type={"gold": 1}, wishlist=_wishlist(), extra_key_pct=79)
    production = out["production"]
    assert production["available"] is True
    assert production["characters"] == 160
    assert production["with_perk4"] == 17
    # 1 guaranteed + 79% global + 30% for a maxed perk 4.
    assert production["best_keys_per_spawn"] == 2.09
    assert production["by_level"]["6"] == 16


def test_key_production_abstains_without_the_capture():
    out = key_advisory(rates_by_type={"gold": 1})
    assert out["production"]["available"] is False
    assert "wlsz" in out["production"]["why"]


def test_claim_keys_still_abstain_on_value_with_the_capture_in_hand():
    """Perk 4 changes how many keys arrive, not what one is worth."""
    out = key_advisory(
        rates_by_type={"gold": 0.9}, kakera_per_click=500.0, wishlist=_wishlist()
    )
    gold = next(row for row in out["rows"] if row["key_type"] == "gold")
    assert gold["value_kakera"] is None
    assert "per-character" in gold["note"]
