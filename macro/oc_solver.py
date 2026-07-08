"""Constraint solver for the Mudae ``$oc`` sphere minigame.

Uses geometric compatibility rules (matching the public
`Mudae Helper $oc solver <https://mudaehelper.pages.dev/oc-solver>`_) rather
than enumerating full boards with incorrect colour partitions.

Strategy
--------
**Find red (clicks 1–3)**

1. Open at **(4, 2)**.
2. Second click depends on the opening colour:
   - **Blue** at (4, 2) → symmetric probe **(2, 4)** (narrows to corner reds).
   - **Orange** → adjacent red-candidate cell.
   - **Anything else** → cell with highest red-location information gain.
3. Once ≤2 red candidates remain, click a **red candidate** (prefer ``(1, 1)``).
4. When an **orange** is revealed later, click an adjacent red candidate.
5. Otherwise → max red information gain.

**Collect value (after red is known)**

1. Click red if not yet revealed.
2. Click hidden ortho neighbours only until **both oranges** adjacent to red are found.
3. Then click hidden **diagonal-line** cells for **yellow** (up to 3).
4. Then row/column cells for **green** (up to 4).
5. Otherwise pick the best remaining cell by expected value.
"""

from __future__ import annotations

import math
from typing import Any

from mudae.constants import SPHERE_VALUE_RANK

GRID_SIZE = 5
GRID_CELLS = GRID_SIZE * GRID_SIZE
CENTER_INDEX = 12

# (4, 2) and (2, 4) in 1-based coordinates — standard opening probes.
OPENING_CELL_INDEX = 16
_SECOND_PROBE_INDEX = 8

_ORANGES_PER_RED = 2
_YELLOWS_PER_RED = 3
_GREENS_PER_RED = 4

OC_COLORS = frozenset({"R", "O", "Y", "G", "T", "B"})

_OC_COLOR_VALUE: dict[str, int] = {
    "R": SPHERE_VALUE_RANK.get("spR", 8) * 20,
    "O": SPHERE_VALUE_RANK.get("spO", 7) * 13,
    "Y": SPHERE_VALUE_RANK.get("spY", 4) * 15,
    "G": SPHERE_VALUE_RANK.get("spG", 3) * 13,
    "T": SPHERE_VALUE_RANK.get("spT", 2) * 12,
    "B": SPHERE_VALUE_RANK.get("spB", 1) * 14,
}

_EMOJI_TO_OC: dict[str, str] = {
    "sp": "R",
    "spR": "R",
    "spO": "O",
    "spY": "Y",
    "spG": "G",
    "spT": "T",
    "spB": "B",
}


def _row_col(index: int) -> tuple[int, int]:
    return divmod(index, GRID_SIZE)


def _orthogonal_neighbours(index: int) -> frozenset[int]:
    row, col = _row_col(index)
    out: set[int] = set()
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE:
            out.add(nr * GRID_SIZE + nc)
    return frozenset(out)


def _diagonal_adjacent(index: int) -> frozenset[int]:
    row, col = _row_col(index)
    out: set[int] = set()
    for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE:
            out.add(nr * GRID_SIZE + nc)
    return frozenset(out)


def _on_diagonal_line(a: int, b: int) -> bool:
    ra, ca = _row_col(a)
    rb, cb = _row_col(b)
    return abs(ra - rb) == abs(ca - cb)


def _same_row(a: int, b: int) -> bool:
    return _row_col(a)[0] == _row_col(b)[0]


def _same_col(a: int, b: int) -> bool:
    return _row_col(a)[1] == _row_col(b)[1]


def _blue_forbidden(red_index: int, cell: int) -> bool:
    """Blue/teal never share a row, column, or diagonal line with red."""
    if cell == red_index:
        return True
    return (
        _same_row(red_index, cell)
        or _same_col(red_index, cell)
        or _on_diagonal_line(red_index, cell)
    )


def _red_compatible(red_index: int, observations: dict[int, str]) -> bool:
    if red_index == CENTER_INDEX:
        return False
    for cell, color in observations.items():
        if color == "R" and cell != red_index:
            return False
        if color == "O" and red_index not in _orthogonal_neighbours(cell):
            return False
        if color == "Y" and not _on_diagonal_line(red_index, cell):
            return False
        if color == "G" and not (_same_row(red_index, cell) or _same_col(red_index, cell)):
            return False
        if color == "B" and _blue_forbidden(red_index, cell):
            return False
        if color == "T" and not _blue_forbidden(red_index, cell):
            return False
    return True


def constraint_red_candidates(observations: dict[int, str]) -> list[int]:
    """Red positions consistent with ``observations`` (newest rules)."""
    return [
        red_index
        for red_index in range(GRID_CELLS)
        if red_index != CENTER_INDEX and _red_compatible(red_index, observations)
    ]


def filter_boards(observations: dict[int, str]) -> list[dict[int, str]]:
    """Legacy hook — one synthetic board per viable red location."""
    reds = constraint_red_candidates(observations)
    return [{red_index: "R"} for red_index in reds]


def emoji_to_oc_color(emoji: str) -> str | None:
    key = (emoji or "").strip()
    if not key or key == "spU":
        return None
    return _EMOJI_TO_OC.get(key)


def observations_from_buttons(buttons: list[dict[str, Any]]) -> dict[int, str]:
    obs: dict[int, str] = {}
    for index, button in enumerate(_sphere_buttons_only(buttons)):
        if index >= GRID_CELLS:
            break
        color = emoji_to_oc_color((button.get("emoji") or "").strip())
        if color:
            obs[index] = color
    return obs


def merge_observations(*sources: dict[int, str]) -> dict[int, str]:
    merged: dict[int, str] = {}
    for source in sources:
        for index, color in source.items():
            if color not in OC_COLORS:
                continue
            previous = merged.get(index)
            if previous is not None and previous != color:
                raise ValueError(f"conflicting color at {index}: {previous} vs {color}")
            merged[index] = color
    return merged


def probability_red_at(observations: dict[int, str]) -> list[float]:
    reds = constraint_red_candidates(observations)
    if not reds:
        return [0.0] * GRID_CELLS
    p = 1.0 / len(reds)
    probs = [0.0] * GRID_CELLS
    for red_index in reds:
        probs[red_index] = p
    return probs


def expected_click_value(index: int, observations: dict[int, str]) -> float:
    reds = constraint_red_candidates(observations)
    if not reds:
        return 0.0
    total = 0.0
    for red_index in reds:
        if index == red_index:
            total += _OC_COLOR_VALUE["R"]
        elif index in _orthogonal_neighbours(red_index):
            total += _OC_COLOR_VALUE["O"] * 0.5
        elif _on_diagonal_line(red_index, index) and index != CENTER_INDEX:
            total += _OC_COLOR_VALUE["Y"] * 0.4
        elif _same_row(red_index, index) or _same_col(red_index, index):
            total += _OC_COLOR_VALUE["G"] * 0.35
        elif _blue_forbidden(red_index, index):
            total += _OC_COLOR_VALUE["T"] * 0.25
        else:
            total += _OC_COLOR_VALUE["B"]
    return total / len(reds)


def _red_location_entropy_from_reds(reds: list[int]) -> float:
    if not reds:
        return 0.0
    p = 1.0 / len(reds)
    return -len(reds) * p * math.log(p)


def red_information_gain(index: int, observations: dict[int, str]) -> float:
    """Expected reduction in red-location entropy from revealing ``index``."""
    reds = constraint_red_candidates(observations)
    if not reds or index == CENTER_INDEX:
        return 0.0

    buckets: dict[str, list[int]] = {}
    for red_index in reds:
        if index == red_index:
            color = "R"
        elif index in _orthogonal_neighbours(red_index):
            color = "O?"
        elif _on_diagonal_line(red_index, index):
            color = "Y?"
        elif _same_row(red_index, index) or _same_col(red_index, index):
            color = "G?"
        elif _blue_forbidden(red_index, index):
            color = "T?"
        else:
            color = "B"
        buckets.setdefault(color, []).append(red_index)

    before = _red_location_entropy_from_reds(reds)
    total = len(reds)
    after = sum(
        (len(subset) / total) * _red_location_entropy_from_reds(subset)
        for subset in buckets.values()
    )
    return before - after


def probability_red_at_cell(index: int, observations: dict[int, str]) -> float:
    reds = constraint_red_candidates(observations)
    if not reds:
        return 0.0
    if index in reds:
        return 1.0 / len(reds)
    return 0.0


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


def _is_hidden_clickable(button: dict[str, Any]) -> bool:
    emoji = (button.get("emoji") or "").strip()
    return (
        bool(button.get("custom_id"))
        and not button.get("disabled")
        and emoji in {"", "spU"}
    )


def _hidden_clickable_indices(buttons: list[dict[str, Any]]) -> list[int]:
    spheres = _sphere_buttons_only(buttons)
    return [
        index
        for index, button in enumerate(spheres[:GRID_CELLS])
        if _is_hidden_clickable(button)
    ]


def _known_red_index(observations: dict[int, str]) -> int | None:
    for index, color in observations.items():
        if color == "R":
            return index
    reds = constraint_red_candidates(observations)
    if len(reds) == 1:
        return reds[0]
    return None


def _orange_adjacent_red_candidates(
    observations: dict[int, str],
    hidden: list[int],
) -> list[int]:
    reds = set(constraint_red_candidates(observations))
    targets: set[int] = set()
    for index, color in observations.items():
        if color != "O":
            continue
        for neighbour in _orthogonal_neighbours(index):
            if neighbour in reds and neighbour in hidden:
                targets.add(neighbour)
    return sorted(targets)


def _diagonal_line_cells(red_index: int) -> frozenset[int]:
    out: set[int] = set()
    for index in range(GRID_CELLS):
        if index in {red_index, CENTER_INDEX}:
            continue
        if _on_diagonal_line(red_index, index):
            out.add(index)
    return frozenset(out)


def _count_color_among(indices: frozenset[int], observations: dict[int, str], color: str) -> int:
    return sum(1 for index in indices if observations.get(index) == color)


def _hidden_among(indices: frozenset[int], hidden: list[int], observations: dict[int, str]) -> list[int]:
    hidden_set = set(hidden)
    return sorted(
        index
        for index in indices
        if index in hidden_set and index not in observations
    )


def _pick_collect_click(
    red_index: int,
    observations: dict[int, str],
    hidden: list[int],
) -> int | None:
    """Next high-value cell once red's location is known."""
    if red_index in hidden and observations.get(red_index) != "R":
        return red_index

    ortho = _orthogonal_neighbours(red_index)
    if _count_color_among(ortho, observations, "O") < _ORANGES_PER_RED:
        orange_targets = _hidden_among(ortho, hidden, observations)
        if orange_targets:
            return orange_targets[0]

    diag_line = _diagonal_line_cells(red_index)
    if _count_color_among(diag_line, observations, "Y") < _YELLOWS_PER_RED:
        yellow_targets = _hidden_among(diag_line, hidden, observations)
        if yellow_targets:
            return yellow_targets[0]

    row_col = _row_col_neighbours(red_index)
    if _count_color_among(row_col, observations, "G") < _GREENS_PER_RED:
        green_targets = _hidden_among(row_col, hidden, observations)
        if green_targets:
            return green_targets[0]

    candidates = [index for index in hidden if index != CENTER_INDEX]
    if not candidates:
        return None
    return max(candidates, key=lambda index: expected_click_value(index, observations))


def _collect_phase_targets(
    red_index: int,
    hidden: list[int],
    observations: dict[int, str],
) -> list[int]:
    """Ordered collect targets (legacy helper for stats display)."""
    pick = _pick_collect_click(red_index, observations, hidden)
    return [pick] if pick is not None else []


def _row_col_neighbours(index: int) -> frozenset[int]:
    row, col = _row_col(index)
    out: set[int] = set()
    for cc in range(GRID_SIZE):
        if cc != col:
            out.add(row * GRID_SIZE + cc)
    for rr in range(GRID_SIZE):
        if rr != row:
            out.add(rr * GRID_SIZE + col)
    return frozenset(out)


def _pick_red_candidate(
    observations: dict[int, str],
    hidden: list[int],
) -> int | None:
    reds = [index for index in constraint_red_candidates(observations) if index in hidden]
    if not reds:
        return None
    # Prefer (1, 1) over (5, 5) when both remain — matches public solver behaviour.
    reds.sort(key=lambda index: (probability_red_at_cell(index, observations), -index), reverse=True)
    return reds[0]


def _pick_best_deduction_cell(
    observations: dict[int, str],
    hidden: list[int],
) -> int:
    candidates = [index for index in hidden if index != CENTER_INDEX]
    if not candidates:
        return hidden[0]

    def sort_key(index: int) -> tuple[float, float, float, int]:
        return (
            red_information_gain(index, observations),
            expected_click_value(index, observations),
            probability_red_at_cell(index, observations),
            -index,
        )

    return max(candidates, key=sort_key)


def _opening_only(observations: dict[int, str]) -> bool:
    return len(observations) == 1 and OPENING_CELL_INDEX in observations


def _pick_post_opening_click(
    observations: dict[int, str],
    hidden: list[int],
) -> int | None:
    """Second click after ``(4, 2)`` — colour-dependent."""
    opening_color = observations[OPENING_CELL_INDEX]

    if opening_color == "R":
        return OPENING_CELL_INDEX if OPENING_CELL_INDEX in hidden else None

    if opening_color == "O":
        adjacent = _orange_adjacent_red_candidates(observations, hidden)
        if adjacent:
            return adjacent[0]
        return _pick_best_deduction_cell(observations, hidden)

    if opening_color == "B" and _SECOND_PROBE_INDEX in hidden:
        return _SECOND_PROBE_INDEX

    return _pick_best_deduction_cell(observations, hidden)


def _pick_hunt_click(
    observations: dict[int, str],
    hidden: list[int],
) -> int:
    reds = constraint_red_candidates(observations)

    if _opening_only(observations):
        pick = _pick_post_opening_click(observations, hidden)
        if pick is not None:
            return pick

    if len(reds) <= 2:
        red_pick = _pick_red_candidate(observations, hidden)
        if red_pick is not None:
            return red_pick

    orange_adjacent = _orange_adjacent_red_candidates(observations, hidden)
    if orange_adjacent:
        return orange_adjacent[0]

    return _pick_best_deduction_cell(observations, hidden)


def choose_oc_click(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
    *,
    clicks_spent: int = 0,
    clicks_budget: int = 5,
    rng: Any | None = None,
) -> dict[str, Any] | None:
    """Pick the next hidden cell to click, or ``None`` when budget is spent."""
    import random

    chooser = rng or random
    if clicks_spent >= clicks_budget:
        return None

    hidden = [
        index
        for index in _hidden_clickable_indices(buttons)
        if index not in observations
    ]
    if not hidden:
        return None

    red_known = _known_red_index(observations)

    # --- Collect phase: red location pinned --------------------------------
    if red_known is not None:
        collect_index = _pick_collect_click(red_known, observations, hidden)
        if collect_index is not None:
            return _button_at_index(buttons, collect_index)

    # --- Opening -----------------------------------------------------------
    if not observations and OPENING_CELL_INDEX in hidden:
        return _button_at_index(buttons, OPENING_CELL_INDEX)

    # --- Red hunt ----------------------------------------------------------
    if red_known is None:
        hunt_index = _pick_hunt_click(observations, hidden)
        return _button_at_index(buttons, hunt_index)

    best = _pick_best_deduction_cell(observations, hidden)
    return _button_at_index(buttons, best)


def solver_stats(observations: dict[int, str]) -> dict[str, Any]:
    reds = constraint_red_candidates(observations)
    hidden = [
        index
        for index in range(GRID_CELLS)
        if index != CENTER_INDEX and index not in observations
    ]
    red_known = _known_red_index(observations)

    best_index = -1
    best_rig = 0.0
    best_ev = 0.0
    best_p_red = 0.0

    if hidden:
        if not observations:
            best_index = OPENING_CELL_INDEX
        elif red_known is not None:
            best_index = _pick_collect_click(red_known, observations, hidden) or -1
        else:
            best_index = _pick_hunt_click(observations, hidden)

        if best_index >= 0:
            best_rig = red_information_gain(best_index, observations)
            best_ev = expected_click_value(best_index, observations)
            best_p_red = probability_red_at_cell(best_index, observations)

    return {
        "boards": len(reds),
        "candidates_left": len(reds),
        "best_index": best_index,
        "best_rig": best_rig,
        "best_ev": best_ev,
        "best_p_red": best_p_red,
    }


def format_solver_stats(observations: dict[int, str]) -> str:
    stats = solver_stats(observations)
    if not stats["boards"] and observations:
        return "solver: no valid red location matches observations"
    best_index = stats["best_index"]
    if best_index < 0:
        return f"solver: {stats['boards']} red candidates"
    row, col = _row_col(best_index)
    p_red_note = (
        f" pR={stats['best_p_red']:.0%}"
        if stats["best_p_red"] > 0
        else ""
    )
    phase = "collect" if _known_red_index(observations) is not None else "hunt"
    return (
        f"solver: {stats['boards']} red candidates · {phase}"
        f" · next ({row + 1},{col + 1})"
        f"{p_red_note} rig={stats['best_rig']:.2f} ev={stats['best_ev']:.1f}"
    )


# Legacy exports used by tests
def placements_for_red(red_index: int) -> list[dict[int, str]]:
    if _red_compatible(red_index, {}):
        return [{red_index: "R"}]
    return []


def all_boards() -> list[dict[int, str]]:
    return [{red: "R"} for red in constraint_red_candidates({})]
