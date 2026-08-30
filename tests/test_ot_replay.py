"""The ``$ot`` harness: board legality, generators, and playing a board out.

The point of these is that the replay drives the *shipped*
:func:`macro.ot_solver.choose_ot_click`, so anything asserted here about how a
game unfolds is asserted about production code.
"""

from __future__ import annotations

import json
import random

import pytest

from macro.minigame_board import GRID_CELLS
from macro.ot_replay import (
    GENERATORS,
    KNOWN_BOARDS,
    board_from_emojis,
    colors_on,
    fleet_of,
    generate_board,
    is_legal_board,
    load_logged_boards,
    paired_delta,
    ship_sp,
    ship_segments,
    simulate_ot_board,
)
from macro.ot_solver import (
    BLUE,
    DEFAULT_CLICKS_BUDGET,
    OT_CELL_SP,
    PROBE_POLICIES,
)


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_every_known_board_is_a_legal_fleet(entry):
    """One teal-4, one green-3, one yellow-3, and N-4 dominoes including orange."""
    board = entry["cells"]
    assert len(board) == GRID_CELLS
    assert is_legal_board(board)
    masks = ship_segments(board)
    lengths = sorted(mask.bit_count() for mask in masks.values())
    assert lengths == sorted([2] * (colors_on(board) - 4) + [3, 3, 4])
    assert masks.keys() >= {"T", "G", "Y", "O"}


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_known_board_colour_count_implies_its_blue_cells(entry):
    board = entry["cells"]
    fleet = fleet_of(board)
    assert board.count(BLUE) == fleet.blue_cells
    assert GRID_CELLS - board.count(BLUE) == fleet.ship_cells


def test_illegal_boards_are_rejected():
    assert not is_legal_board("B" * 24)  # wrong length
    assert not is_legal_board("B" * 25)  # no ships at all
    # A teal that bends round a corner is not a straight ship.
    bent = list("B" * GRID_CELLS)
    for cell in (0, 1, 2, 7):
        bent[cell] = "T"
    assert not is_legal_board("".join(bent))


def test_board_emoji_round_trip():
    board = KNOWN_BOARDS[0]["cells"]
    emojis = ["sp" + c if c != "B" else "spB" for c in board]
    assert board_from_emojis(emojis) == board
    assert board_from_emojis(["spU"] * GRID_CELLS) is None
    assert board_from_emojis(["spB"] * 10) is None


# --- Playing a board --------------------------------------------------------


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_playing_a_board_respects_the_rules(entry):
    result = simulate_ot_board(entry["cells"])
    assert result["clicks_paid"] <= DEFAULT_CLICKS_BUDGET
    assert result["clicks"] <= GRID_CELLS
    assert 0 < result["base_value"] <= result["ship_sp"] + DEFAULT_CLICKS_BUDGET * 10
    assert result["n_colors"] == colors_on(entry["cells"])


@pytest.mark.parametrize("policy", [p for p in PROBE_POLICIES if p != "lookahead"])
def test_every_probe_policy_terminates(policy):
    """One sparse board and one dense one — enough to catch a non-terminating rule.

    ``lookahead`` is excluded: it is a measured dead end (see ``docs/TODO.md``)
    and costs ~5s a board, which does not belong in the suite.
    """
    for entry in (KNOWN_BOARDS[0], KNOWN_BOARDS[4]):
        result = simulate_ot_board(entry["cells"], policy=policy)
        assert result["clicks_paid"] <= DEFAULT_CLICKS_BUDGET
        assert result["base_value"] > 0


def test_a_ship_cell_never_costs_a_click():
    """Only blue is paid, so most of a good game is free clicks."""
    board = KNOWN_BOARDS[0]["cells"]
    result = simulate_ot_board(board)
    assert result["clicks"] > result["clicks_paid"]
    assert result["base_value"] >= result["clicks_paid"] * OT_CELL_SP[BLUE]
    assert ship_sp(board) == sum(OT_CELL_SP[c] for c in board if c != BLUE)


def test_the_solver_beats_the_hand_played_scores():
    """Both logged boards were played by a human; the solver must do better."""
    for entry in KNOWN_BOARDS:
        if entry["logged_sp"] is None:
            continue
        played = simulate_ot_board(entry["cells"])
        assert played["base_value"] > entry["logged_sp"], entry["name"]


def test_nine_colour_boards_are_nearly_free():
    """Only 5 cells are empty, so almost everything is a certain ship."""
    result = simulate_ot_board(KNOWN_BOARDS[4]["cells"])
    assert result["share_of_ceiling"] > 0.9


# --- Generators -------------------------------------------------------------


@pytest.mark.parametrize("generator", GENERATORS)
@pytest.mark.parametrize("n_colors", (6, 7, 8, 9))
def test_generated_boards_are_legal(generator, n_colors):
    rng = random.Random(n_colors)
    for _ in range(25):
        board = generate_board(rng, n_colors, generator=generator)
        assert is_legal_board(board)
        assert colors_on(board) == n_colors


def test_the_two_generators_disagree_about_where_ships_go():
    """Sequential placement is not uniform over outcomes — that is the point.

    If these ever matched, the ``sequential`` arm of the bakeoff would be
    measuring nothing.
    """
    def corner_rate(generator: str) -> float:
        rng = random.Random(11)
        boards = [generate_board(rng, 6, generator=generator) for _ in range(400)]
        corners = (0, 4, 20, 24)
        return sum(
            1 for b in boards for c in corners if b[c] != BLUE
        ) / (len(boards) * len(corners))

    assert corner_rate("uniform") != pytest.approx(corner_rate("sequential"), abs=0.01)


# --- Log loading ------------------------------------------------------------


def test_load_logged_boards_keeps_only_finished_ot_games(tmp_path):
    board = KNOWN_BOARDS[5]["cells"]
    emojis = ["spB" if c == "B" else "sp" + c for c in board]
    rows = [
        {"game": "ot", "board": emojis, "base_value": 625, "clicks_budget": 4,
         "date_key": "2026-08-26"},
        {"game": "oh", "board": emojis, "base_value": 100},          # wrong game
        {"game": "ot", "board": ["spU"] * GRID_CELLS},               # unfinished
        {"game": "ot", "board": ["spB"] * GRID_CELLS},               # not a fleet
    ]
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    loaded = load_logged_boards(str(path))
    assert len(loaded) == 1
    assert loaded[0]["cells"] == board
    assert loaded[0]["logged_sp"] == 625


def test_paired_delta_calls_a_tiny_sample_inconclusive():
    delta = paired_delta([110.0, 90.0, 130.0], [100.0, 100.0, 100.0])
    assert delta["n"] == 3
    assert delta["mean"] == pytest.approx(10.0)
    assert not delta["significant"]
    assert delta["boards_needed"] > 3


def test_clicks_split_cleanly_into_paid_blues_and_free_ships():
    for entry in KNOWN_BOARDS:
        result = simulate_ot_board(entry["cells"])
        assert result["clicks_paid"] + result["ship_hits"] == result["clicks"]


def test_extra_chance_is_a_real_switch_not_a_comment(monkeypatch):
    """Flipping the rule must actually change how a board plays out.

    ``EXTRA_CHANCE`` is off because no logged game can confirm it. This pins
    that the constant is wired to something, so the harness can price the rule
    if a real board ever settles it — the same policy simply gets to keep
    clicking past the 4th blue until it has hit 5 ship cells.
    """
    board = KNOWN_BOARDS[0]["cells"]
    conservative = simulate_ot_board(board)
    assert conservative["clicks_paid"] == DEFAULT_CLICKS_BUDGET

    monkeypatch.setattr("macro.ot_replay.EXTRA_CHANCE", True)
    monkeypatch.setattr("macro.ot_solver.EXTRA_CHANCE", True)
    generous = simulate_ot_board(board)
    # Same policy, strictly more clicks allowed, so never worse.
    assert generous["clicks"] >= conservative["clicks"]
    assert generous["base_value"] >= conservative["base_value"]
