"""Tests for the $oc leftover-click lookahead (docs/TODO.md).

Covers the two fixes over the pre-lookahead solver:
  1. Collect-phase EV is remaining-need-aware, not a stale fixed weight.
  2. Hunt-phase widens the "guess red directly" threshold once clicks are
     scarce, instead of always chasing information gain.

Plus the guards added after auditing that work against 100 real logged
boards: ``expected_click_value`` must not drift, and the synthetic board
generator must keep matching the measured colour distribution.
"""

from __future__ import annotations

import random

import pytest

from macro import oc_solver
from macro.oc_replay import (
    _legacy_choose_oc_click,
    _legacy_pick_collect_click,
    generate_synthetic_board,
    load_logged_boards,
    paired_delta,
    random_red_index,
    replay_logged_boards,
    score_oc_trials,
    simulate_oc_board,
)


def _original_expected_click_value(index: int, observations: dict[int, str]) -> float:
    """The pre-refactor implementation, kept verbatim as a reference."""
    reds = oc_solver.constraint_red_candidates(observations)
    if not reds:
        return 0.0
    total = 0.0
    for red in reds:
        if index == red:
            total += oc_solver._OC_COLOR_VALUE["R"]
        elif index in oc_solver._orthogonal_neighbours(red):
            total += oc_solver._OC_COLOR_VALUE["O"] * 0.5
        elif oc_solver._on_diagonal_line(red, index) and index != oc_solver.CENTER_INDEX:
            total += oc_solver._OC_COLOR_VALUE["Y"] * 0.4
        elif oc_solver._same_row(red, index) or oc_solver._same_col(red, index):
            total += oc_solver._OC_COLOR_VALUE["G"] * 0.35
        elif oc_solver._blue_forbidden(red, index):
            total += oc_solver._OC_COLOR_VALUE["T"] * 0.25
        else:
            total += oc_solver._OC_COLOR_VALUE["B"]
    return total / len(reds)


@pytest.mark.parametrize(
    "observations",
    [
        {},
        {16: "B"},
        {16: "B", 8: "B"},
        {1: "O"},
        {0: "Y", 7: "B"},
        {6: "Y", 3: "O"},
        {0: "R"},
    ],
)
def test_expected_click_value_matches_original_for_every_cell(observations):
    """Pins all 25 cells, including the centre.

    Reusing ``_hunt_outcome_buckets`` once silently dropped this
    function's ``index != CENTER_INDEX`` guard, changing its value at
    cell 12 only. Nothing caught it because no decision path clicks the
    centre; this test is that catch.
    """
    for cell in range(oc_solver.GRID_CELLS):
        assert oc_solver.expected_click_value(cell, observations) == pytest.approx(
            _original_expected_click_value(cell, observations)
        )


def test_colour_values_are_real_base_sp():
    """The solver must maximise the SP the game actually pays."""
    from mudae.constants import SPHERE_BASE_SP

    assert oc_solver._OC_COLOR_VALUE == {
        "R": SPHERE_BASE_SP["spR"],
        "O": SPHERE_BASE_SP["spO"],
        "Y": SPHERE_BASE_SP["spY"],
        "G": SPHERE_BASE_SP["spG"],
        "T": SPHERE_BASE_SP["spT"],
        "B": SPHERE_BASE_SP["spB"],
    }


def test_region_click_ev_drops_to_teal_once_satisfied():
    # Both oranges already found: a hidden ortho-neighbour cell can no
    # longer be orange, so its EV must equal the teal (miss) value exactly
    # — not the stale 0.5-weighted orange guess the old fallback used.
    ev = oc_solver._region_click_ev("O", needed=0, pool=2)
    assert ev == oc_solver._OC_COLOR_VALUE["T"]


def test_region_click_ev_blends_by_true_remaining_fraction():
    ev = oc_solver._region_click_ev("O", needed=1, pool=2)
    expected = 0.5 * oc_solver._OC_COLOR_VALUE["O"] + 0.5 * oc_solver._OC_COLOR_VALUE["T"]
    assert ev == pytest.approx(expected)


def test_region_click_ev_other_is_guaranteed_blue():
    assert oc_solver._region_click_ev("other", needed=0, pool=5) == oc_solver._OC_COLOR_VALUE["B"]


def test_collect_state_excludes_center_index_from_other_pool():
    # Red at a corner: center isn't geometrically eligible for any region,
    # so it must not appear in the catch-all "other" pool either — matching
    # the rest of the solver, which never treats center as a click target
    # when nothing needs it.
    red = 0
    observations = {red: "R"}
    hidden = [1, 5, oc_solver.CENTER_INDEX]
    _state, cells = oc_solver._collect_state(red, observations, hidden)
    assert oc_solver.CENTER_INDEX not in cells["other"]


def test_collect_state_keeps_center_index_as_a_real_orange_candidate():
    # Red at index 7 (row 1, col 2): center (12) is a genuine orthogonal
    # neighbour and can legitimately be one of the two oranges. Excluding
    # it here (as an earlier version of this fix did) forfeits real SP the
    # legacy policy still collects, which a synthetic-board regression run
    # caught as a consistent negative uplift at every budget >= 4.
    red = 7
    assert oc_solver.CENTER_INDEX in oc_solver._orthogonal_neighbours(red)
    observations = {red: "R"}
    hidden = [oc_solver.CENTER_INDEX, 3, 11]
    _state, cells = oc_solver._collect_state(red, observations, hidden)
    assert oc_solver.CENTER_INDEX in cells["O"]


def test_collect_ev_is_exact_once_a_region_is_satisfied():
    """Red at a corner (index 0), every colour quota already met.

    A leftover row/col cell is then geometrically *guaranteed* teal, and a
    cell outside red's row/col/diagonal is guaranteed blue. The need-aware
    EV must price the teal cell at exactly its base SP (20), because there
    is no uncertainty left. ``expected_click_value`` still underprices it
    (12.25) — it applies a fixed 0.35 "might be green" weight even though
    no greens remain. That stale weight is the flaw this replaced.

    Both pickers happen to choose the same cell here *since* the value
    table was aligned to real ``SPHERE_BASE_SP``; under the old rank-based
    table blue was overvalued (14 vs a true 10) and the legacy fallback
    picked the blue cell instead. The valuation, not the pick, is the
    invariant worth pinning.
    """
    red = 0
    observations = {
        red: "R",
        1: "O", 5: "O",           # both oranges found
        6: "Y", 18: "Y", 24: "Y",  # all three yellows found
        2: "G", 3: "G", 4: "G", 10: "G",  # all four greens found
    }
    leftover_green_region = 15  # row/col cell beyond the green quota -> must be teal
    other_cell = 7  # outside red's row/col/diagonal -> must be blue
    hidden = [leftover_green_region, other_cell]

    state, _cells = oc_solver._collect_state(red, observations, hidden)
    assert state["G"] == (0, 1)  # no greens left to find, one cell still hidden
    assert state["other"] == (0, 1)

    # Exact, because nothing is uncertain any more.
    assert oc_solver._region_click_ev("G", 0, 1) == oc_solver._OC_COLOR_VALUE["T"]
    assert oc_solver._region_click_ev("other", 0, 1) == oc_solver._OC_COLOR_VALUE["B"]

    # The old EV still underprices the guaranteed-teal cell.
    assert oc_solver.expected_click_value(leftover_green_region, observations) < (
        oc_solver._OC_COLOR_VALUE["T"]
    )

    assert oc_solver._pick_collect_click(red, observations, hidden, clicks_left=1) == (
        leftover_green_region
    )
    assert _legacy_pick_collect_click(red, observations, hidden) == leftover_green_region


def test_collect_lookahead_prefers_higher_value_region_when_budget_allows():
    red = 0
    observations = {red: "R"}
    hidden = [1, 5, 6, 18, 24, 2, 3, 4, 10, 15, 20, 7]  # O, Y, G pools + one "other"
    pick = oc_solver._pick_collect_click(red, observations, hidden, clicks_left=5)
    # Orange (91) dominates every other region's EV at full need — the
    # lookahead should still start there, same as the old priority order.
    assert pick in {1, 5}


def test_hunt_guesses_directly_once_candidates_fit_in_clicks_left():
    # Yellow at cell 0, blue at cell 7 narrows red to exactly 3 candidates
    # (0, 18, 24) — too many for the old unconditional "<=2" guess
    # threshold, but exactly HUNT_LOOKAHEAD_CLICKS, and not reachable via
    # the (unrelated) orange-adjacent heuristic.
    observations = {0: "Y", 7: "B"}
    reds = oc_solver.constraint_red_candidates(observations)
    assert reds == [0, 18, 24]
    assert len(reds) == oc_solver.HUNT_LOOKAHEAD_CLICKS
    hidden = [index for index in range(25) if index not in observations and index != oc_solver.CENTER_INDEX]

    # Plenty of clicks left: old behaviour — info gain, no direct guess yet.
    plenty = oc_solver._pick_hunt_click(observations, hidden, clicks_left=10)
    assert plenty not in reds

    # Clicks scarce and candidates fit within them: guess directly.
    scarce = oc_solver._pick_hunt_click(observations, hidden, clicks_left=3)
    assert scarce in reds


def test_hunt_keeps_info_gain_when_clicks_are_not_scarce():
    observations = {0: "Y", 7: "B"}
    hidden = [index for index in range(25) if index not in observations and index != oc_solver.CENTER_INDEX]
    reds = oc_solver.constraint_red_candidates(observations)
    assert len(reds) == 3
    # No clicks_left signalled at all -> unchanged from pre-lookahead
    # behaviour: unconditional "<=2" guess threshold, so 3 candidates means
    # keep gathering information.
    unspecified = oc_solver._pick_hunt_click(observations, hidden, clicks_left=None)
    assert unspecified not in reds


def test_choose_oc_click_threads_clicks_left_into_collect_phase():
    red = 0
    observations = {
        red: "R",
        1: "O", 5: "O", 6: "Y", 18: "Y", 24: "Y", 2: "G", 3: "G", 4: "G", 10: "G",
    }
    buttons = []
    for index in range(25):
        emoji = {"R": "sp"}.get(observations.get(index), "spU")
        if index in observations and index != red:
            color_emoji = {"O": "spO", "Y": "spY", "G": "spG"}[observations[index]]
            emoji = color_emoji
        buttons.append(
            {
                "emoji": emoji,
                "custom_id": f"cmd s{index}",
                "kind": "sphere",
                "disabled": index in observations and index != 15 and index != 7,
            }
        )
    choice = oc_solver.choose_oc_click(
        buttons, observations, clicks_spent=8, clicks_budget=9,
    )
    assert choice is not None
    picked_index = int(choice["custom_id"].split("s")[1])
    assert picked_index == 15  # same reasoning as the isolated collect test above


def test_lookahead_never_regresses_average_sp_across_synthetic_boards():
    """A/B against the frozen legacy policy on the same synthetic boards.

    Not a claim about Mudae's real generator (macro/oc_replay.py) — just a
    regression guard that the lookahead doesn't lose SP on average versus
    the policy it replaces.
    """
    trials = 800
    legacy = score_oc_trials(trials=trials, budget=5, seed=7, policy="legacy")
    lookahead = score_oc_trials(trials=trials, budget=5, seed=7, policy="lookahead")
    assert lookahead["avg_sp"] >= legacy["avg_sp"] * 0.99


def test_simulate_oc_board_terminates_and_spends_full_budget_when_possible():
    import random

    rng = random.Random(3)
    red = random_red_index(rng)
    truth = generate_synthetic_board(red, rng)
    session = simulate_oc_board(truth, budget=5, rng=random.Random(1), policy="lookahead")
    assert session["clicks_paid"] == 5
    assert session["base_value"] > 0


def test_legacy_choose_oc_click_matches_original_fixed_priority():
    """Anchor: the frozen legacy re-implementation still behaves like the
    pre-lookahead solver (always finishes orange before yellow before
    green), so the A/B comparisons above are against a faithful baseline.
    """
    red = 0
    observations = {red: "R"}
    hidden = [1, 5, 6, 18, 24, 2, 3, 4, 10]
    buttons = [
        {"emoji": "spU", "custom_id": f"cmd s{i}", "kind": "sphere", "disabled": False}
        for i in range(25)
    ]
    choice = _legacy_choose_oc_click(buttons, observations, clicks_spent=0, clicks_budget=5)
    picked = int(choice["custom_id"].split("s")[1])
    assert picked in {1, 5}  # orange first, unconditionally


# --- Synthetic generator must keep matching the real logged boards ---------

# Measured over 100 fully-revealed logged $oc boards: share of each
# geometric region that shows each colour, in percent.
_MEASURED_REGION_MIX = {
    "ortho": {"O": 63, "G": 22, "T": 15},
    "diag": {"Y": 64, "T": 36},
    "rowcol-only": {"G": 68, "T": 32},
    "outside": {"B": 97, "Y": 2, "T": 1},
}


def _region_of(cell: int, red: int) -> str:
    if cell in oc_solver._orthogonal_neighbours(red):
        return "ortho"
    if cell in oc_solver._diagonal_line_cells(red):
        return "diag"
    if cell in oc_solver._row_col_neighbours(red):
        return "rowcol-only"
    return "outside"


def _sample_generated_boards(n: int, seed: int = 0):
    rng = random.Random(seed)
    for _ in range(n):
        red = random_red_index(rng)
        yield red, generate_synthetic_board(red, rng)


def test_generated_boards_never_contradict_the_constraints():
    """The true red must survive the solver's own filtering.

    The first version of this generator mis-coloured the centre blue when
    the centre sat on red's diagonal, which eliminated the true red on a
    third of boards and silently invalidated every benchmark run on it.
    """
    for red, truth in _sample_generated_boards(1500, seed=11):
        observations = {i: c for i, c in truth.items() if i != red}
        assert red in oc_solver.constraint_red_candidates(observations)


def test_generated_boards_have_the_real_colour_counts():
    for _red, truth in _sample_generated_boards(400, seed=12):
        counts = {c: sum(1 for v in truth.values() if v == c) for c in "ROYG"}
        assert counts == {"R": 1, "O": 2, "Y": 3, "G": 4}


def test_generated_boards_match_the_measured_region_mix():
    """Within 3pp of the 100-board measurement, per region and colour."""
    tally: dict[str, dict[str, int]] = {r: {} for r in _MEASURED_REGION_MIX}
    for red, truth in _sample_generated_boards(3000, seed=13):
        for cell, colour in truth.items():
            if cell == red:
                continue
            bucket = tally[_region_of(cell, red)]
            bucket[colour] = bucket.get(colour, 0) + 1

    for region, expected in _MEASURED_REGION_MIX.items():
        total = sum(tally[region].values())
        assert total > 0
        for colour, pct in expected.items():
            got = tally[region].get(colour, 0) / total * 100
            assert abs(got - pct) <= 3, f"{region}/{colour}: {got:.1f}% vs measured {pct}%"


def test_greens_do_appear_on_orthogonal_cells():
    """22% of orthogonal cells are green on real boards.

    An earlier generator excluded this outright, which is what made a
    proposed "disjoint regions" change look correct when it was not.
    """
    greens = ortho = 0
    for red, truth in _sample_generated_boards(600, seed=14):
        for cell in oc_solver._orthogonal_neighbours(red):
            ortho += 1
            greens += truth[cell] == "G"
    assert ortho and 0.15 <= greens / ortho <= 0.30


# --- Paired statistics ------------------------------------------------------


def test_paired_delta_flags_an_underpowered_sample():
    """A handful of large, cancelling deltas must not read as a result."""
    base = [300] * 30
    new = [300] * 22 + [220, 380, 300, 255, 300, 220, 370, 300]
    stat = paired_delta(new, base)
    assert stat["n"] == 30
    assert not stat["significant"]
    assert stat["ci_low"] < 0 < stat["ci_high"]
    assert stat["boards_needed"] > stat["n"]


def test_paired_delta_reports_a_clean_difference():
    stat = paired_delta([310] * 40, [300] * 40)
    assert stat["mean"] == pytest.approx(10.0)
    assert stat["changed"] == 40
    assert stat["stdev"] == 0.0  # identical deltas -> no spread to test against


def test_paired_delta_handles_no_change():
    stat = paired_delta([300] * 10, [300] * 10)
    assert stat["mean"] == 0.0
    assert stat["changed"] == 0
    assert not stat["significant"]


# --- Real logged boards -----------------------------------------------------


def _write_log(tmp_path, rows, *, jsonl: bool):
    import json

    path = tmp_path / ("log.jsonl" if jsonl else "log.json")
    if jsonl:
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    else:
        path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


def _logged_row(truth: dict[int, str], red: int, **over):
    emoji = {"R": "spR", "O": "spO", "Y": "spY", "G": "spG", "T": "spT", "B": "spB"}
    row = {
        "game": "oc",
        "board": [emoji[truth[i]] for i in range(25)],
        "clicks_budget": 5,
        "base_value": 300,
        "date_key": "2026-08-29",
    }
    row.update(over)
    return row


@pytest.mark.parametrize("jsonl", [True, False])
def test_load_logged_boards_reads_both_log_formats(tmp_path, jsonl):
    red, truth = next(iter(_sample_generated_boards(1, seed=21)))
    path = _write_log(tmp_path, [_logged_row(truth, red)], jsonl=jsonl)
    boards = load_logged_boards(path)
    assert len(boards) == 1
    assert boards[0]["truth"] == truth
    assert boards[0]["budget"] == 5


def test_load_logged_boards_skips_rows_that_are_not_ground_truth(tmp_path):
    red, truth = next(iter(_sample_generated_boards(1, seed=22)))
    good = _logged_row(truth, red)
    partial = _logged_row(truth, red)
    partial["board"] = ["spU"] + partial["board"][1:]  # never fully revealed
    other_game = _logged_row(truth, red, game="oq")
    path = _write_log(tmp_path, [good, partial, other_game], jsonl=True)
    assert len(load_logged_boards(path)) == 1


def test_replay_logged_boards_scores_a_real_board(tmp_path):
    red, truth = next(iter(_sample_generated_boards(1, seed=23)))
    path = _write_log(tmp_path, [_logged_row(truth, red)], jsonl=True)
    result = replay_logged_boards(path, policy="lookahead")
    assert result["boards"] == 1
    assert result["avg_sp"] > 0
    assert len(result["per_board"]) == 1
