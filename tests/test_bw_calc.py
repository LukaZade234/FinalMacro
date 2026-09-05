"""Tests for the `$bw` sweep.

Two kinds. The **arithmetic** tests pin the published tier tables and the guards
around them. The **replay** tests run the whole model over a real 160-row
`$wlsz+z!` capture and its matching `$bonus`, because that is the only way to
catch a weight, ordering or perk-lookup error: a synthetic wishlist would have
none of the structure the answer actually depends on.
"""

from __future__ import annotations

import pytest

from macro.bw_calc import (
    DEFAULT_BASE_POOL,
    KEY_CAP_PER_HOUR,
    SLASH_SPAWN_BONUS_PCT,
    BwInputs,
    WishCharacter,
    characters_from_wishlist,
    derive_perk1_pct,
    starwish_bw_bonus,
    sweep_bw,
    wish_bw_bonus,
)
from tests.bw_wishlist_fixture import (
    LIVE_BONUS_FIELDS,
    LIVE_SHOP_OP1_SHARE_PCT,
    LIVE_WISHLIST_ENTRIES,
)

LIVE_CHARACTERS = characters_from_wishlist(LIVE_WISHLIST_ENTRIES)


def _live_inputs(**overrides) -> BwInputs:
    rolls = LIVE_BONUS_FIELDS["rolls_per_hour"]
    kwargs = dict(
        gross_rolls=rolls["base"] + rolls["bonus"],
        bk=rolls["penalties"]["bk"],
        observed_bw=rolls["penalties"]["bw"],
        observed_wish_pct=LIVE_BONUS_FIELDS["wish_spawn_bonus_pct"],
        observed_starwish_extra_pct=LIVE_BONUS_FIELDS["starwish_spawn_bonus_pct"],
        extra_key_pct=LIVE_BONUS_FIELDS["extra_key_wish_chance_pct"],
        characters=LIVE_CHARACTERS,
        base_pool=DEFAULT_BASE_POOL,
        slash_in_sheet=True,
    )
    kwargs.update(overrides)
    return BwInputs(**kwargs)


# --- The tier tables ----------------------------------------------------------


@pytest.mark.parametrize(
    "bw,expected",
    [
        (0, 0.0),
        (1, 20.0),
        (5, 100.0),  # 5 x 20
        (6, 115.0),
        (15, 250.0),  # + 10 x 15
        (16, 260.0),
        (100, 1100.0),  # + 85 x 10
        (200, 1600.0),  # + 100 x 5
        (300, 1700.0),  # + 100 x 1
    ],
)
def test_wish_tiers_at_every_boundary(bw, expected):
    assert wish_bw_bonus(bw) == expected


@pytest.mark.parametrize(
    "bw,expected",
    [(0, 0.0), (1, 10.0), (100, 1000.0), (101, 1005.0), (200, 1500.0), (300, 1600.0)],
)
def test_starwish_tiers_at_every_boundary(bw, expected):
    assert starwish_bw_bonus(bw) == expected


def test_negative_bw_reads_as_zero():
    assert wish_bw_bonus(-5) == 0.0
    assert starwish_bw_bonus(-5) == 0.0


# --- The decomposition, against two independently captured sheets -------------


def test_the_live_sheet_decomposes_to_a_clean_static_offset():
    """`$bw 19` buys 290 of the reported 440, leaving 150 of static bonus."""
    sweep = sweep_bw(_live_inputs(slash_in_sheet=False))
    assert wish_bw_bonus(19) == 290.0
    assert sweep.static_wish_pct == 150.0
    assert sweep.static_starwish_pct == 457.0 - starwish_bw_bonus(19)


def test_the_bonus_fixture_agrees_on_that_offset_at_a_different_bw():
    """The 2/2 `$bonus` fixture was captured at `$bw 40` and gives the same 150.

    Two sheets at different `$bw` values landing on one static offset is what
    makes the tier table credible rather than merely fitted.
    """
    sweep = sweep_bw(
        _live_inputs(observed_bw=40, observed_wish_pct=650, slash_in_sheet=False)
    )
    assert wish_bw_bonus(40) == 500.0
    assert sweep.static_wish_pct == 150.0


def test_starwish_is_the_extra_on_top_of_wish_not_the_total():
    """The fixture prints `(= 1,315%)`; 650 + 400 + 265 reproduces it exactly."""
    sweep = sweep_bw(
        _live_inputs(
            observed_bw=40,
            observed_wish_pct=650,
            observed_starwish_extra_pct=665,
            slash_in_sheet=False,
        )
    )
    at_40 = sweep.at(40)
    assert at_40 is not None
    assert at_40.wish_pct == 650.0
    assert at_40.starwish_pct == 1315.0


def test_a_sheet_that_contradicts_the_tiers_abstains():
    """Less bonus than `$bw` alone bought means one of the two is wrong."""
    sweep = sweep_bw(_live_inputs(observed_bw=100, observed_wish_pct=440))
    assert sweep.available is False
    assert "less wish bonus" in sweep.blocked_by
    assert sweep.points == ()


# --- What refuses to compute --------------------------------------------------


def test_no_wishlist_capture_blocks_with_a_named_reason():
    sweep = sweep_bw(_live_inputs(characters=()))
    assert sweep.available is False
    assert "$wl" in sweep.blocked_by


def test_no_rolls_per_hour_blocks():
    assert "$bonus" in sweep_bw(_live_inputs(gross_rolls=0)).blocked_by


def test_bk_eating_the_whole_pool_blocks():
    sweep = sweep_bw(_live_inputs(bk=200))
    assert sweep.available is False
    assert "$bk" in sweep.blocked_by


# --- The roll pool ------------------------------------------------------------


def test_the_sweep_stops_where_the_roll_pool_does():
    sweep = sweep_bw(_live_inputs())
    assert sweep.max_bw == 142 - 40
    assert [point.bw for point in sweep.points] == list(range(0, sweep.max_bw + 1))
    assert sweep.points[0].net_rolls == 142 - 40
    assert sweep.points[-1].net_rolls == 0
    assert all(point.net_rolls >= 0 for point in sweep.points)


def test_net_rolls_lose_exactly_one_per_bw():
    sweep = sweep_bw(_live_inputs())
    for point in sweep.points:
        assert point.net_rolls == 142 - 40 - point.bw


# --- Slash ---------------------------------------------------------------------


def test_the_slash_bonus_comes_back_out_because_the_macro_rolls_with_dollar():
    with_slash = sweep_bw(_live_inputs(slash_in_sheet=False))
    without = sweep_bw(_live_inputs(slash_in_sheet=True))
    assert without.slash_removed is True
    assert with_slash.static_wish_pct - without.static_wish_pct == SLASH_SPAWN_BONUS_PCT
    assert any("rolls with $" in note for note in without.notes)


def test_the_slash_bonus_is_only_taken_off_once_for_a_starwish():
    """A starwish's total is wish + its own extra, so wish carries the slash cut.

    `$bonus` lists slash as a source of the wish line and not of the starwish
    line. Subtracting it from both offsets docked every starwish 20 points
    instead of 10 — which understated exactly the characters that matter most.
    """
    kept = sweep_bw(_live_inputs(slash_in_sheet=False)).at(19)
    docked = sweep_bw(_live_inputs(slash_in_sheet=True)).at(19)

    assert kept.wish_pct - docked.wish_pct == SLASH_SPAWN_BONUS_PCT
    assert kept.starwish_pct - docked.starwish_pct == SLASH_SPAWN_BONUS_PCT
    # And the sheet's own figures, unmodified, are 440 / 897.
    assert (kept.wish_pct, kept.starwish_pct) == (440.0, 897.0)


def test_perk_one_lifts_its_carrier_without_enlarging_the_pool():
    """Perk 1 shifts share; it does not add characters to roll against.

    Counting it in the denominator too is what put this model 25x further from
    `bwcalc`'s published table than it needed to be.
    """
    plain = WishCharacter(name="Plain")
    lifted = WishCharacter(name="Lifted", perk1_pct=313)

    without = sweep_bw(_live_inputs(characters=(plain, plain, plain))).at(19)
    with_perk1 = sweep_bw(_live_inputs(characters=(plain, plain, lifted))).at(19)

    assert with_perk1.pool_weight == without.pool_weight
    # The carrier still spawns more often, so the wishlist as a whole does too.
    assert with_perk1.wl_spawns_per_hour > without.wl_spawns_per_hour


def test_saying_you_use_slash_keeps_the_bonus_the_sheet_reported():
    sweep = sweep_bw(_live_inputs(slash_in_sheet=True, uses_slash=True))
    assert sweep.slash_removed is False
    assert sweep.static_wish_pct == 150.0


def test_slash_on_without_the_sheet_listing_it_adds_nothing_and_says_so():
    sweep = sweep_bw(_live_inputs(slash_in_sheet=False, uses_slash=True))
    assert sweep.slash_removed is False
    assert any("does not list slash" in note for note in sweep.notes)


# --- $persrare -----------------------------------------------------------------


def test_persrare_at_one_reroll_is_exactly_the_no_persrare_curve():
    """`$ov` has no parser, so N defaults to 1 — and that must cost nothing."""
    plain = sweep_bw(_live_inputs())
    with_n1 = sweep_bw(_live_inputs(persrare_n=1, claimed_pool=1200))
    assert [p.total_keys_per_hour for p in plain.points] == [
        p.total_keys_per_hour for p in with_n1.points
    ]


def test_persrare_raises_ev_and_moves_the_optimum_down():
    """Rerolls shrink the claimed share more at low `$bw`, favouring fewer."""
    plain = sweep_bw(_live_inputs())
    rerolled = sweep_bw(_live_inputs(persrare_n=3, claimed_pool=1200))
    assert rerolled.at(19).total_keys_per_hour > plain.at(19).total_keys_per_hour
    assert rerolled.best_total_bw < plain.best_total_bw


def test_persrare_without_a_claimed_count_says_it_changes_nothing():
    sweep = sweep_bw(_live_inputs(persrare_n=4, claimed_pool=0))
    assert any("change nothing" in note for note in sweep.notes)


# --- The hourly key cap --------------------------------------------------------


def test_keys_are_capped_at_the_hourly_limit():
    """Clipped at 2,200, and the cheapest `$bw` that reaches it is named.

    Deliberately synthetic. Reaching the cap needs `net rolls x keys per spawn`
    over 2,200, and no real roll pool comes close — see the test below.
    """
    sweep = sweep_bw(_live_inputs(gross_rolls=5000, bk=0, base_pool=1))
    assert sweep.cheapest_capped_bw is not None
    for point in sweep.points:
        assert point.capped_keys_per_hour == min(
            point.total_keys_per_hour, float(KEY_CAP_PER_HOUR)
        )
    capped = [p.bw for p in sweep.points if p.total_keys_per_hour >= KEY_CAP_PER_HOUR]
    assert sweep.cheapest_capped_bw == min(capped)
    assert any("key limit is reached" in note for note in sweep.notes)


def test_a_real_roll_pool_cannot_reach_the_cap_at_any_bw():
    """102 rolls an hour at ~2 keys a spawn tops out two orders below 2,200."""
    sweep = sweep_bw(_live_inputs())
    assert sweep.cheapest_capped_bw is None
    assert max(p.total_keys_per_hour for p in sweep.points) < KEY_CAP_PER_HOUR / 20


# --- Replaying the real capture ------------------------------------------------


def test_the_capture_maps_onto_the_spawn_model():
    assert len(LIVE_CHARACTERS) == 160
    assert sum(1 for c in LIVE_CHARACTERS if c.starwish) == 16
    # `Full` means every perk maxed, so perk 4 is level 6 without an explicit row.
    full = [c for c in LIVE_CHARACTERS if c.perk4_level == 6]
    assert len(full) == 16
    assert full[0].keys_per_spawn_from_perk4 == 0.30
    # One character carries perk 4 partway up.
    partial = [c for c in LIVE_CHARACTERS if 0 < c.perk4_level < 6]
    assert [(c.name, c.perk4_level) for c in partial] == [("Tanya Degurechaff", 2)]


# Colblitz's own bwcalc output for this exact account and wishlist, with the
# slash bonus left in as their run had it: (bw, rolls, WL/hr, Sel/hr for Lucy,
# WL keys/hr, Sel keys/hr). Pasted from the published table, not recomputed.
COLBLITZ_TABLE = {
    0: (102, 20.571, 0.346, 38.461, 0.723),
    5: (97, 24.545, 0.364, 45.664, 0.760),
    10: (92, 26.491, 0.371, 49.185, 0.775),
    15: (87, 27.817, 0.373, 51.572, 0.779),
    18: (84, 27.891, 0.371, 51.695, 0.775),
    19: (83, 27.891, 0.370, 51.691, 0.773),
    25: (77, 27.649, 0.362, 51.220, 0.756),
    40: (62, 25.435, 0.324, 47.081, 0.677),
    60: (42, 19.613, 0.244, 36.280, 0.511),
    80: (22, 11.302, 0.139, 20.898, 0.290),
}


def test_the_model_reproduces_colblitzs_published_table():
    """The one external check on the whole model.

    Everything else here pins our own arithmetic against itself. This pins it
    against an independent implementation of the same published method, run on
    the same account — so a wrong pool convention or a double-counted bonus
    shows up as a number, not as a plausible-looking curve.
    """
    sweep = sweep_bw(_live_inputs(slash_in_sheet=False), focus_name="Lucy")

    for bw, (rolls, wl, sel, wl_keys, sel_keys) in COLBLITZ_TABLE.items():
        point = sweep.at(bw)
        assert point.net_rolls == rolls
        for ours, theirs in (
            (point.wl_spawns_per_hour, wl),
            (point.focus_spawns_per_hour, sel),
            (point.total_keys_per_hour, wl_keys),
            (point.focus_keys_per_hour, sel_keys),
        ):
            # Their table is printed to 3 decimals, so a figure like 0.139
            # carries +-0.0005 of rounding all by itself. On top of that we sit
            # a consistent ~0.06% high (0.21% worst case): our pool comes out
            # about 0.8 weight smaller than theirs out of ~2,900, a difference
            # far below the precision of the base-pool input feeding both.
            assert abs(ours - theirs) <= 0.0005 + 0.0025 * theirs, (
                f"$bw {bw}: {ours:.4f} vs bwcalc {theirs:.3f}"
            )


def test_all_three_optima_match_colblitz():
    sweep = sweep_bw(_live_inputs(slash_in_sheet=False), focus_name="Lucy")
    assert sweep.best_total_bw == 18
    assert sweep.best_starwish_bw == 15
    assert sweep.best_focus_bw == 15

    whole = sweep.at(18)
    assert round(whole.total_keys_per_hour, 1) == 51.7
    assert round(whole.wl_share_of_rolls * 100, 1) == 33.2

    stars = sweep.at(15)
    assert round(stars.sw_keys_per_hour, 1) == 12.3
    assert round(stars.sw_share_of_rolls * 100, 1) == 6.8

    lucy = sweep.at(15)
    assert round(lucy.focus_keys_per_hour, 2) == 0.78
    assert round(lucy.focus_one_in_rolls) == 233


def test_starwishes_peak_lower_than_the_wishlist_as_a_whole():
    """They carry the extra bonus, so they stop wanting more `$bw` sooner."""
    sweep = sweep_bw(_live_inputs(slash_in_sheet=False))
    assert sweep.best_starwish_bw < sweep.best_total_bw


def test_no_starwishes_means_no_starwish_optimum():
    plain = WishCharacter(name="Plain")
    assert sweep_bw(_live_inputs(characters=(plain,))).best_starwish_bw is None


def test_the_live_account_is_already_at_its_optimum():
    """The whole model, end to end, on the account it was derived from."""
    sweep = sweep_bw(_live_inputs())
    assert sweep.available is True
    assert sweep.current_bw == 19
    assert sweep.best_total_bw == 19
    assert sweep.at(19).net_rolls == 83
    assert 45.0 < sweep.at(19).total_keys_per_hour < 55.0
    assert sweep.to_dict()["current_share_of_best"] == 1.0


def test_a_single_character_peaks_lower_than_the_whole_wishlist():
    """One character's own EV ignores the rest, so it buys less `$bw`."""
    sweep = sweep_bw(_live_inputs(), focus_name="Rebecca")
    assert sweep.focus_name == "Rebecca"
    assert sweep.best_focus_bw is not None
    assert sweep.best_focus_bw < sweep.best_total_bw
    assert sweep.at(sweep.best_focus_bw).focus_spawn_pct > 0


def test_focus_starwish_is_reported_so_a_page_can_show_her_own_bonus():
    """A starwish focus character's own bonus is `starwish_pct`, not `wish_pct`.

    The page's "rows worth comparing" table used to always print `wish_pct` for
    every row, including a starwish focus character's — understating her actual
    spawn bonus and making her row look weaker than the wishlist-wide rows it
    was sitting next to. `focus_starwish` is what lets the page pick correctly.
    """
    assert sweep_bw(_live_inputs(), focus_name="Rebecca").focus_starwish is True
    assert sweep_bw(_live_inputs(), focus_name="Neferpitou").focus_starwish is False
    assert sweep_bw(_live_inputs()).focus_starwish is False


def test_an_unknown_focus_name_leaves_the_focus_columns_empty():
    sweep = sweep_bw(_live_inputs(), focus_name="Nobody At All")
    assert sweep.best_focus_bw is None
    assert sweep.focus_name == ""
    assert sweep.focus_starwish is False
    assert all(point.focus_keys_per_hour is None for point in sweep.points)


def test_starwishes_outweigh_plain_wishes():
    sweep = sweep_bw(_live_inputs())
    star = sweep_bw(_live_inputs(), focus_name="Rebecca").at(19).focus_spawn_pct
    plain = sweep_bw(_live_inputs(), focus_name="Neferpitou").at(19).focus_spawn_pct
    assert star > plain
    assert sweep.at(19).starwish_pct > sweep.at(19).wish_pct


# --- The perk-1 finding --------------------------------------------------------


def test_the_row_percentages_are_the_perk_one_spawn_bonus():
    """Reproduces Mudae's own `+N%` on all 160 rows.

    `MUDAE_LOGIC.md` recorded these as unexplained. They are perk 1 from the
    neighbours either side in wishlist order — the list **wrapping**, which is
    why the last row scores off the first — plus the `$shop` OP1 share fed back
    to the carrier. This test is what keeps that reading honest.
    """
    levels = [
        6 if row["upgrades_full"] else int(row["upgrades"].get("1", 0) or 0)
        for row in LIVE_WISHLIST_ENTRIES
    ]
    derived = derive_perk1_pct(levels, share_pct=LIVE_SHOP_OP1_SHARE_PCT)
    reported = [int(row["sphere_percent"] or 0) for row in LIVE_WISHLIST_ENTRIES]
    assert derived == reported
    # The three distinct values, and that the wrap is what produces the last one.
    assert sorted(set(v for v in reported if v)) == [125, 188, 313]
    assert reported[-1] == 125


def test_perk_one_derivation_handles_degenerate_lists():
    assert derive_perk1_pct([]) == []
    assert derive_perk1_pct([6], share_pct=50) == [63]
    # Two rows are each other's only neighbour, counted once rather than twice.
    assert derive_perk1_pct([6, 0], share_pct=0) == [0, 125]


# --- Weights -------------------------------------------------------------------


def test_perk_one_raises_a_characters_own_weight():
    base = WishCharacter(name="Plain")
    boosted = WishCharacter(name="Boosted", perk1_pct=313)
    inputs = BwInputs(
        gross_rolls=142,
        bk=40,
        observed_bw=19,
        observed_wish_pct=440,
        observed_starwish_extra_pct=457,
        extra_key_pct=79,
        characters=(base, boosted),
    )
    plain = sweep_bw(inputs, focus_name="Plain").at(19).focus_spawn_pct
    lifted = sweep_bw(inputs, focus_name="Boosted").at(19).focus_spawn_pct
    assert lifted > plain
