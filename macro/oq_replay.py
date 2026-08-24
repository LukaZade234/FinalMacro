"""Replay all 12,650 $oq worlds against a hunt policy.

Used for the MIXED vs entropy bake-off. After three purples Mudae auto-reveals
the 4th as a clickable red; harvest / red-claim still go through
``choose_oq_click`` so the score matches live play.
"""

from __future__ import annotations

from typing import Any

from macro.minigame_board import GRID_CELLS, build_session, make_click
from macro.oq_solver import (
    CLICK_BUDGET,
    HUNT_POLICY_MIXED,
    choose_oq_click,
    is_paid_reveal,
)
import macro.oq_worlds as oq_worlds
from macro.oq_worlds import ensure_built

_OQ_STATE_TO_EMOJI = {
    "t": "spP",
    "r": "spR",
    "0": "spB",
    "1": "spT",
    "2": "spG",
    "3": "spY",
    "4": "spO",
}


def _btn(index: int, emoji: str = "spU", *, disabled: bool = False) -> dict[str, Any]:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def truth_grid(world_index: int) -> dict[int, str]:
    ensure_built()
    outcome = oq_worlds.WORLD_OUTCOMES[world_index]
    mapping = {-1: "t", 0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}
    return {index: mapping[value] for index, value in enumerate(outcome)}


def reveal_oq_cell(
    truth: dict[int, str], observations: dict[int, str], index: int
) -> str:
    """Colour shown after clicking ``index`` (4th purple is already red)."""
    color = truth[index]
    if color == "t" and sum(1 for value in observations.values() if value == "t") >= 3:
        return "r"
    return color


def auto_reveal_fourth_purple(
    truth: dict[int, str], observations: dict[int, str]
) -> int | None:
    """If 3 purples are found, the unclicked 4th becomes a visible red.

    The cell stays clickable until claimed. Returns its index, or ``None``.
    """
    if sum(1 for value in observations.values() if value == "t") < 3:
        return None
    if any(value == "r" for value in observations.values()):
        return None
    for index, color in truth.items():
        if color == "t" and index not in observations:
            observations[index] = "r"
            return index
    return None


def _buttons_for(
    observations: dict[int, str], clicked: set[int]
) -> list[dict[str, Any]]:
    buttons = [_btn(index) for index in range(GRID_CELLS)]
    for index, color in observations.items():
        emoji = _OQ_STATE_TO_EMOJI[color]
        buttons[index] = _btn(index, emoji, disabled=index in clicked)
    return buttons


def _final_board(truth: dict[int, str], observations: dict[int, str]) -> list[str]:
    found = sum(1 for value in observations.values() if value in {"t", "r"})
    board: list[str] = []
    for index in range(GRID_CELLS):
        color = observations.get(index)
        if color is None:
            color = truth[index]
            if color == "t" and found >= 3:
                color = "r"
        board.append(_OQ_STATE_TO_EMOJI[color])
    return board


def simulate_oq_world(
    world_index: int,
    *,
    hunt_policy: str = HUNT_POLICY_MIXED,
    budget: int = CLICK_BUDGET,
) -> dict[str, Any]:
    """Play one world to completion. Returns a minigame session dict."""
    truth = truth_grid(world_index)
    observations: dict[int, str] = {}
    clicked: set[int] = set()
    clicks: list[dict[str, Any]] = []
    paid = 0
    for _ in range(budget + 4):
        auto_reveal_fourth_purple(truth, observations)
        buttons = _buttons_for(observations, clicked)
        choice = choose_oq_click(
            buttons,
            observations,
            clicks_spent=paid,
            clicks_budget=budget,
            hunt_policy=hunt_policy,
        )
        if choice is None:
            break
        index = int(choice["custom_id"].split("s")[1])
        reveal = reveal_oq_cell(truth, observations, index)
        observations[index] = reveal
        clicked.add(index)
        paid_click = is_paid_reveal(reveal)
        clicks.append(make_click(index, _OQ_STATE_TO_EMOJI[reveal], paid=paid_click))
        if paid_click:
            paid += 1
        if paid >= budget:
            break
    session = build_session(
        "oq",
        clicks,
        _final_board(truth, observations),
        clicks_paid=paid,
        clicks_budget=budget,
        reason="done",
    )
    session["world_index"] = world_index
    return session


def score_oq_policy(
    hunt_policy: str = HUNT_POLICY_MIXED,
    *,
    world_indices: list[int] | None = None,
    budget: int = CLICK_BUDGET,
) -> dict[str, Any]:
    """Replay worlds and return win rate + average base SP."""
    ensure_built()
    indices = world_indices
    if indices is None:
        indices = list(range(len(oq_worlds.ALL_WORLDS)))
    wins = 0
    total_sp = 0
    games = 0
    for world_index in indices:
        session = simulate_oq_world(
            world_index, hunt_policy=hunt_policy, budget=budget
        )
        games += 1
        if session["won"]:
            wins += 1
        total_sp += int(session["base_value"])
    return {
        "policy": hunt_policy,
        "games": games,
        "wins": wins,
        "win_rate": (wins / games) if games else 0.0,
        "avg_base_sp": (total_sp / games) if games else 0.0,
        "total_base_sp": total_sp,
    }
