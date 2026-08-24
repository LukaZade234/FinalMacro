"""$oq MIXED vs entropy replay harness."""

from __future__ import annotations

from macro.oq_replay import score_oq_policy, simulate_oq_world
from macro.oq_solver import (
    DEFAULT_OPENING_CELL,
    HUNT_POLICY_ENTROPY,
    HUNT_POLICY_MIXED,
    filter_worlds,
    heuristic_analysis,
    states_from_observations,
)
from macro.oq_worlds import NEIGHBORS, ensure_built


def test_mixed_picks_colblitz_opening_on_empty_board():
    ensure_built()
    valid = filter_worlds(states_from_observations({}))
    cell, reason = heuristic_analysis(valid, ["?"] * 25, hunt_policy=HUNT_POLICY_MIXED)
    assert cell == DEFAULT_OPENING_CELL  # Colblitz overlay (1,1) 0-based
    assert len(NEIGHBORS[cell]) == 8
    assert reason.startswith("mixed")


def test_entropy_policy_still_available():
    ensure_built()
    valid = filter_worlds(states_from_observations({}))
    _cell, reason = heuristic_analysis(
        valid, ["?"] * 25, hunt_policy=HUNT_POLICY_ENTROPY
    )
    assert "entropy" in reason or "purple" in reason


def test_simulate_world_returns_session():
    session = simulate_oq_world(0, hunt_policy=HUNT_POLICY_MIXED)
    assert session["game"] == "oq"
    assert len(session["board"]) == 25
    assert session["clicks"]
    assert session["clicks_paid"] <= 7
    assert "spU" not in session["board"]


def test_simulate_claims_auto_revealed_fourth_purple():
    """Finding 3 purples auto-reveals the 4th as red — the sim must click it."""
    session = simulate_oq_world(0, hunt_policy=HUNT_POLICY_MIXED)
    assert session["won"]
    reds = [
        click for click in session["clicks"] if click["emoji"] in {"spR", "sp", "spW"}
    ]
    assert len(reds) == 1
    assert reds[0]["paid"] is True


def test_mixed_and_entropy_both_score_sample():
    # Stride through combination space so early worlds (all top-left) do not dominate.
    indices = list(range(0, 12_650, 80))
    mixed = score_oq_policy(HUNT_POLICY_MIXED, world_indices=indices)
    entropy = score_oq_policy(HUNT_POLICY_ENTROPY, world_indices=indices)
    assert mixed["games"] == entropy["games"] == len(indices)
    assert mixed["win_rate"] >= 0.90
    assert 0.5 < entropy["win_rate"] < 1.0
