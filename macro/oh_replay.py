"""Replay ``$oh`` sessions — against real logged boards, or synthetic ones.

``$oh`` had no simulator at all until this module, so no change to
:func:`macro.sphere_game.choose_oh_click` could be scored. This is that
missing measurement, built the same way as :mod:`macro.oc_replay`: fake the
Discord button dicts and drive the **real** decision function through them,
so the harness tests shipped code rather than a copy of it.

**Prefer** :func:`replay_logged_boards` — real Mudae boards are ground
truth. :func:`generate_board` exists for volume and is calibrated against
those boards.

Two things make ``$oh`` different from ``$oc`` / ``$oq``:

* **The replay is stochastic.** Blue unveils 3 covered cells and teal
  unveils 1, and the targets are uniformly random — so replaying the same
  board twice gives different scores. Every scoring entry point averages a
  fixed set of seeds and reports how many.
* **An ``$oc`` spawn is invisible.** It renders as ``spU`` whether or not it
  has been unveiled, so it never leaves the face-down pool and can never be
  targeted deliberately. See :data:`OC_GRANT_VALUE`.

Mechanics here are measured, not assumed. The logged ``$oh`` rows carry a
per-click ``unveiled`` field (cell indices) written by an external
enrichment step; across 586 unveil events it confirms blue→3, teal→1, and
that the targets are uniform random rather than positional (26.8% land
adjacent to the clicked cell, against 24.0% expected by chance).
"""

from __future__ import annotations

import json
import random
import statistics
from typing import Any

from macro.minigame_board import GRID_CELLS
from macro.sphere_game import choose_oh_click

# Per-cell spawn rates as a share of all 25 cells (Colblitz, confirmed
# against 96 logged boards / 2,317 revealed cells in 2026-08). The colour
# rates sum to 98%; the remaining 2% is an $oc spawn, which stays `spU`.
OH_SPAWN_RATES: dict[str, float] = {
    "spW": 0.04,
    "spR": 0.22,
    "spD": 1.46,
    "spO": 0.97,
    "spL": 2.96,
    "spY": 2.57,
    "spG": 7.88,
    "spT": 23.48,
    "spB": 54.49,
    "spP": 3.93,
    "oc": 2.00,
}

# SP each cell pays. Dark and light have no fixed value — they transform on
# click — so these are their measured means.
OH_CELL_SP: dict[str, float] = {
    "spW": 500.0,
    "spR": 150.0,
    "spD": 104.0,
    "spO": 90.0,
    "spL": 76.0,
    "spY": 55.0,
    "spG": 35.0,
    "spT": 20.0,
    "spB": 10.0,
    "spP": 5.0,
}

# Cells that unveil more of the board when clicked, and how many.
OH_UNVEILS: dict[str, int] = {"spB": 3, "spT": 1}

OH_FREE = "spP"          # costs no click
OH_HIDDEN = "spU"        # face-down
OC_CELL = "oc"           # an $oc spawn; renders as spU forever

DEFAULT_CLICKS_BUDGET = 5

# Clicking an $oc spawn grants a whole extra $oc game, worth ~314 SP (the
# logged average). It is nonetheless valued at **0 by default**, on purpose:
# an $oc cell is indistinguishable from a face-down even after being
# unveiled, so the only way to chase it is to stop claiming known value and
# click hidden tiles. Priced at its true 314 SP, a policy search happily
# buys that random drop with certain SP — the best schedule found at 10
# initial reveals was "never take any revealed sphere", which is not a
# strategy anyone should ship. Raise it only to quantify that effect, and
# report both valuations when you do.
OC_GRANT_VALUE = 0.0
OC_GRANT_TRUE_SP = 314.2

# Number of initially revealed cells, which is an upgradeable perk. Logged
# accounts show 1-5, one shows 7 and one shows 10.
DEFAULT_INITIAL_REVEALS = 3

_SEEDS = tuple(range(8))


def _btn(index: int, emoji: str = OH_HIDDEN, *, disabled: bool = False) -> dict[str, Any]:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def cell_sp(kind: str) -> float:
    """SP a cell pays when clicked (``$oc`` uses :data:`OC_GRANT_VALUE`)."""
    if kind == OC_CELL:
        return OC_GRANT_VALUE
    return OH_CELL_SP.get(kind, 0.0)


# --- Frozen "before" baseline, for the bakeoff only -------------------------
#
# Reproduces the greedy exactly as it shipped before the value-ordering fix:
# it ranked revealed spheres by the ordinal SPHERE_VALUE_RANK, which puts
# dark (5) below light (6) and orange (7) even though dark pays ~104 SP
# against orange's 90. Kept here so the bakeoff can A/B old against new;
# production carries a single policy.

_LEGACY_RANK = {"spB": 1, "spT": 2, "spG": 3, "spY": 4, "spD": 5, "spL": 6,
                "spO": 7, "spR": 8, "sp": 8, "spW": 9}


def _legacy_choose_oh_click(
    buttons: list[dict[str, Any]],
    *,
    clicks_spent: int = 0,
    clicks_budget: int = DEFAULT_CLICKS_BUDGET,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    chooser = rng or random
    budget_left = clicks_spent < clicks_budget
    free_purples: list[dict[str, Any]] = []
    value_spheres: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []

    for button in buttons:
        if not button.get("custom_id") or button.get("disabled"):
            continue
        emoji = str(button.get("emoji") or "").strip()
        if not emoji.startswith("sp"):
            continue
        if emoji == OH_FREE:
            free_purples.append(button)
        elif emoji == OH_HIDDEN:
            if budget_left:
                hidden.append(button)
        elif emoji in OH_UNVEILS:
            continue  # blue / teal skipped outright
        elif budget_left:
            value_spheres.append(button)

    def key(button: dict[str, Any]) -> tuple[int, int]:
        rank = _LEGACY_RANK.get(str(button.get("emoji") or "").strip(), 0)
        index = int(str(button["custom_id"]).split("s")[1])
        return rank, -index

    if free_purples:
        return max(free_purples, key=key)
    if value_spheres:
        return max(value_spheres, key=key)
    if hidden:
        return chooser.choice(hidden)
    return None


def generate_board(rng: random.Random) -> list[str]:
    """A 25-cell board sampled from the measured spawn rates."""
    kinds = list(OH_SPAWN_RATES)
    weights = [OH_SPAWN_RATES[k] for k in kinds]
    return rng.choices(kinds, weights=weights, k=GRID_CELLS)


def _visible_emoji(kind: str, seen: bool) -> str:
    """What the player sees. An ``$oc`` cell reads face-down even when seen."""
    if kind == OC_CELL or not seen:
        return OH_HIDDEN
    return kind


def simulate_oh_board(
    truth: list[str],
    *,
    rng: random.Random,
    initial_revealed: int = DEFAULT_INITIAL_REVEALS,
    budget: int = DEFAULT_CLICKS_BUDGET,
    revealed_cells: list[int] | None = None,
    policy: str = "current",
) -> dict[str, Any]:
    """Play one board to completion with the live ``choose_oh_click``.

    ``revealed_cells`` pins which cells start face-up (a logged board knows
    this); otherwise ``initial_revealed`` are chosen at random. ``policy``
    is ``"current"`` (the shipped chooser) or ``"legacy"`` (the frozen
    pre-fix baseline above), for the bakeoff.
    """
    chooser = _legacy_choose_oh_click if policy == "legacy" else choose_oh_click
    if revealed_cells is None:
        seen = set(rng.sample(range(GRID_CELLS), min(initial_revealed, GRID_CELLS)))
    else:
        seen = set(revealed_cells)
    taken: set[int] = set()
    total = 0.0
    spent = 0
    free_clicks = 0
    oc_grants = 0

    def unveil(count: int) -> None:
        pool = [i for i in range(GRID_CELLS) if i not in seen and i not in taken]
        for index in rng.sample(pool, min(count, len(pool))):
            seen.add(index)

    while spent < budget:
        buttons = [
            _btn(i, _visible_emoji(truth[i], i in seen), disabled=i in taken)
            for i in range(GRID_CELLS)
        ]
        choice = chooser(
            buttons, clicks_spent=spent, clicks_budget=budget, rng=rng,
        )
        if choice is None:
            break
        index = int(choice["custom_id"].split("s")[1])
        kind = truth[index]
        taken.add(index)
        seen.add(index)
        total += cell_sp(kind)

        if kind == OH_FREE:
            free_clicks += 1  # purple never costs a click
        else:
            spent += 1
        if kind == OC_CELL:
            oc_grants += 1
        if kind in OH_UNVEILS:
            unveil(OH_UNVEILS[kind])

    return {
        "base_value": total,
        "clicks_paid": spent,
        "free_clicks": free_clicks,
        "oc_grants": oc_grants,
        "seen": len(seen),
    }


# --- Real logged boards -----------------------------------------------------

# A completed board that still shows this many `spU` is simply unfinished,
# not an $oc spawn. Logged games leave at most one genuine $oc cell.
_MAX_LEFTOVER_HIDDEN = 2


def load_logged_boards(path: str) -> list[dict[str, Any]]:
    """Fully-recoverable ``$oh`` boards from a JSON or JSONL minigame log.

    Leftover ``spU`` on a *completed* board is an ``$oc`` spawn — ``$oc``
    renders face-down forever, so a cell that stayed hidden to the end of a
    finished game is one. Those cells are relabelled :data:`OC_CELL`, which
    recovers the full truth for boards that are otherwise complete. Games
    abandoned early (many cells left hidden) are dropped, since their
    unrevealed cells are unknown rather than ``$oc``.
    """
    raw = open(path, encoding="utf-8").read()
    stripped = raw.lstrip()
    rows = (
        json.loads(raw)
        if stripped.startswith("[")
        else [json.loads(line) for line in raw.splitlines() if line.strip()]
    )

    boards: list[dict[str, Any]] = []
    for row in rows:
        if row.get("game") != "oh":
            continue
        board = row.get("board") or []
        if len(board) != GRID_CELLS:
            continue
        hidden = [i for i, c in enumerate(board) if c == OH_HIDDEN]
        if len(hidden) > _MAX_LEFTOVER_HIDDEN:
            continue
        if any(c not in OH_CELL_SP and c != OH_HIDDEN for c in board):
            continue
        truth = [OC_CELL if c == OH_HIDDEN else c for c in board]
        initial = row.get("initial_board") or []
        revealed = (
            [i for i, c in enumerate(initial) if c != OH_HIDDEN]
            if len(initial) == GRID_CELLS
            else None
        )
        boards.append(
            {
                "truth": truth,
                "budget": int(row.get("clicks_budget") or DEFAULT_CLICKS_BUDGET),
                "revealed_cells": revealed,
                "logged_sp": int(row.get("base_value") or 0),
                "date_key": row.get("date_key"),
            }
        )
    return boards


def _score_boards(
    boards: list[dict[str, Any]],
    *,
    seeds: tuple[int, ...],
    initial_revealed: int | None,
    policy: str = "current",
) -> tuple[list[float], dict[str, float]]:
    """Mean SP per board across ``seeds``, plus aggregate counters."""
    per_board: list[float] = []
    grants = 0.0
    free = 0.0
    for position, entry in enumerate(boards):
        runs = []
        for seed in seeds:
            rng = random.Random((seed << 20) ^ position)
            result = simulate_oh_board(
                entry["truth"],
                rng=rng,
                budget=entry.get("budget", DEFAULT_CLICKS_BUDGET),
                revealed_cells=(
                    entry.get("revealed_cells") if initial_revealed is None else None
                ),
                initial_revealed=initial_revealed or DEFAULT_INITIAL_REVEALS,
                policy=policy,
            )
            runs.append(result["base_value"])
            grants += result["oc_grants"]
            free += result["free_clicks"]
        per_board.append(statistics.mean(runs))
    total_runs = max(len(boards) * len(seeds), 1)
    return per_board, {
        "oc_grants_per_game": grants / total_runs,
        "free_clicks_per_game": free / total_runs,
    }


def replay_logged_boards(
    path: str,
    *,
    seeds: tuple[int, ...] = _SEEDS,
    policy: str = "current",
) -> dict[str, Any]:
    """Replay every recoverable logged board, averaging over ``seeds``.

    Unveil targets are random, so a single pass is noisy; the per-board
    figure is a mean over ``seeds`` and ``seeds`` is reported so a caller
    can say how stable the number is.
    """
    boards = load_logged_boards(path)
    per_board, counters = _score_boards(
        boards, seeds=seeds, initial_revealed=None, policy=policy,
    )
    n = len(boards) or 1
    return {
        "policy": policy,
        "boards": len(boards),
        "seeds": len(seeds),
        "avg_sp": sum(per_board) / n,
        "logged_avg_sp": sum(b["logged_sp"] for b in boards) / n,
        "per_board": per_board,
        **counters,
    }


def score_oh_trials(
    *,
    trials: int = 2000,
    initial_revealed: int = DEFAULT_INITIAL_REVEALS,
    budget: int = DEFAULT_CLICKS_BUDGET,
    seed: int = 0,
    policy: str = "current",
) -> dict[str, Any]:
    """Play ``trials`` synthetic boards at a fixed initial-reveal count."""
    rng = random.Random(seed)
    boards = [
        {"truth": generate_board(rng), "budget": budget} for _ in range(trials)
    ]
    per_board, counters = _score_boards(
        boards, seeds=(seed,), initial_revealed=initial_revealed, policy=policy,
    )
    n = len(per_board) or 1
    return {
        "policy": policy,
        "trials": trials,
        "initial_revealed": initial_revealed,
        "budget": budget,
        "avg_sp": sum(per_board) / n,
        **counters,
    }
