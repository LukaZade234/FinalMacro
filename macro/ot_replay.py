"""Replay ``$ot`` boards — real logged ones, or generated for volume.

Built the same way as :mod:`macro.oc_replay` and :mod:`macro.oh_replay`: fake
the Discord button dicts and drive the **real**
:func:`macro.ot_solver.choose_ot_click` through them, so the harness scores
shipped code rather than a copy of it.

**Prefer** :func:`replay_known_boards` and :func:`replay_logged_boards` — real
Mudae boards are ground truth. :func:`generate_board` exists for volume, and
its two generators exist because we do not know which one Mudae is:

``uniform``
    Every legal fleet placement equally likely. This is exactly what
    :func:`macro.ot_solver.enumerate_ot` assumes, so a policy scored under it
    is being graded by its own prior.
``sequential``
    Place teal at a uniformly random legal spot, then green, then yellow, then
    the dominoes one at a time, restarting on a dead end. Closer to how a bot
    would actually build a board, and *not* uniform over outcomes.

Report both. If the policy ranking flips between them, the ranking is a
property of the prior rather than of the policy, and only real boards can
break the tie.

Unlike ``$oh`` this replay is **deterministic** — the solver takes no random
choices and a board reveals the same cells every time — so a single pass per
board is the whole answer, with no seed averaging.
"""

from __future__ import annotations

import json
import random
import statistics
from typing import Any

from macro.minigame_board import GRID_CELLS
from macro.ot_solver import (
    BLUE,
    DEFAULT_CLICKS_BUDGET,
    DEFAULT_PROBE_POLICY,
    EXTRA_CHANCE,
    EXTRA_CHANCE_SHIP_HITS,
    OT_CELL_SP,
    OT_RARE_WEIGHTS,
    RARE_COLORS,
    RISK_PENALTY_SP,
    SEGMENTS,
    OtFleet,
    choose_ot_click,
    fleet_for_colors,
    sample_fleet_placement,
)

# Real boards, as 25 letters read left-to-right then top-to-bottom.
#
# `log-*` are the two hand-played games in the minigame log, with the SP the
# player actually scored. The rest were transcribed from finished boards. They
# carry no guild or channel identifiers — unlike `docs/minigames_to_use.jsonl`,
# which is gitignored for exactly that reason — so the harness works from a
# clean checkout with no local data.
KNOWN_BOARDS: tuple[dict[str, Any], ...] = (
    {"name": "board-1", "cells": "GBBOOGYBTBGYBTBBYBTLBBBTL", "logged_sp": None},
    {"name": "board-2", "cells": "TTTTBYOGBBYOGBBYBGBBBBLLB", "logged_sp": None},
    {"name": "board-3", "cells": "GBBBBGTTTTGBYDBOBYDBOBYRR", "logged_sp": None},
    {"name": "board-4", "cells": "BBBBGBYLLGBYOWGBYOWDTTTTD", "logged_sp": None},
    {"name": "board-5", "cells": "YYYTGWWRTGBBRTGDDBTOLLBBO", "logged_sp": None},
    {"name": "log-1", "cells": "BBBBBBBBBGBOOBGTTTTGYYYLL", "logged_sp": 625},
    {"name": "log-2", "cells": "BBDDBYYYBOTTTTOGGGBBBBLLB", "logged_sp": 570},
)

_EMOJI_TO_LETTER = {
    "spB": "B", "spT": "T", "spG": "G", "spY": "Y", "spO": "O",
    "spL": "L", "spD": "D", "spR": "R", "sp": "R", "spW": "W",
}
_LETTER_TO_EMOJI = {
    "B": "spB", "T": "spT", "G": "spG", "Y": "spY", "O": "spO",
    "L": "spL", "D": "spD", "R": "spR", "W": "spW",
}
HIDDEN = "spU"

GENERATORS = ("uniform", "sequential")


def _button(index: int, emoji: str, *, disabled: bool = False) -> dict[str, Any]:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def colors_on(cells: str) -> int:
    """``Number of different colors`` for a finished board."""
    return len(set(cells))


def fleet_of(cells: str, *, clicks_budget: int = DEFAULT_CLICKS_BUDGET) -> OtFleet:
    return fleet_for_colors(colors_on(cells), clicks_budget=clicks_budget)


def ship_sp(cells: str) -> float:
    """SP of every ship cell — what a perfect game collects for free.

    Used as the yardstick rather than as a hard maximum: blue pays 10 SP too,
    so a game that had to spend its budget can score slightly *above* this.
    """
    return sum(OT_CELL_SP[c] for c in cells if c != BLUE)


# --- Playing a board --------------------------------------------------------


def simulate_ot_board(
    cells: str,
    *,
    policy: str = DEFAULT_PROBE_POLICY,
    budget: int = DEFAULT_CLICKS_BUDGET,
    risk_penalty: float = RISK_PENALTY_SP,
) -> dict[str, Any]:
    """Play one board to the end with the live ``choose_ot_click``."""
    fleet = fleet_of(cells, clicks_budget=budget)
    observations: dict[int, str] = {}
    taken: set[int] = set()
    blues = 0
    hits = 0
    total = 0.0

    def over() -> bool:
        if blues < budget:
            return False
        # Extra Chance, if it is real, suspends the ending until enough ship
        # cells have been hit. Off by default — see `ot_solver.EXTRA_CHANCE`.
        return not EXTRA_CHANCE or hits >= EXTRA_CHANCE_SHIP_HITS

    while not over() and len(taken) < GRID_CELLS:
        buttons = [
            _button(
                index,
                _LETTER_TO_EMOJI[cells[index]] if index in taken else HIDDEN,
                disabled=index in taken,
            )
            for index in range(GRID_CELLS)
        ]
        choice = choose_ot_click(
            buttons,
            observations,
            fleet=fleet,
            blues_spent=blues,
            policy=policy,
            risk_penalty=risk_penalty,
        )
        if choice is None:
            break
        index = int(str(choice["custom_id"]).split("s")[1])
        colour = cells[index]
        taken.add(index)
        observations[index] = colour
        total += OT_CELL_SP[colour]
        if colour == BLUE:
            blues += 1
        else:
            hits += 1

    ceiling = ship_sp(cells)
    return {
        "base_value": total,
        "clicks": len(taken),
        "clicks_paid": blues,
        "ship_hits": hits,
        "ship_sp": ceiling,
        "share_of_ceiling": (total / ceiling) if ceiling else 0.0,
        "n_colors": fleet.n_colors,
    }


# --- Real boards ------------------------------------------------------------


def board_from_emojis(board: list[str]) -> str | None:
    """A logged 25-emoji board as letters, or ``None`` if not fully revealed."""
    if len(board) < GRID_CELLS:
        return None
    letters = []
    for emoji in board[:GRID_CELLS]:
        letter = _EMOJI_TO_LETTER.get(str(emoji or "").strip())
        if letter is None:
            return None
        letters.append(letter)
    return "".join(letters)


def load_logged_boards(path: str) -> list[dict[str, Any]]:
    """Fully-revealed ``$ot`` boards from a JSON or JSONL minigame log."""
    raw = open(path, encoding="utf-8").read()
    stripped = raw.lstrip()
    rows = (
        json.loads(raw)
        if stripped.startswith("[")
        else [json.loads(line) for line in raw.splitlines() if line.strip()]
    )
    boards: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        if row.get("game") != "ot":
            continue
        cells = board_from_emojis(row.get("board") or [])
        if cells is None or not is_legal_board(cells):
            continue
        boards.append(
            {
                "name": row.get("date_key") or f"row-{position}",
                "cells": cells,
                "logged_sp": row.get("base_value"),
                "budget": int(row.get("clicks_budget") or DEFAULT_CLICKS_BUDGET),
            }
        )
    return boards


def ship_segments(cells: str) -> dict[str, int] | None:
    """Each colour's cell mask, or ``None`` when a colour is not one straight ship."""
    masks: dict[str, int] = {}
    for index, colour in enumerate(cells):
        if colour == BLUE:
            continue
        masks[colour] = masks.get(colour, 0) | (1 << index)
    for colour, mask in masks.items():
        length = mask.bit_count()
        if length not in SEGMENTS or mask not in SEGMENTS[length]:
            return None
    return masks


def is_legal_board(cells: str) -> bool:
    """True when ``cells`` is a fleet the ``$ot`` rules could actually produce."""
    if len(cells) != GRID_CELLS:
        return False
    masks = ship_segments(cells)
    if masks is None:
        return False
    lengths = sorted(mask.bit_count() for mask in masks.values())
    expected = [2] * (colors_on(cells) - 4) + [3, 3, 4]
    return lengths == sorted(expected) and "O" in masks


# --- Generators -------------------------------------------------------------


def _sample_sequential(
    fleet: OtFleet, rng: random.Random
) -> tuple[int, int, int, list[int]] | None:
    used = 0
    placed: list[int] = []
    for length in (4, 3, 3):
        options = [s for s in SEGMENTS[length] if not s & used]
        if not options:
            return None
        segment = rng.choice(options)
        placed.append(segment)
        used |= segment
    dominoes: list[int] = []
    for _ in range(fleet.two_ships):
        options = [s for s in SEGMENTS[2] if not s & used]
        if not options:
            return None
        domino = rng.choice(options)
        dominoes.append(domino)
        used |= domino
    return placed[0], placed[1], placed[2], dominoes


def _paint(
    teal: int, green: int, yellow: int, dominoes: list[int], rng: random.Random
) -> str:
    """Turn placements into a 25-letter board, naming the length-2 ships."""
    cells = [BLUE] * GRID_CELLS

    def fill(mask: int, colour: str) -> None:
        rest = mask
        while rest:
            bit = rest & -rest
            cells[bit.bit_length() - 1] = colour
            rest ^= bit

    fill(teal, "T")
    fill(green, "G")
    fill(yellow, "Y")

    rares = list(RARE_COLORS)
    weights = [OT_RARE_WEIGHTS[colour] for colour in rares]
    chosen: list[str] = []
    for _ in range(len(dominoes) - 1):
        pick = rng.choices(rares, weights=weights, k=1)[0]
        position = rares.index(pick)
        rares.pop(position)
        weights.pop(position)
        chosen.append(pick)
    colours = ["O"] + chosen
    rng.shuffle(colours)
    for domino, colour in zip(dominoes, colours):
        fill(domino, colour)
    return "".join(cells)


def generate_board(
    rng: random.Random, n_colors: int, *, generator: str = "uniform"
) -> str:
    """One random board with ``n_colors`` distinct colours."""
    fleet = fleet_for_colors(n_colors)
    while True:
        if generator == "sequential":
            sample = _sample_sequential(fleet, rng)
            if sample is None:
                continue
        else:
            sample = sample_fleet_placement(fleet, rng)
        return _paint(*sample, rng)


# --- Scoring ----------------------------------------------------------------


def _score(
    boards: list[dict[str, Any]],
    *,
    policy: str,
    risk_penalty: float = RISK_PENALTY_SP,
) -> dict[str, Any]:
    per_board: list[float] = []
    ceilings: list[float] = []
    blues: list[int] = []
    for entry in boards:
        result = simulate_ot_board(
            entry["cells"],
            policy=policy,
            budget=int(entry.get("budget") or DEFAULT_CLICKS_BUDGET),
            risk_penalty=risk_penalty,
        )
        per_board.append(result["base_value"])
        ceilings.append(result["ship_sp"])
        blues.append(result["clicks_paid"])
    n = len(boards) or 1
    return {
        "policy": policy,
        "risk_penalty": risk_penalty,
        "boards": len(boards),
        "avg_sp": sum(per_board) / n,
        "avg_ceiling": sum(ceilings) / n,
        "share_of_ceiling": (sum(per_board) / sum(ceilings)) if sum(ceilings) else 0.0,
        "avg_blues": sum(blues) / n,
        "per_board": per_board,
        "names": [entry.get("name") for entry in boards],
    }


def replay_known_boards(
    *, policy: str = DEFAULT_PROBE_POLICY, risk_penalty: float = RISK_PENALTY_SP
) -> dict[str, Any]:
    """Replay the boards baked into :data:`KNOWN_BOARDS`."""
    return _score(
        [dict(entry) for entry in KNOWN_BOARDS],
        policy=policy,
        risk_penalty=risk_penalty,
    )


def replay_logged_boards(
    path: str,
    *,
    policy: str = DEFAULT_PROBE_POLICY,
    risk_penalty: float = RISK_PENALTY_SP,
) -> dict[str, Any]:
    """Replay every fully-revealed ``$ot`` board in a minigame log."""
    boards = load_logged_boards(path)
    result = _score(boards, policy=policy, risk_penalty=risk_penalty)
    logged = [b["logged_sp"] for b in boards if b.get("logged_sp") is not None]
    result["logged_avg_sp"] = (sum(logged) / len(logged)) if logged else 0.0
    return result


def score_ot_trials(
    *,
    trials: int = 200,
    n_colors: int | None = None,
    generator: str = "uniform",
    policy: str = DEFAULT_PROBE_POLICY,
    risk_penalty: float = RISK_PENALTY_SP,
    seed: int = 0,
) -> dict[str, Any]:
    """Play generated boards. ``n_colors`` of ``None`` cycles 6-9 evenly."""
    rng = random.Random(seed)
    boards = []
    for index in range(trials):
        colours = n_colors if n_colors is not None else 6 + index % 4
        boards.append(
            {"name": f"{generator}-{index}", "cells": generate_board(
                rng, colours, generator=generator
            )}
        )
    result = _score(boards, policy=policy, risk_penalty=risk_penalty)
    result["generator"] = generator
    result["trials"] = trials
    return result


def paired_delta(new: list[float], base: list[float]) -> dict[str, Any]:
    """Paired per-board comparison with the statistics to judge it by.

    Same shape as :func:`macro.oc_replay.paired_delta`, and reported for the
    same reason: on a small sample a policy difference is usually noise, and
    ``significant`` is the only field that should drive a decision.
    """
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
