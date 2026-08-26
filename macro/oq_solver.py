"""Solver for the Mudae ``$oq`` (Orb Quest) sphere minigame.

World filter is the 12,650 purple placements in ``oq_worlds``. Hunt uses the
Colblitz MIXED scorer (``P(purple) + 0.1×Gini``). Opening is Colblitz overlay
cell ``(1,1)`` (0-based) = index 6. Last paid click is max ``P(purple)``.
Finding 3 purples auto-reveals the 4th as red (or rainbow) on the grid — we
claim that visible sphere, we do not search for it. Leftover clicks harvest.
When 2 purples are already found, hunt expectimax treats the third as a free
click that unlocks the auto-red. Entropy hunt is ``hunt_policy="entropy"``.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

import macro.oq_worlds as oq_worlds
from macro.oq_worlds import GRID_CELLS, ensure_built
from mudae.constants import SPHERE_BASE_SP, canonical_sphere_emoji

# Colblitz overlay ``(1,1)`` is 0-based (inner 3×3). Same cell MIXED picks
# on an empty board (highest Gini, lowest index).
DEFAULT_OPENING_CELL = 6

CLICK_BUDGET = 7
TARGET_PURPLES = 3

# Orb payout during bonus harvest by adjacent-purple count (Blue..Orange).
HARVEST_VALUE = (
    SPHERE_BASE_SP["spB"],
    SPHERE_BASE_SP["spT"],
    SPHERE_BASE_SP["spG"],
    SPHERE_BASE_SP["spY"],
    SPHERE_BASE_SP["spO"],
)

# Colblitz MIXED: P(purple) plus a small Gini tie-breaker.
MIXED_ALPHA = 1.0
MIXED_BETA = 0.1
HUNT_POLICY_MIXED = "mixed"
HUNT_POLICY_ENTROPY = "entropy"

# Depth-limited expectimax once two purples are found. The third is free and
# unlocks the auto-revealed red; 0–1 purple hunt stays MIXED so colour EV
# does not steal paid clicks from information.
EXPECTIMAX_DEPTH = 2
EXPECTIMAX_TOP_K = 6

OQ_COLORS = frozenset({"0", "1", "2", "3", "4", "t", "r"})

# Mudae uses bare ``sp`` for red on $oq grids (same as roll buttons).
# The 4th purple may become red or rainbow (``spW``); both are treated alike.
OQ_RED_EMOJIS = frozenset({"sp", "spR", "spW"})
OQ_MINE_EMOJIS = frozenset({"spP", "sp", "spR", "spW"})

_EMOJI_TO_OQ: dict[str, str] = {
    "spP": "t",
    "spR": "r",
    "spW": "r",
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
    key = canonical_sphere_emoji(emoji)
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
    return locate_mine_candidates_from(filter_worlds(states), states)


def locate_mine_candidates_from(
    valid_worlds: frozenset[int],
    states: list[str],
) -> frozenset[int]:
    known_targets = {i for i, s in enumerate(states) if s == "t"}
    candidates: set[int] = set()
    for wi in valid_worlds:
        for mine in oq_worlds.ALL_WORLDS[wi]:
            if mine not in known_targets:
                candidates.add(mine)
                break
    return frozenset(candidates)


def _paid_clicks_from_states(states: list[str]) -> int:
    """Colour and red cells cost a click; purple is free."""
    return sum(1 for state in states if state not in {"?", "t"})


def _hidden_cells(
    states: list[str],
    allowed: frozenset[int] | None = None,
) -> list[int]:
    return [
        index
        for index, state in enumerate(states)
        if state == "?" and (allowed is None or index in allowed)
    ]


def _purple_sp(purples_found: int) -> int:
    if purples_found >= TARGET_PURPLES:
        return SPHERE_BASE_SP["spR"]
    return SPHERE_BASE_SP["spP"]


def _with_cell(states: list[str], cell: int, token: str) -> list[str]:
    out = list(states)
    out[cell] = token
    return out


def _analyze_cells(
    valid_worlds: frozenset[int],
    cells: list[int],
) -> dict[int, dict[str, Any]]:
    """Per-cell P(purple), Gini, MIXED score, and world partitions."""
    total = len(valid_worlds)
    if total == 0 or not cells:
        return {}
    inv = 1.0 / total
    result: dict[int, dict[str, Any]] = {}
    for cell in cells:
        buckets: dict[int, list[int]] = {}
        for wi in valid_worlds:
            outcome = oq_worlds.WORLD_OUTCOMES[wi][cell]
            bucket = buckets.get(outcome)
            if bucket is None:
                buckets[outcome] = [wi]
            else:
                bucket.append(wi)
        mine_count = len(buckets.get(-1, ()))
        p_purple = mine_count * inv
        entropy = 0.0
        gini_sum = 0.0
        for bucket in buckets.values():
            p = len(bucket) * inv
            if p > 0:
                entropy -= p * math.log2(p)
                gini_sum += p * p
        gini = 1.0 - gini_sum
        result[cell] = {
            "p_purple": p_purple,
            "gini": gini,
            "entropy": entropy,
            "mixed": MIXED_ALPHA * p_purple + MIXED_BETA * gini,
            "buckets": buckets,
        }
    return result


def _immediate_ev(row: dict[str, Any], purples_found: int) -> float:
    total = 0
    for bucket in row["buckets"].values():
        total += len(bucket)
    if total == 0:
        return 0.0
    inv = 1.0 / total
    ev = 0.0
    for outcome, bucket in row["buckets"].items():
        p = len(bucket) * inv
        if outcome == -1:
            ev += p * _purple_sp(purples_found)
        else:
            ev += p * HARVEST_VALUE[min(int(outcome), 4)]
    return ev


def _greedy_harvest_sp(states: list[str], clicks_remain: int) -> float:
    if clicks_remain <= 0:
        return 0.0
    mines = {index for index, state in enumerate(states) if state in {"t", "r"}}
    payouts = [
        HARVEST_VALUE[
            min(sum(1 for n in oq_worlds.NEIGHBORS[cell] if n in mines), 4)
        ]
        for cell, state in enumerate(states)
        if state == "?"
    ]
    payouts.sort(reverse=True)
    return float(sum(payouts[:clicks_remain]))


def _leaf_ev(
    valid_worlds: frozenset[int],
    states: list[str],
    clicks_remain: int,
    purples_found: int,
    allowed: frozenset[int] | None,
) -> float:
    if clicks_remain <= 0:
        return 0.0
    if any(state == "r" for state in states):
        return _greedy_harvest_sp(states, clicks_remain)
    hidden = _hidden_cells(states, allowed)
    info = _analyze_cells(valid_worlds, hidden)
    if not info:
        return 0.0
    if clicks_remain <= 1:
        cell = max(info, key=lambda c: (info[c]["p_purple"], -c))
    else:
        cell = max(info, key=lambda c: (info[c]["mixed"], -c))
    return _immediate_ev(info[cell], purples_found)


def _expectimax(
    valid_worlds: frozenset[int],
    states: list[str],
    clicks_remain: int,
    purples_found: int,
    depth: int,
    allowed: frozenset[int] | None,
) -> tuple[float, int]:
    """Return ``(expected_sp, best_cell)`` for the two-purple hunt."""
    hidden = _hidden_cells(states, allowed)
    if clicks_remain <= 0 or not hidden or not valid_worlds:
        return 0.0, -1
    if any(state == "r" for state in states):
        return _greedy_harvest_sp(states, clicks_remain), -1

    info = _analyze_cells(valid_worlds, hidden)
    if not info:
        return 0.0, -1

    for cell, row in info.items():
        if row["p_purple"] < 0.9999:
            continue
        sp = _purple_sp(purples_found)
        paid = 0 if purples_found < TARGET_PURPLES else 1
        child_states = _with_cell(
            states, cell, "t" if purples_found < TARGET_PURPLES else "r"
        )
        nk = clicks_remain - paid
        npur = min(purples_found + 1, TARGET_PURPLES)
        child_valid = frozenset(row["buckets"].get(-1, ()))
        extra = _expectimax_child_value(
            child_valid, child_states, nk, npur, depth - 1, token="t" if paid == 0 else "r",
        )
        return sp + extra, cell

    if clicks_remain <= 1 or depth <= 0:
        if clicks_remain <= 1:
            cell = max(info, key=lambda c: (info[c]["p_purple"], -c))
        else:
            cell = max(info, key=lambda c: (info[c]["mixed"], -c))
        return _immediate_ev(info[cell], purples_found), cell

    ranked = sorted(info, key=lambda c: (-info[c]["mixed"], c))
    best_cell = ranked[0]
    best_val = -1.0
    n_worlds = len(valid_worlds)
    for cell in ranked[:EXPECTIMAX_TOP_K]:
        row = info[cell]
        total = 0.0
        for outcome, worlds in row["buckets"].items():
            p = len(worlds) / n_worlds
            if p <= 0:
                continue
            child_valid = frozenset(worlds)
            if outcome == -1:
                sp = _purple_sp(purples_found)
                paid = 0 if purples_found < TARGET_PURPLES else 1
                nk = clicks_remain - paid
                npur = min(purples_found + 1, TARGET_PURPLES)
                token = "t" if paid == 0 else "r"
            else:
                sp = HARVEST_VALUE[min(int(outcome), 4)]
                nk = clicks_remain - 1
                npur = purples_found
                token = str(outcome)
            child_states = _with_cell(states, cell, token)
            extra = _expectimax_child_value(
                child_valid, child_states, nk, npur, depth - 1, token=token,
            )
            total += p * (sp + extra)
        if total > best_val:
            best_val = total
            best_cell = cell
    return best_val, best_cell


def _expectimax_child_value(
    child_valid: frozenset[int],
    child_states: list[str],
    clicks_remain: int,
    purples_found: int,
    depth: int,
    *,
    token: str,
) -> float:
    if clicks_remain <= 0:
        return 0.0
    if token == "r":
        return _greedy_harvest_sp(child_states, clicks_remain)
    if purples_found >= TARGET_PURPLES:
        # 3rd purple is in; Mudae auto-reveals the 4th as red. Claim it, then
        # harvest with that mine on the board.
        return _auto_red_then_harvest(child_valid, child_states, clicks_remain)
    if depth <= 0:
        return _leaf_ev(
            child_valid, child_states, clicks_remain, purples_found, None,
        )
    sub, _ = _expectimax(
        child_valid, child_states, clicks_remain, purples_found, depth, None,
    )
    return sub


def _auto_red_then_harvest(
    valid_worlds: frozenset[int],
    states: list[str],
    clicks_remain: int,
) -> float:
    if clicks_remain <= 0:
        return 0.0
    red_sp = float(SPHERE_BASE_SP["spR"])
    known = {index for index, state in enumerate(states) if state == "t"}
    total = 0.0
    n = 0
    for world_index in valid_worlds:
        fourth = next(
            (mine for mine in oq_worlds.ALL_WORLDS[world_index] if mine not in known),
            None,
        )
        if fourth is None:
            total += red_sp
        else:
            stated = _with_cell(states, fourth, "r")
            total += red_sp + _greedy_harvest_sp(stated, clicks_remain - 1)
        n += 1
    if n == 0:
        return red_sp + _greedy_harvest_sp(states, clicks_remain - 1)
    return total / n


def _mine_indices(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
) -> set[int]:
    """Cells occupied by a purple or red sphere (for harvest adjacency)."""
    mines: set[int] = set()
    spheres = _sphere_buttons_only(buttons)
    for index, button in enumerate(spheres[:GRID_CELLS]):
        emoji = _grid_emoji(button)
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
    *,
    hunt_policy: str = HUNT_POLICY_MIXED,
    clicks_remain: int | None = None,
    allowed: frozenset[int] | None = None,
) -> tuple[int, str]:
    """Return ``(best_cell_index, reason)`` for MIXED / entropy / last-click.

    ``clicks_remain`` is paid clicks left. If omitted it is inferred from
    colour/red cells on ``states`` (never from masked boards).
    """
    if not valid_worlds:
        return -1, "no valid worlds"
    hidden = _hidden_cells(states, allowed)
    info = _analyze_cells(valid_worlds, hidden)
    if not info:
        return -1, "no hidden cells"

    remain = clicks_remain
    if remain is None:
        remain = CLICK_BUDGET - _paid_clicks_from_states(states)

    for cell, row in info.items():
        if row["p_purple"] >= 0.9999:
            return cell, "100% purple (free)"

    if remain <= 1:
        best = max(info, key=lambda c: (info[c]["p_purple"], -c))
        return best, f"last click ({info[best]['p_purple']:.0%} purple)"

    if hunt_policy == HUNT_POLICY_ENTROPY:
        threshold = 0.06 + 0.06 * remain
        best_prob_cell = max(info, key=lambda c: (info[c]["p_purple"], -c))
        if info[best_prob_cell]["p_purple"] > threshold:
            p = info[best_prob_cell]["p_purple"]
            return best_prob_cell, f"purple {p:.0%} > {threshold:.0%}"
        best_entropy_cell = max(info, key=lambda c: (info[c]["entropy"], -c))
        return (
            best_entropy_cell,
            f"entropy {info[best_entropy_cell]['entropy']:.2f} (thresh {threshold:.0%})",
        )

    best_cell = max(info, key=lambda c: (info[c]["mixed"], -c))
    row = info[best_cell]
    return (
        best_cell,
        f"mixed {row['mixed']:.3f} (P={row['p_purple']:.0%} G={row['gini']:.2f})",
    )


def recommend_oq_cell(
    valid_worlds: frozenset[int],
    states: list[str],
    *,
    clicks_remain: int,
    hunt_policy: str = HUNT_POLICY_MIXED,
    allowed: frozenset[int] | None = None,
) -> tuple[int, str]:
    """Hunt pick: last-click, MIXED, entropy, or two-purple expectimax."""
    hidden = _hidden_cells(states, allowed)
    if not hidden or not valid_worlds:
        return -1, "no hidden cells"

    cell, reason = heuristic_analysis(
        valid_worlds,
        states,
        hunt_policy=hunt_policy,
        clicks_remain=clicks_remain,
        allowed=allowed,
    )
    if hunt_policy != HUNT_POLICY_MIXED:
        return cell, reason
    if clicks_remain <= 1:
        return cell, reason
    if reason.startswith("100%"):
        return cell, reason

    purples_found = min(sum(1 for state in states if state == "t"), TARGET_PURPLES)
    # Only once two purples are down: the next purple is free and unlocks
    # the auto-revealed red. Earlier hunt stays MIXED so we do not spend
    # paid clicks on colour EV instead of information.
    if purples_found != 2:
        return cell, reason

    depth = EXPECTIMAX_DEPTH
    hidden_n = len(hidden)
    if hidden_n <= 8 and clicks_remain <= 3:
        depth = 3
    _ev, best = _expectimax(
        valid_worlds, states, clicks_remain, purples_found, depth, allowed,
    )
    if best < 0:
        return cell, reason
    return best, f"expectimax d{depth} EV={_ev:.0f} · {reason}"


def _grid_emoji(button: dict[str, Any]) -> str:
    return canonical_sphere_emoji(button.get("emoji"))


def observations_from_buttons(buttons: list[dict[str, Any]]) -> dict[int, str]:
    obs: dict[int, str] = {}
    for index, button in enumerate(_sphere_buttons_only(buttons)):
        if index >= GRID_CELLS:
            break
        state = emoji_to_oq_state(_grid_emoji(button))
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
        if _is_clickable(button) and _grid_emoji(button) in emojis
    ]


def _is_hidden_clickable(button: dict[str, Any]) -> bool:
    emoji = _grid_emoji(button)
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
    hunt_policy: str = HUNT_POLICY_MIXED,
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
        remain = clicks_budget - clicks_spent
        best_index, _reason = recommend_oq_cell(
            valid,
            states,
            clicks_remain=remain,
            hunt_policy=hunt_policy,
        )
        if best_index >= 0 and best_index in hidden_unrevealed:
            return _button_at_index(buttons, best_index)
        return _button_at_index(buttons, hidden_unrevealed[0])

    if targets >= TARGET_PURPLES and not _red_on_grid(buttons, observations):
        # The 4th purple becomes a visible red/rainbow on the grid. Do not
        # probe hidden cells looking for it — the live loop waits for the edit.
        return None

    # Red collected (or was already on grid) — harvest by adjacent mine count.
    ranking = harvest_ranking(buttons, observations)
    if ranking:
        return _button_at_index(buttons, ranking[0][2])
    return _button_at_index(buttons, hidden[0])


def is_paid_reveal(state: str) -> bool:
    return state not in {"?", "t"}


def format_solver_stats(
    observations: dict[int, str],
    *,
    hunt_policy: str = HUNT_POLICY_MIXED,
    clicks_spent: int | None = None,
) -> str:
    states = states_from_observations(observations)
    phase, clicks, targets = get_game_state(states)
    valid = filter_worlds(states)
    remain = (
        CLICK_BUDGET - clicks_spent
        if clicks_spent is not None
        else CLICK_BUDGET - _paid_clicks_from_states(states)
    )
    if phase == OqPhase.PLAYING:
        best_index, reason = recommend_oq_cell(
            valid, states, clicks_remain=remain, hunt_policy=hunt_policy,
        )
        if best_index >= 0:
            row, col = divmod(best_index, 5)
            return (
                f"solver: {len(valid)} worlds · {phase.value}"
                f" · {targets}/3 purple · {clicks}/{CLICK_BUDGET} paid"
                f" · next ({row + 1},{col + 1}) · {reason}"
            )
    if phase == OqPhase.BONUS_LOCATE:
        return (
            f"solver: {len(valid)} worlds · {phase.value}"
            f" · {targets}/3 purple · {clicks}/{CLICK_BUDGET} paid"
            f" · waiting for auto-revealed red"
        )
    if phase == OqPhase.BONUS_HARVEST:
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
