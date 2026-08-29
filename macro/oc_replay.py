"""Replay ``$oc`` sessions — against real logged boards, or synthetic ones.

Used to A/B the old fixed-priority collect order and 1-ply hunt against the
shallow lookahead in :mod:`macro.oc_solver` (``scripts/oc_bakeoff.py``).

**Prefer** :func:`load_logged_boards` / :func:`replay_logged_boards`: real
Mudae-generated boards are ground truth and share none of the solver's
assumptions. :func:`generate_synthetic_board` exists only for volume, and
its sampling is calibrated against those real boards (see below).

An earlier version of this generator was wrong in two ways that made every
number it produced untrustworthy — it never placed a green on an
orthogonal cell (real boards: 22% of them) and it mis-coloured the centre
blue, which made the solver's own constraints eliminate the true red on a
third of generated boards. Both are fixed here:

* greens are drawn from ``_row_col_neighbours`` *minus the oranges*, so
  they can land on orthogonal cells;
* yellows are drawn from the full diagonal line *including* the centre
  (``_diagonal_line_cells`` excludes it);
* teal is derived straight from the constraint ``_blue_forbidden`` rather
  than from ``row_col | diag``.

Measured against 100 fully-revealed logged boards, this reproduces the
real per-region colour mix to within ~2 points everywhere (ortho 63/24/13
vs 63/22/15, diagonal 64/36 vs 64/36, row-col-only 67/33 vs 68/32,
outside 97/2/1 vs 97/2/1) with zero constraint violations. It is still a
model, not Mudae's actual generator — treat its output as a relative
comparison, and confirm anything important on the logged boards.
"""

from __future__ import annotations

import random
from typing import Any

from macro.minigame_board import GRID_CELLS, build_session, make_click
from macro import oc_solver
from macro.oc_solver import CENTER_INDEX, choose_oc_click

_OC_STATE_TO_EMOJI = {
    "R": "spR",
    "O": "spO",
    "Y": "spY",
    "G": "spG",
    "T": "spT",
    "B": "spB",
}

DEFAULT_CLICKS_BUDGET = 5


def _btn(index: int, emoji: str = "spU", *, disabled: bool = False) -> dict[str, Any]:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def _diagonal_line_including_center(red_index: int) -> list[int]:
    """Every cell on ``red_index``'s diagonal — ``_diagonal_line_cells`` drops the centre."""
    return [
        cell
        for cell in range(GRID_CELLS)
        if cell != red_index and oc_solver._on_diagonal_line(red_index, cell)
    ]


def generate_synthetic_board(red_index: int, rng: random.Random) -> dict[int, str]:
    """A full 25-cell truth board, sampled to match the logged colour mix.

    See the module docstring for how this was calibrated and where it still
    differs from Mudae.
    """
    ortho = list(oc_solver._orthogonal_neighbours(red_index))
    rng.shuffle(ortho)
    oranges = set(ortho[: oc_solver._ORANGES_PER_RED])

    # Yellow sits anywhere on the diagonal, the centre included.
    diag_pool = [c for c in _diagonal_line_including_center(red_index) if c not in oranges]
    rng.shuffle(diag_pool)
    yellows = set(diag_pool[: oc_solver._YELLOWS_PER_RED])

    # Green shares red's row/column and may be orthogonally adjacent — on
    # real boards 22% of orthogonal cells are green.
    green_pool = [
        cell
        for cell in oc_solver._row_col_neighbours(red_index)
        if cell not in oranges and cell not in yellows
    ]
    rng.shuffle(green_pool)
    greens = set(green_pool[: oc_solver._GREENS_PER_RED])

    board: dict[int, str] = {red_index: "R"}
    for cell in range(GRID_CELLS):
        if cell == red_index:
            continue
        if cell in oranges:
            board[cell] = "O"
        elif cell in yellows:
            board[cell] = "Y"
        elif cell in greens:
            board[cell] = "G"
        elif oc_solver._blue_forbidden(red_index, cell):
            # Teal is exactly "shares a row, column or diagonal with red"
            # — the same predicate the constraint solver enforces.
            board[cell] = "T"
        else:
            board[cell] = "B"
    return board


def random_red_index(rng: random.Random) -> int:
    return rng.choice([index for index in range(GRID_CELLS) if index != CENTER_INDEX])


# --- Frozen "before" baseline, for the bakeoff only -------------------------
#
# Reproduces the fixed-priority collect order and 1-ply hunt that shipped
# before the leftover-click lookahead: always finish orange, then yellow,
# then green, and hunt purely by information gain regardless of clicks left.
# Kept only here (not in oc_solver.py) so production carries a single policy.


def _legacy_pick_collect_click(
    red_index: int,
    observations: dict[int, str],
    hidden: list[int],
) -> int | None:
    if red_index in hidden and observations.get(red_index) != "R":
        return red_index

    ortho = oc_solver._orthogonal_neighbours(red_index)
    if oc_solver._count_color_among(ortho, observations, "O") < oc_solver._ORANGES_PER_RED:
        targets = oc_solver._hidden_among(ortho, hidden, observations)
        if targets:
            return targets[0]

    diag = oc_solver._diagonal_line_cells(red_index)
    if oc_solver._count_color_among(diag, observations, "Y") < oc_solver._YELLOWS_PER_RED:
        targets = oc_solver._hidden_among(diag, hidden, observations)
        if targets:
            return targets[0]

    row_col = oc_solver._row_col_neighbours(red_index)
    if oc_solver._count_color_among(row_col, observations, "G") < oc_solver._GREENS_PER_RED:
        targets = oc_solver._hidden_among(row_col, hidden, observations)
        if targets:
            return targets[0]

    candidates = [index for index in hidden if index != CENTER_INDEX]
    if not candidates:
        return None
    return max(candidates, key=lambda index: oc_solver.expected_click_value(index, observations))


def _legacy_pick_hunt_click(observations: dict[int, str], hidden: list[int]) -> int:
    reds = oc_solver.constraint_red_candidates(observations)

    if oc_solver._opening_only(observations):
        pick = oc_solver._pick_post_opening_click(observations, hidden)
        if pick is not None:
            return pick

    if len(reds) <= 2:
        red_pick = oc_solver._pick_red_candidate(observations, hidden)
        if red_pick is not None:
            return red_pick

    orange_adjacent = oc_solver._orange_adjacent_red_candidates(observations, hidden)
    if orange_adjacent:
        return orange_adjacent[0]

    return oc_solver._pick_best_deduction_cell(observations, hidden)


def _legacy_choose_oc_click(
    buttons: list[dict[str, Any]],
    observations: dict[int, str],
    *,
    clicks_spent: int,
    clicks_budget: int,
) -> dict[str, Any] | None:
    if clicks_spent >= clicks_budget:
        return None
    hidden = [
        index
        for index in oc_solver._hidden_clickable_indices(buttons)
        if index not in observations
    ]
    if not hidden:
        return None

    red_known = oc_solver._known_red_index(observations)
    if red_known is not None:
        collect_index = _legacy_pick_collect_click(red_known, observations, hidden)
        if collect_index is not None:
            return oc_solver._button_at_index(buttons, collect_index)

    if not observations and oc_solver.OPENING_CELL_INDEX in hidden:
        return oc_solver._button_at_index(buttons, oc_solver.OPENING_CELL_INDEX)

    if red_known is None:
        hunt_index = _legacy_pick_hunt_click(observations, hidden)
        return oc_solver._button_at_index(buttons, hunt_index)

    best = oc_solver._pick_best_deduction_cell(observations, hidden)
    return oc_solver._button_at_index(buttons, best)


def _buttons_for(truth: dict[int, str], observations: dict[int, str], clicked: set[int]) -> list[dict[str, Any]]:
    buttons = [_btn(index) for index in range(GRID_CELLS)]
    for index, color in observations.items():
        buttons[index] = _btn(index, _OC_STATE_TO_EMOJI[color], disabled=index in clicked)
    del truth  # only observed cells are ever shown to the policy
    return buttons


def simulate_oc_board(
    truth: dict[int, str],
    *,
    budget: int = DEFAULT_CLICKS_BUDGET,
    rng: random.Random | None = None,
    policy: str = "lookahead",
) -> dict[str, Any]:
    """Play one synthetic board to completion. Returns a minigame session dict.

    ``policy`` is ``"lookahead"`` (current ``choose_oc_click``) or
    ``"legacy"`` (the frozen pre-lookahead baseline above), for the bakeoff.
    """
    chooser = rng or random.Random()
    observations: dict[int, str] = {}
    clicked: set[int] = set()
    clicks: list[dict[str, Any]] = []
    spent = 0
    for _ in range(budget):
        buttons = _buttons_for(truth, observations, clicked)
        if policy == "legacy":
            choice = _legacy_choose_oc_click(
                buttons, observations, clicks_spent=spent, clicks_budget=budget,
            )
        else:
            choice = choose_oc_click(
                buttons,
                observations,
                clicks_spent=spent,
                clicks_budget=budget,
                rng=chooser,
            )
        if choice is None:
            break
        index = int(choice["custom_id"].split("s")[1])
        color = truth[index]
        observations[index] = color
        clicked.add(index)
        clicks.append(make_click(index, _OC_STATE_TO_EMOJI[color], paid=True))
        spent += 1

    board = [
        _OC_STATE_TO_EMOJI[observations.get(index, truth[index])]
        for index in range(GRID_CELLS)
    ]
    return build_session(
        "oc",
        clicks,
        board,
        clicks_paid=spent,
        clicks_budget=budget,
        reason="done",
    )


# --- Real logged boards (ground truth) --------------------------------------

_EMOJI_TO_STATE = {
    "sp": "R",
    "spR": "R",
    "spO": "O",
    "spY": "Y",
    "spG": "G",
    "spT": "T",
    "spB": "B",
}


def load_logged_boards(path: str) -> list[dict[str, Any]]:
    """Fully-revealed ``$oc`` boards from a JSON or JSONL minigame log.

    Accepts either ``data/minigame_log.json`` (a JSON array) or a
    ``.jsonl`` export. Rows that are not ``$oc``, are not fully revealed
    (any ``spU`` left), or do not have exactly one red are skipped — a
    partially revealed board is not ground truth and would silently bias
    the comparison.

    Note the boards are valid regardless of *who* played the logged game:
    Mudae generates the layout, so a row played by hand elsewhere is still
    a legitimate board to replay.
    """
    import json

    raw = open(path, encoding="utf-8").read()
    stripped = raw.lstrip()
    if stripped.startswith("["):
        rows = json.loads(raw)
    else:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]

    boards: list[dict[str, Any]] = []
    for row in rows:
        if row.get("game") != "oc":
            continue
        board = row.get("board") or []
        if len(board) != GRID_CELLS or not all(c in _EMOJI_TO_STATE for c in board):
            continue
        truth = {i: _EMOJI_TO_STATE[c] for i, c in enumerate(board)}
        if sum(1 for v in truth.values() if v == "R") != 1:
            continue
        boards.append(
            {
                "truth": truth,
                "budget": int(row.get("clicks_budget") or DEFAULT_CLICKS_BUDGET),
                "logged_sp": int(row.get("base_value") or 0),
                "date_key": row.get("date_key"),
            }
        )
    return boards


def replay_logged_boards(path: str, *, policy: str = "lookahead") -> dict[str, Any]:
    """Replay every logged board from scratch under ``policy``."""
    boards = load_logged_boards(path)
    per_board: list[int] = []
    wins = 0
    for entry in boards:
        session = simulate_oc_board(
            entry["truth"], budget=entry["budget"], policy=policy,
        )
        per_board.append(int(session["base_value"]))
        if session["won"]:
            wins += 1
    n = len(boards) or 1
    return {
        "policy": policy,
        "boards": len(boards),
        "avg_sp": sum(per_board) / n,
        "win_rate": wins / n,
        "per_board": per_board,
    }


def paired_delta(new: list[int], base: list[int]) -> dict[str, Any]:
    """Paired per-board comparison with the statistics to judge it by.

    Reported because this is exactly where a smaller sample misled us: on
    30 boards one candidate change measured -8.83 SP, and on 100 boards
    the same change measured +1.35. ``significant`` is the only field that
    should drive a ship/no-ship decision, and ``boards_needed`` says how
    much more data an inconclusive result would take.
    """
    import statistics

    deltas = [a - b for a, b in zip(new, base)]
    n = len(deltas)
    mean = statistics.mean(deltas) if n else 0.0
    sd = statistics.stdev(deltas) if n > 1 else 0.0
    se = sd / (n ** 0.5) if n and sd else 0.0
    t = mean / se if se else 0.0
    needed = int((2 * sd / abs(mean)) ** 2) if mean and sd else 0
    return {
        "n": n,
        "mean": mean,
        "stdev": sd,
        "stderr": se,
        "t": t,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
        "changed": sum(1 for d in deltas if d),
        "significant": abs(t) >= 1.96,
        "boards_needed": needed,
    }


def score_oc_trials(
    *,
    trials: int = 500,
    budget: int = DEFAULT_CLICKS_BUDGET,
    seed: int = 0,
    policy: str = "lookahead",
) -> dict[str, Any]:
    """Replay ``trials`` random synthetic boards (same boards for any policy
    given the same ``seed``) and return average SP."""
    rng = random.Random(seed)
    total_sp = 0
    total_clicks = 0
    for _ in range(trials):
        red_index = random_red_index(rng)
        truth = generate_synthetic_board(red_index, rng)
        session = simulate_oc_board(truth, budget=budget, rng=rng, policy=policy)
        total_sp += int(session["base_value"])
        total_clicks += int(session["clicks_paid"])
    return {
        "policy": policy,
        "trials": trials,
        "budget": budget,
        "avg_sp": (total_sp / trials) if trials else 0.0,
        "avg_clicks": (total_clicks / trials) if trials else 0.0,
        "total_sp": total_sp,
    }
