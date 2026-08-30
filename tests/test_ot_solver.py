"""Exactness of the ``$ot`` fleet enumerator and the invariants the policy needs.

The counting DP in :mod:`macro.ot_solver` replaces a brute-force DFS over every
fleet placement, so the configuration totals below are the real point of this
file: they were produced by that independent DFS and pin the DP to it.
"""

from __future__ import annotations

import pytest

from macro.minigame_board import GRID_CELLS
from macro.ot_replay import KNOWN_BOARDS, is_legal_board
from macro.ot_solver import (
    BLUE,
    DEFAULT_CLICKS_BUDGET,
    EXTRA_CHANCE_SHIP_HITS,
    OT_BLUE_BONUS_COLORS,
    OT_CELL_SP,
    SEGMENTS,
    UNKNOWN_TWO,
    blue_bonus_for,
    choose_ot_cell,
    choose_ot_click,
    emoji_to_ot_color,
    enumerate_ot,
    expected_two_cell_sp,
    fleet_for_colors,
    format_solver_stats,
    merge_observations,
    observations_from_buttons,
    ot_game_over,
    parse_ot_fleet,
    solver_stats,
)

# Independently counted with a brute-force DFS that lists every placement.
CONFIGURATIONS = {6: 597_408, 7: 1_890_960, 8: 3_082_032, 9: 2_485_616}

LIVE_MESSAGE = (
    "You can click 4 times on the buttons below (2 minutes).\n"
    "All colors are free (they don't consume clicks) except for the blue spheres\n"
    "Identical colors follow one another on the same row or column. For example, "
    "there is a line or a column having ALL the green spheres following one another.\n"
    "Spheres to find: teal = 4, green = 3, yellow = 3, rarer spheres = 2.\n"
    "​\n"
    "Number of different colors: 6\n"
)


def _buttons(board: str | None = None, taken: set[int] | None = None) -> list[dict]:
    taken = taken or set()
    letters = {"B": "spB", "T": "spT", "G": "spG", "Y": "spY", "O": "spO",
               "L": "spL", "D": "spD", "R": "spR", "W": "spW"}
    out = []
    for index in range(GRID_CELLS):
        emoji = "spU"
        if board is not None and index in taken:
            emoji = letters[board[index]]
        out.append(
            {
                "emoji": emoji,
                "custom_id": f"cmd s{index}",
                "kind": "sphere",
                "disabled": index in taken,
            }
        )
    return out


# --- Geometry ---------------------------------------------------------------


def test_segment_tables_cover_every_straight_placement():
    assert len(SEGMENTS[4]) == 20
    assert len(SEGMENTS[3]) == 30
    assert len(SEGMENTS[2]) == 40
    for length, masks in SEGMENTS.items():
        assert len(set(masks)) == len(masks)
        assert all(mask.bit_count() == length for mask in masks)


@pytest.mark.parametrize("n_colors,expected", sorted(CONFIGURATIONS.items()))
def test_enumeration_matches_the_brute_force_count(n_colors, expected):
    marginals = enumerate_ot(fleet_for_colors(n_colors), {})
    assert marginals.total == expected


@pytest.mark.parametrize("n_colors", sorted(CONFIGURATIONS))
def test_cell_classes_partition_the_configurations(n_colors):
    """Every configuration puts each cell in exactly one class."""
    marginals = enumerate_ot(fleet_for_colors(n_colors), {})
    for cell in range(GRID_CELLS):
        assert (
            marginals.blue[cell]
            + marginals.teal[cell]
            + marginals.green[cell]
            + marginals.yellow[cell]
            + marginals.two[cell]
        ) == marginals.total


@pytest.mark.parametrize("n_colors", sorted(CONFIGURATIONS))
def test_fleet_arithmetic_follows_the_colour_count(n_colors):
    fleet = fleet_for_colors(n_colors)
    assert fleet.two_ships == n_colors - 4
    assert fleet.ship_cells == 10 + 2 * fleet.two_ships
    assert fleet.ship_cells + fleet.blue_cells == GRID_CELLS


def test_corners_are_the_likeliest_blue_cells():
    """A corner is reachable by fewer ship placements than an edge midpoint."""
    marginals = enumerate_ot(fleet_for_colors(6), {})
    assert marginals.p_blue(0) > marginals.p_blue(2) > 0.0
    assert marginals.p_blue(0) == pytest.approx(marginals.p_blue(24))


# --- Observations -----------------------------------------------------------


def test_a_fully_revealed_board_leaves_exactly_one_configuration():
    board = KNOWN_BOARDS[0]["cells"]
    observations = {index: colour for index, colour in enumerate(board)}
    marginals = enumerate_ot(fleet_for_colors(len(set(board))), observations)
    assert marginals.total == 1


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_real_boards_survive_their_own_reveal(entry):
    """Every real board is reachable, and the solver never calls a ship blue."""
    board = entry["cells"]
    assert is_legal_board(board)
    fleet = fleet_for_colors(len(set(board)))
    # Reveal half the board; the truth must still be consistent, and no cell
    # the solver marks certain may actually be empty.
    observations = {index: board[index] for index in range(0, GRID_CELLS, 2)}
    marginals = enumerate_ot(fleet, observations)
    assert marginals.total >= 1
    for cell in range(GRID_CELLS):
        if marginals.is_certain_ship(cell):
            assert board[cell] != BLUE


def test_revealed_blues_are_never_reported_as_ships():
    fleet = fleet_for_colors(6)
    marginals = enumerate_ot(fleet, {0: BLUE, 12: BLUE})
    assert marginals.p_blue(0) == 1.0
    assert marginals.p_blue(12) == 1.0
    assert not marginals.is_certain_ship(0)


def test_a_revealed_ship_colour_pins_that_ship():
    """Three yellows in a row leave no room for a fourth."""
    fleet = fleet_for_colors(6)
    marginals = enumerate_ot(fleet, {5: "Y", 6: "Y", 7: "Y"})
    assert marginals.total > 0
    assert marginals.yellow[5] == marginals.total
    for cell in (8, 0, 10):
        assert marginals.yellow[cell] == 0


def test_a_named_two_cell_values_its_partner_at_that_colour():
    """A single rainbow cell makes its neighbours worth far more than a stranger."""
    fleet = fleet_for_colors(9)
    marginals = enumerate_ot(fleet, {12: "W"})
    assert "W" in marginals.pinned
    # Cell 12's ship covers one of its four neighbours, so each is partly
    # rainbow; a cell nowhere near it cannot be.
    assert marginals.pinned["W"][7] > 0
    assert marginals.pinned["W"][0] == 0
    assert marginals.ev(7) > marginals.ev(0)


def test_unknown_two_constrains_geometry_without_naming_a_colour():
    fleet = fleet_for_colors(6)
    marginals = enumerate_ot(fleet, {12: UNKNOWN_TWO})
    assert marginals.total > 0
    assert marginals.two[12] == marginals.total
    assert marginals.blue[12] == 0
    assert marginals.pinned == {}


def test_impossible_observations_report_no_information():
    """Two cells of one length-2 colour that are not adjacent cannot happen."""
    marginals = enumerate_ot(fleet_for_colors(6), {0: "O", 24: "O"})
    assert marginals.total == 0
    assert marginals.ev(3) == 0.0


def test_emoji_and_button_observations():
    assert emoji_to_ot_color("spW") == "W"
    assert emoji_to_ot_color("sp") == "R"
    assert emoji_to_ot_color("spU") is None
    buttons = _buttons("B" * GRID_CELLS, taken={0, 1})
    assert observations_from_buttons(buttons) == {0: BLUE, 1: BLUE}


def test_merge_prefers_a_named_colour_over_the_generic_two():
    assert merge_observations({3: UNKNOWN_TWO}, {3: "O"}) == {3: "O"}
    assert merge_observations({3: "O"}, {3: UNKNOWN_TWO}) == {3: "O"}
    with pytest.raises(ValueError):
        merge_observations({3: "O"}, {3: "W"})


# --- Fleet parsing ----------------------------------------------------------


def test_parse_the_live_grid_message():
    from macro.sphere_game import parse_clicks_allowed

    budget = parse_clicks_allowed(LIVE_MESSAGE)
    assert budget == 4
    fleet = parse_ot_fleet(LIVE_MESSAGE, clicks_budget=budget)
    assert fleet is not None
    assert fleet.n_colors == 6
    assert fleet.two_ships == 2
    assert fleet.clicks_budget == 4


@pytest.mark.parametrize("text", ["", "Number of different colors: 5", "colors: 12"])
def test_parse_rejects_anything_that_is_not_an_ot_fleet(text):
    assert parse_ot_fleet(text) is None


def test_more_colours_mean_a_more_valuable_unknown_ship():
    values = [expected_two_cell_sp(fleet_for_colors(n), set()) for n in (6, 7, 8, 9)]
    assert values == sorted(values)
    # Was 90.9 while `OT_RARE_WEIGHTS` borrowed the $oh spawn rates. Those
    # predicted 0.2 rainbow ships across the 26 rare slots of KNOWN_BOARDS,
    # where 3 turned up, so an unidentified length-2 cell was worth far more
    # than the solver thought.
    assert values[0] == pytest.approx(116.4, abs=0.5)


def test_seeing_a_colour_removes_it_from_the_unknown_pool():
    fleet = fleet_for_colors(9)
    before = expected_two_cell_sp(fleet, set())
    after = expected_two_cell_sp(fleet, {"W"})
    assert after < before  # rainbow was the biggest thing left to hope for


# --- Policy -----------------------------------------------------------------


def test_finding_every_blue_makes_the_rest_free():
    """The perfect game: once the empties are known, every ship cell is certain."""
    board = KNOWN_BOARDS[0]["cells"]
    fleet = fleet_for_colors(len(set(board)))
    observations = {
        index: BLUE for index, colour in enumerate(board) if colour == BLUE
    }
    marginals = enumerate_ot(fleet, observations)
    hidden = [cell for cell in range(GRID_CELLS) if cell not in observations]
    assert marginals.total > 0
    assert all(marginals.is_certain_ship(cell) for cell in hidden)
    # With everything certain the pick is the most valuable cell, not a probe.
    choice = choose_ot_cell(fleet, observations, hidden, marginals=marginals)
    assert marginals.ev(choice) == max(marginals.ev(cell) for cell in hidden)


def test_the_probe_never_picks_a_known_blue():
    fleet = fleet_for_colors(7)
    observations = {0: BLUE, 1: BLUE, 2: BLUE}
    hidden = [cell for cell in range(GRID_CELLS) if cell not in observations]
    for policy in ("greedy", "safe", "risk", "mixed"):
        choice = choose_ot_cell(fleet, observations, hidden, policy=policy)
        assert choice in hidden


def test_the_safe_policy_really_does_minimise_blue_risk():
    fleet = fleet_for_colors(6)
    hidden = list(range(GRID_CELLS))
    marginals = enumerate_ot(fleet, {})
    choice = choose_ot_cell(fleet, {}, hidden, marginals=marginals, policy="safe")
    assert marginals.p_blue(choice) == min(marginals.p_blue(c) for c in hidden)


def test_no_click_once_the_blue_budget_is_gone_without_extra_chance():
    """The old reading is a *state*, so the solver can short-circuit it.

    Under Extra Chance it is an event instead — the same (4 blues, 5 hits) is a
    finished board if the blue came last and a live one if the ship hit did — so
    there the caller must ask `ot_game_over` after each blue and this returns a
    cell either way. See `test_extra_chance_keeps_playing_past_the_budget`.
    """
    fleet = fleet_for_colors(6)
    buttons = _buttons()
    assert choose_ot_click(buttons, {}, fleet=fleet, blues_spent=0) is not None
    assert (
        choose_ot_click(
            buttons,
            {},
            fleet=fleet,
            blues_spent=DEFAULT_CLICKS_BUDGET,
            extra_chance=False,
        )
        is None
    )


def test_extra_chance_keeps_playing_past_the_budget():
    fleet = fleet_for_colors(6)
    buttons = _buttons()
    for hits in (0, EXTRA_CHANCE_SHIP_HITS, EXTRA_CHANCE_SHIP_HITS + 3):
        assert (
            choose_ot_click(
                buttons,
                {},
                fleet=fleet,
                blues_spent=DEFAULT_CLICKS_BUDGET + 2,
                ship_hits=hits,
            )
            is not None
        ), hits


@pytest.mark.parametrize(
    "blues, hits, extra, expected",
    [
        # Nothing under the budget can ever end a board.
        (0, 0, True, False),
        (3, 9, True, False),
        # The 4th blue: fatal at 5 hits, granted below.
        (4, 5, True, True),
        (4, 4, True, False),
        (4, 0, True, False),
        # ...and it stays grantable however many blues pile up, which is what
        # makes a perfect game 8 Extra Chances on an 11-blue board.
        (11, 0, True, False),
        (11, 5, True, True),
        # Without Extra Chance the 4th blue always ends it.
        (4, 0, False, True),
        (3, 0, False, False),
    ],
)
def test_the_end_condition_is_the_one_the_logs_showed(blues, hits, extra, expected):
    """Ten logged games split on exactly this predicate.

    Nine reached their 4th blue with 6-16 ship hits and the grid locked; the
    tenth reached it with 3 and the grid stayed live, so the macro stopped on a
    playable board.
    """
    assert ot_game_over(blues, hits, extra_chance=extra) is expected


def test_no_click_when_every_cell_is_already_revealed():
    fleet = fleet_for_colors(6)
    board = KNOWN_BOARDS[0]["cells"]
    observations = {index: colour for index, colour in enumerate(board)}
    buttons = _buttons(board, taken=set(range(GRID_CELLS)))
    assert choose_ot_click(buttons, observations, fleet=fleet) is None


def test_inconsistent_observations_still_return_a_playable_cell():
    """A misread colour count must not stall the game loop."""
    fleet = fleet_for_colors(6)
    observations = {0: "O", 24: "O"}
    hidden = [cell for cell in range(GRID_CELLS) if cell not in observations]
    assert choose_ot_cell(fleet, observations, hidden) in hidden


def test_solver_stats_describe_the_phase_and_the_pick():
    fleet = fleet_for_colors(6)
    stats = solver_stats(fleet, {})
    assert stats["configurations"] == CONFIGURATIONS[6]
    # An empty board with Extra Chance live is the hunt, not a plain probe —
    # the phase name has to say so, or holding certain ships back would read as
    # the solver ignoring free SP.
    assert stats["phase"] == "hunt"
    assert 0 <= stats["best_index"] < GRID_CELLS
    assert stats["best_ev"] > OT_CELL_SP[BLUE]
    text = format_solver_stats(fleet, {})
    assert "placements" in text and "hunt" in text
    assert "no fleet placement" in format_solver_stats(fleet, {0: "O", 24: "O"})

    after = solver_stats(fleet, {}, ship_hits=EXTRA_CHANCE_SHIP_HITS)
    assert after["phase"] == "probe"
    assert solver_stats(fleet, {}, policy="risk")["phase"] == "probe"


def test_the_uniform_sampler_reproduces_the_exact_marginals():
    """Sampling walks the same counting DP, so it must agree with it.

    P(triple) is proportional to how many boards that triple admits, and the
    dominoes are then drawn uniformly inside it — which makes every
    configuration equally likely. If the two ever disagree, the ``uniform``
    arm of the bakeoff is measuring a different game than the solver plays.
    """
    import random

    from macro.ot_solver import sample_fleet_placement

    fleet = fleet_for_colors(6)
    exact = enumerate_ot(fleet, {})
    rng = random.Random(4)
    trials = 4000
    empty = [0] * GRID_CELLS
    for _ in range(trials):
        teal, green, yellow, dominoes = sample_fleet_placement(fleet, rng)
        occupied = teal | green | yellow
        for domino in dominoes:
            occupied |= domino
        assert occupied.bit_count() == fleet.ship_cells
        for cell in range(GRID_CELLS):
            if not occupied >> cell & 1:
                empty[cell] += 1
    for cell in range(GRID_CELLS):
        assert empty[cell] / trials == pytest.approx(exact.p_blue(cell), abs=0.04)


def test_the_shipped_probe_rule_is_the_one_that_was_measured():
    """Pin the policy and its tuning so a change has to be deliberate.

    `greedy` is the intuitive rule and it loses; the risk penalty is tuned to
    the low end of the winning plateau because higher values have a demonstrated
    collapse on a real board. The blue bonus is the same expression with the
    opposite sign, applied only while Extra Chance is live. Changing any of
    these should mean re-running `scripts/ot_bakeoff.py`, not editing a
    constant.
    """
    from macro.ot_solver import (
        DEFAULT_PROBE_POLICY,
        EXTRA_CHANCE,
        OT_BLUE_BONUS_SP,
        RISK_PENALTY_SP,
    )

    assert EXTRA_CHANCE is True
    assert DEFAULT_PROBE_POLICY == "hunt"
    assert RISK_PENALTY_SP == 60.0
    assert OT_BLUE_BONUS_SP == 600.0


def test_the_blue_bonus_is_off_where_it_measured_negative():
    """6-7 colours hunt; 8-9 keep the plain probe.

    At 8-9 colours there are only 5-7 blues, the four ship hits run out before
    the hunt lands one, and the bonus measured -122 SP (t = -3.52) / -161 SP
    (t = -3.57) on 120 generated boards apiece. Deferring the certain ships is
    kept at every colour count; only the bonus is switched off.
    """
    assert OT_BLUE_BONUS_COLORS == {6, 7}
    assert [blue_bonus_for(fleet_for_colors(n)) > 0 for n in (6, 7, 8, 9)] == [
        True,
        True,
        False,
        False,
    ]


def test_the_hunt_holds_certain_ships_back_until_the_phase_is_over():
    """A certain ship is free *later* but costs a ship hit *now*.

    Spending one while Extra Chance is live buys nothing — the cell stays
    collectable — and moves the board one step closer to the ending. So the
    hunt takes an uncertain cell instead, and only harvests once the phase is
    done.
    """
    # A real board, revealed just far enough that some cells have resolved and
    # most have not.
    cells = KNOWN_BOARDS[0]["cells"]
    fleet = fleet_for_colors(len(set(cells)))
    observations = {index: cells[index] for index in range(2)}
    marginals = enumerate_ot(fleet, observations)
    hidden = [index for index in range(GRID_CELLS) if index not in observations]
    certain = {cell for cell in hidden if marginals.is_certain_ship(cell)}
    uncertain = [cell for cell in hidden if cell not in certain]
    assert certain and uncertain, "this board no longer exercises the choice"

    during = choose_ot_cell(fleet, observations, hidden, policy="hunt", ship_hits=0)
    assert during in uncertain

    after = choose_ot_cell(
        fleet, observations, hidden, policy="hunt", ship_hits=EXTRA_CHANCE_SHIP_HITS
    )
    assert after in certain


def test_a_zero_penalty_is_exactly_the_greedy_rule():
    """The penalty spans the whole family, so the named rules are its endpoints."""
    fleet = fleet_for_colors(7)
    observations = {0: BLUE, 6: "T", 24: BLUE}
    hidden = [cell for cell in range(GRID_CELLS) if cell not in observations]
    greedy = choose_ot_cell(fleet, observations, hidden, policy="greedy")
    as_risk = choose_ot_cell(
        fleet, observations, hidden, policy="risk", risk_penalty=0.0
    )
    assert as_risk == greedy
    # ...and a huge penalty collapses onto the safest cell, which is `safe`.
    safest = choose_ot_cell(fleet, observations, hidden, policy="safe")
    extreme = choose_ot_cell(
        fleet, observations, hidden, policy="risk", risk_penalty=1e6
    )
    assert extreme == safest
