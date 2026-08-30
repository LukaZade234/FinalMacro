"""Tests for the $oh replay harness (macro/oh_replay.py).

The harness is the only way any $oh policy change can be scored, so these
pin the game model it encodes: the spawn mix, the blue→3 / teal→1 unveil
rule, purple being free, and — the subtle one — an $oc spawn staying
face-down forever.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import pytest

from macro import oh_replay
from macro.oh_replay import (
    OC_CELL,
    OH_HIDDEN,
    OH_SPAWN_RATES,
    OH_UNVEILS,
    _visible_emoji,
    generate_board,
    load_logged_boards,
    replay_logged_boards,
    score_oh_trials,
    simulate_oh_board,
)

_LOG = Path(__file__).resolve().parent.parent / "docs" / "minigames_to_use.jsonl"


def _require_log() -> str:
    if not _LOG.exists():
        pytest.skip(f"{_LOG.name} not present (gitignored local log)")
    return str(_LOG)


# --- the board model --------------------------------------------------------


def test_spawn_rates_sum_to_100_percent():
    assert sum(OH_SPAWN_RATES.values()) == pytest.approx(100.0, abs=1e-9)


def test_generated_boards_reproduce_the_measured_spawn_mix():
    rng = random.Random(3)
    seen: Counter[str] = Counter()
    for _ in range(4000):
        seen.update(generate_board(rng))
    total = sum(seen.values())
    for kind, pct in OH_SPAWN_RATES.items():
        got = seen[kind] / total * 100
        tolerance = 0.4 if pct < 3 else 2.0
        assert abs(got - pct) <= tolerance, f"{kind}: {got:.2f}% vs {pct:.2f}%"


def test_oc_cell_looks_face_down_even_once_seen():
    """The whole reason $oc cannot be targeted."""
    assert _visible_emoji(OC_CELL, seen=True) == OH_HIDDEN
    assert _visible_emoji(OC_CELL, seen=False) == OH_HIDDEN
    assert _visible_emoji("spY", seen=True) == "spY"
    assert _visible_emoji("spY", seen=False) == OH_HIDDEN


def test_an_unveiled_oc_cell_can_still_be_clicked():
    # Every cell is $oc, so the only legal clicks are face-down ones; the
    # run must still spend its whole budget rather than stalling.
    truth = [OC_CELL] * 25
    result = simulate_oh_board(truth, rng=random.Random(1), initial_revealed=10)
    assert result["clicks_paid"] == 5
    assert result["oc_grants"] == 5


# --- click mechanics --------------------------------------------------------


def test_purple_does_not_consume_the_click_budget():
    truth = ["spP"] * 25
    result = simulate_oh_board(truth, rng=random.Random(1), initial_revealed=25)
    # Purple is free, so the budget never depletes and the loop ends only
    # when the board runs out of purples.
    assert result["clicks_paid"] == 0
    assert result["free_clicks"] == 25
    assert result["base_value"] == pytest.approx(25 * 5.0)


@pytest.mark.parametrize("kind,unveils", [("spB", 3), ("spT", 1), ("spG", 0)])
def test_unveil_counts_match_the_logged_mechanic(kind, unveils):
    """Blue exposes 3 more cells, teal 1, anything else none.

    The greedy never clicks an *already revealed* blue or teal, so the only
    way to reach the mechanic is a face-down that turns out to be one —
    which is exactly how it shows up in the logs too.
    """
    assert OH_UNVEILS == {"spB": 3, "spT": 1}
    result = simulate_oh_board(
        [kind] * 25, rng=random.Random(5), revealed_cells=[], budget=1,
    )
    assert result["clicks_paid"] == 1
    # one cell for the click itself, plus whatever it unveiled
    assert result["seen"] == 1 + unveils


def test_budget_is_respected():
    truth = ["spG"] * 25
    result = simulate_oh_board(truth, rng=random.Random(1), initial_revealed=25, budget=3)
    assert result["clicks_paid"] == 3
    assert result["base_value"] == pytest.approx(3 * 35.0)


def test_oc_grant_value_is_zero_by_default():
    """Shipped default: an untargetable random drop is not counted."""
    assert oh_replay.OC_GRANT_VALUE == 0.0
    truth = [OC_CELL] * 25
    result = simulate_oh_board(truth, rng=random.Random(1), initial_revealed=10)
    assert result["base_value"] == 0.0


# --- loading real boards ----------------------------------------------------


def _row(board, **over):
    row = {"game": "oh", "board": board, "clicks_budget": 5, "base_value": 100}
    row.update(over)
    return row


def test_load_logged_boards_labels_leftover_hidden_as_oc(tmp_path):
    board = ["spG"] * 25
    board[7] = OH_HIDDEN  # one cell never revealed in a finished game
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps(_row(board)), encoding="utf-8")
    boards = load_logged_boards(str(path))
    assert len(boards) == 1
    assert boards[0]["truth"][7] == OC_CELL


def test_load_logged_boards_drops_abandoned_games(tmp_path):
    abandoned = [OH_HIDDEN] * 13 + ["spG"] * 12  # far too many unknowns
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps(_row(abandoned)), encoding="utf-8")
    assert load_logged_boards(str(path)) == []


def test_load_logged_boards_reads_a_json_array(tmp_path):
    path = tmp_path / "log.json"
    path.write_text(json.dumps([_row(["spG"] * 25)]), encoding="utf-8")
    assert len(load_logged_boards(str(path))) == 1


def test_load_logged_boards_keeps_initial_reveals(tmp_path):
    initial = [OH_HIDDEN] * 25
    initial[4] = "spY"
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps(_row(["spG"] * 25, initial_board=initial)), encoding="utf-8")
    assert load_logged_boards(str(path))[0]["revealed_cells"] == [4]


# --- against the real log ---------------------------------------------------


def test_real_logged_boards_are_recoverable():
    boards = load_logged_boards(_require_log())
    assert len(boards) > 80
    assert all(len(b["truth"]) == 25 for b in boards)
    assert all(b["revealed_cells"] is not None for b in boards)


def test_replaying_real_boards_lands_near_live_play():
    """Calibration: the simulator should score roughly what the macro did.

    Not exact — the replay re-rolls the random unveils — so this is a loose
    band that would catch a broken model, not a regression detector.
    """
    result = replay_logged_boards(_require_log(), seeds=(0, 1, 2, 3))
    assert result["boards"] > 80
    assert result["avg_sp"] == pytest.approx(result["logged_avg_sp"], rel=0.15)


def test_synthetic_score_rises_with_more_initial_reveals():
    """The perk is worth buying even though it does not widen a solver's edge."""
    low = score_oh_trials(trials=1500, initial_revealed=1)
    high = score_oh_trials(trials=1500, initial_revealed=10)
    assert high["avg_sp"] > low["avg_sp"] * 1.15
