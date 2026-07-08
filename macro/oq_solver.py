"""Solver for the Mudae ``$oq`` (Orb Quest) sphere minigame.

Ported from the public `OQ Solver <https://orb-quest-book.pages.dev/>` world
filter + adaptive heuristic. Opening move uses the EV-optimal inner-edge cell
from that solver's basic book (cell 7 / index 7).
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

import macro.oq_worlds as oq_worlds
from macro.oq_worlds import GRID_CELLS, ensure_built

# EV-optimal opening from orb-quest-book (canon 7 · inner edge).
DEFAULT_OPENING_CELL = 7

CLICK_BUDGET = 7
TARGET_PURPLES = 3

# Orb payout during bonus harvest by adjacent-purple count (Blue..Orange).
HARVEST_VALUE = (10, 20, 35, 55, 90)

OQ_COLORS = frozenset({"0", "1", "2", "3", "4", "t", "r"})

# Mudae uses bare ``sp`` for red on $oq grids (same as roll buttons).
OQ_RED_EMOJIS = frozenset({"sp", "spR"})
OQ_MINE_EMOJIS = frozenset({"spP", "sp", "spR"})

_EMOJI_TO_OQ: dict[str, str] = {
    "spP": "t",
    "spR": "r",
    "spB": "0",
    "spT": "1",
    "spG": "2",
    "spY": "3",
    "spO": "4",
}


class OqPhase(str, Enum):
    PLAYING = "playing"
    BONUS_LOCATE = "bonus_locate"
    BONUS_HARVEST = "bonus_harvest"
    REVEAL = "reveal"


def emoji_to_oq_state(emoji: str) -> str | None:
    key = (emoji or "").strip()
    if not key or key == "spU":
        return None
    if key == "sp":
        return "r"
    return _EMOJI_TO_OQ.get(key)


def states_from_observations(observations: dict[int, str]) -> list[str]:
    """Build a 25-cell state vector (``?`` = hidden)."""
    states = ["?"] * GRID_CELLS
    for index, color in observations.items():
        if 0 <= index < GRID_CELLS and color in OQ_COLORS | {"t", "r"}:
            states[index] = color
    return states


def get_game_state(states: list[str]) -> tuple[OqPhase, int, int]:
    """Return ``(phase, paid_clicks, targets_found)``."""
    clicks = 0
    targets = 0
    reds = 0
    for state in states:
        if state == "t":
            targets += 1
        elif state == "r":
            reds += 1
        elif state != "?":
            clicks += 1

    if targets < TARGET_PURPLES:
        phase = OqPhase.PLAYING
    elif clicks >= CLICK_BUDGET:
        phase = OqPhase.REVEAL
    elif reds == 0:
        phase = OqPhase.BONUS_LOCATE
    else:
        phase = OqPhase.BONUS_HARVEST
    return phase, clicks, targets


def filter_worlds(states: list[str]) -> frozenset[int]:
    ensure_built()
    valid = set(range(len(oq_worlds.ALL_WORLDS)))
    for cell, state in enumerate(states):
        if state == "?":
            continue
        outcome = -1 if state in {"t", "r"} else int(state)
        key = (cell, outcome + 1)
        matching = oq_worlds.CONSTRAINT.get(key)
        if not matching:
            return frozenset()
        valid &= set(matching)
    return frozenset(valid)


def locate_mine_candidates(states: list[str]) -> frozenset[int]:
    """Cells that could hold the 4th purple after 3 are found."""
    valid = filter_worlds(states)
    known_targets = {i for i, s in enumerate(states) if s == "t"}
    candidates: set[int] = set()
    for wi in valid:
        for mine in oq_worlds.ALL_WORLDS[wi]:
            if mine not in known_targets:
                candidates.add(mine)
                break
    return frozenset(candidates)


def _mine_indices(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
) -> set[int]:
    """Cells occupied by a purple or red sphere (for harvest adjacency)."""
    mines: set[int] = set()
    spheres = _sphere_buttons_only(buttons)
    for index, button in enumerate(spheres[:GRID_CELLS]):
        emoji = (button.get("emoji") or "").strip()
        if emoji in OQ_MINE_EMOJIS:
            mines.add(index)
    for index, state in observations.items():
        if state in {"t", "r"}:
            mines.add(index)
    return mines


def _red_on_grid(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
) -> bool:
    if any(state == "r" for state in observations.values()):
        return True
    return bool(_revealed_collectible_indices(buttons, emojis=OQ_RED_EMOJIS))


def harvest_ranking(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
) -> list[tuple[int, int, int]]:
    """Hidden cells ranked by adjacent mine count (adj, payout, cell)."""
    mines = _mine_indices(buttons, observations)
    ranking: list[tuple[int, int, int]] = []
    for cell in _hidden_clickable_indices(buttons):
        adj = min(sum(1 for n in oq_worlds.NEIGHBORS[cell] if n in mines), 4)
        ranking.append((adj, HARVEST_VALUE[adj], cell))
    ranking.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return ranking


def heuristic_analysis(
    valid_worlds: frozenset[int],
    states: list[str],
) -> tuple[int, str]:
    """Return ``(best_cell_index, reason)`` for the main playing phase."""
    total = len(valid_worlds)
    if total == 0:
        return -1, "no valid worlds"

    inv = 1.0 / total
    probs: dict[int, float] = {}
    entropies: dict[int, float] = {}

    for cell, state in enumerate(states):
        if state != "?":
            continue
        counts: dict[int, int] = {}
        mine_count = 0
        for wi in valid_worlds:
            outcome = oq_worlds.WORLD_OUTCOMES[wi][cell]
            counts[outcome] = counts.get(outcome, 0) + 1
            if outcome == -1:
                mine_count += 1
        probs[cell] = mine_count * inv
        entropy = 0.0
        for count in counts.values():
            p = count * inv
            if p > 0:
                entropy -= p * math.log2(p)
        entropies[cell] = entropy

    clicks = sum(1 for s in states if s not in {"?", "t"})
    clicks_remain = CLICK_BUDGET - clicks

    for cell, prob in probs.items():
        if prob >= 0.9999:
            return cell, "100% purple (free)"

    if clicks_remain <= 1:
        best = max(probs, key=lambda c: probs[c])
        return best, f"last click ({probs[best]:.0%} purple)"

    base_threshold = 0.06
    threshold = base_threshold + base_threshold * clicks_remain
    best_prob_cell = max(probs, key=lambda c: probs[c])
    if probs[best_prob_cell] > threshold:
        p = probs[best_prob_cell]
        return best_prob_cell, f"purple {p:.0%} > {threshold:.0%}"

    best_entropy_cell = max(entropies, key=lambda c: entropies[c])
    return (
        best_entropy_cell,
        f"entropy {entropies[best_entropy_cell]:.2f} (thresh {threshold:.0%})",
    )


def observations_from_buttons(buttons: list[dict[str, Any]]) -> dict[int, str]:
    obs: dict[int, str] = {}
    for index, button in enumerate(_sphere_buttons_only(buttons)):
        if index >= GRID_CELLS:
            break
        state = emoji_to_oq_state((button.get("emoji") or "").strip())
        if state:
            obs[index] = state
    return obs


def merge_observations(*sources: dict[int, str]) -> dict[int, str]:
    merged: dict[int, str] = {}
    for source in sources:
        for index, color in source.items():
            if color not in OQ_COLORS:
                continue
            previous = merged.get(index)
            if previous is not None and previous != color:
                raise ValueError(f"conflicting color at {index}: {previous} vs {color}")
            merged[index] = color
    return merged


def _sphere_buttons_only(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        button
        for button in buttons
        if (button.get("kind") == "sphere")
        or (button.get("emoji") or "").strip().startswith("sp")
    ]


def _button_at_index(buttons: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    spheres = _sphere_buttons_only(buttons)
    if 0 <= index < len(spheres):
        return spheres[index]
    return None


def _hidden_clickable_indices(buttons: list[dict[str, Any]]) -> list[int]:
    spheres = _sphere_buttons_only(buttons)
    return [
        index
        for index, button in enumerate(spheres[:GRID_CELLS])
        if _is_hidden_clickable(button)
    ]


def _is_clickable(button: dict[str, Any]) -> bool:
    return bool(button.get("custom_id")) and not button.get("disabled")


def _revealed_collectible_indices(
    buttons: list[dict[str, Any]],
    *,
    emojis: frozenset[str],
) -> list[int]:
    """Grid cells showing a revealed sphere emoji that still accepts a click."""
    spheres = _sphere_buttons_only(buttons)
    return [
        index
        for index, button in enumerate(spheres[:GRID_CELLS])
        if _is_clickable(button) and (button.get("emoji") or "").strip() in emojis
    ]


def _is_hidden_clickable(button: dict[str, Any]) -> bool:
    emoji = (button.get("emoji") or "").strip()
    return (
        bool(button.get("custom_id"))
        and not button.get("disabled")
        and emoji in {"", "spU"}
    )


def choose_oq_click(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
    *,
    clicks_spent: int = 0,
    clicks_budget: int = CLICK_BUDGET,
) -> dict[str, Any] | None:
    """Pick the next cell to click, or ``None`` when the session should stop."""
    free_purples = _revealed_collectible_indices(buttons, emojis=frozenset({"spP"}))
    if free_purples:
        return _button_at_index(buttons, min(free_purples))

    budget_left = clicks_spent < clicks_budget
    if not budget_left:
        return None

    revealed_reds = _revealed_collectible_indices(buttons, emojis=OQ_RED_EMOJIS)
    if revealed_reds:
        return _button_at_index(buttons, min(revealed_reds))

    hidden = _hidden_clickable_indices(buttons)
    if not hidden:
        return None

    states = states_from_observations(observations)
    phase, _, targets = get_game_state(states)

    if phase == OqPhase.REVEAL:
        return None

    if phase == OqPhase.PLAYING:
        hidden_unrevealed = [index for index in hidden if index not in observations]
        if not hidden_unrevealed:
            return None
        if all(s == "?" for s in states):
            if DEFAULT_OPENING_CELL in hidden_unrevealed:
                return _button_at_index(buttons, DEFAULT_OPENING_CELL)
        valid = filter_worlds(states)
        best_index, _reason = heuristic_analysis(valid, states)
        if best_index >= 0 and best_index in hidden_unrevealed:
            return _button_at_index(buttons, best_index)
        return _button_at_index(buttons, hidden_unrevealed[0])

    if targets >= TARGET_PURPLES and not _red_on_grid(buttons, observations):
        candidates = locate_mine_candidates(states)
        locate_hidden = [index for index in hidden if index in candidates]
        pick = min(locate_hidden) if locate_hidden else min(hidden)
        return _button_at_index(buttons, pick)

    # Red collected (or was already on grid) — harvest by adjacent mine count.
    ranking = harvest_ranking(buttons, observations)
    if ranking:
        return _button_at_index(buttons, ranking[0][2])
    return _button_at_index(buttons, hidden[0])


def is_paid_reveal(state: str) -> bool:
    return state not in {"?", "t"}


def format_solver_stats(observations: dict[int, str]) -> str:
    states = states_from_observations(observations)
    phase, clicks, targets = get_game_state(states)
    valid = filter_worlds(states)
    if phase == OqPhase.PLAYING:
        best_index, reason = heuristic_analysis(valid, states)
        if best_index >= 0:
            row, col = divmod(best_index, 5)
            return (
                f"solver: {len(valid)} worlds · {phase.value}"
                f" · {targets}/3 purple · {clicks}/{CLICK_BUDGET} paid"
                f" · next ({row + 1},{col + 1}) · {reason}"
            )
    if phase in {OqPhase.BONUS_LOCATE, OqPhase.BONUS_HARVEST}:
        return (
            f"solver: {len(valid)} worlds · {phase.value}"
            f" · {targets}/3 purple · {clicks}/{CLICK_BUDGET} paid"
        )
    return (
        f"solver: {len(valid)} worlds · {phase.value}"
        f" · {targets}/3 purple · {clicks}/{CLICK_BUDGET} paid"
    )


def cell_label(index: int | None) -> str:
    if index is None:
        return "?"
    row, col = divmod(index, 5)
    return f"({row + 1},{col + 1})"
