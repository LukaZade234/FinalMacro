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
    OT_CELL_SP,
    OT_RARE_WEIGHTS,
    RARE_COLORS,
    RISK_PENALTY_SP,
    SEGMENTS,
    OtFleet,
    choose_ot_click,
    fleet_for_colors,
    ot_game_over,
    sample_fleet_placement,
)

# What one extra click is worth on top of the cell's own SP.
#
# `base_value` everywhere in this repo is `SPHERE_BASE_SP`, but that is not what
# Mudae pays. Across the ten $ot games of 2026-08-30 the awarded total is
# `2 * base_value + 36 * clicks` — exact on five of them (+1202, +2770, +1404,
# +3940, +662) and within 3% on four more. In base-SP units that flat term is
# +18 a click, whatever colour the cell turns out to be, so a longer game is
# worth more than base SP alone says.
#
# The multiplier is account-scoped ($oq grids print their own `Multiplier: 3x`),
# so this is a **reporting** figure for `paid_value` only. Nothing in
# `macro.ot_solver` may depend on it: a constant added to every cell cannot
# change an argmax anyway, and guessing someone else's shop upgrades into the
# policy would be worse than ignoring them.
OT_CLICK_BONUS_SP = 18.0

# Real boards, as 25 letters read left-to-right then top-to-bottom.
#
# `log-*` are the two hand-played games, with the SP the player scored. `run-*`
# are games the macro played on 2026-08-30 with the base SP it scored — the
# `run-10xx` ones under the pre-Extra-Chance policy, the later ones with Extra
# Chance — so `logged_sp` is the score to beat in both cases, human or machine.
# Compare *totals* against it,
# not single boards: those runs were a different build (older `OT_RARE_WEIGHTS`
# among other things), so one board can differ for unrelated reasons.
# `board-*` were transcribed from finished boards and have no score attached.
#
# The tenth game is absent on purpose: it reached 4 blues with 3 ship hits, so
# the macro stopped on a live board and 18 cells were never revealed. There is
# no ground truth to record, and that hole is itself the evidence for Extra
# Chance (see `ot_solver.EXTRA_CHANCE`).
#
# All of these are letters only, carrying no guild or channel identifiers —
# unlike `docs/minigames_to_use.jsonl`, which is gitignored for exactly that
# reason — so the harness works from a clean checkout with no local data.
KNOWN_BOARDS: tuple[dict[str, Any], ...] = (
    {"name": "board-1", "cells": "GBBOOGYBTBGYBTBBYBTLBBBTL", "logged_sp": None},
    {"name": "board-2", "cells": "TTTTBYOGBBYOGBBYBGBBBBLLB", "logged_sp": None},
    {"name": "board-3", "cells": "GBBBBGTTTTGBYDBOBYDBOBYRR", "logged_sp": None},
    {"name": "board-4", "cells": "BBBBGBYLLGBYOWGBYOWDTTTTD", "logged_sp": None},
    {"name": "board-5", "cells": "YYYTGWWRTGBBRTGDDBTOLLBBO", "logged_sp": None},
    {"name": "log-1", "cells": "BBBBBBBBBGBOOBGTTTTGYYYLL", "logged_sp": 625},
    {"name": "log-2", "cells": "BBDDBYYYBOTTTTOGGGBBBBLLB", "logged_sp": 570},
    {"name": "run-1032", "cells": "TTTTBBBOOBGGGBBYYYBBBBBLL", "logged_sp": 385},
    {"name": "run-1033", "cells": "BBBBBOOBBYTTTTYBLLBYGGGBB", "logged_sp": 590},
    {"name": "run-1034", "cells": "BGYRBBGYROBGYBOLLBBBTTTTB", "logged_sp": 1025},
    {"name": "run-1035", "cells": "YTBBBYTGGGYTROOBTRBBBDDBB", "logged_sp": 850},
    {"name": "run-1040", "cells": "BTTTTBBBOOBBYYYBGGGBBBBLL", "logged_sp": 265},
    {"name": "run-1041", "cells": "BBBYBBOOYBBLLYBGGGBBTTTTB", "logged_sp": 855},
    {"name": "run-1043", "cells": "TBYYYTLLBBTBBBBTBGGGBOOBB", "logged_sp": 450},
    {"name": "run-1043b", "cells": "YYYBOTTTTOBBGGGBBLLBBBBBB", "logged_sp": 460},
    {"name": "run-1044", "cells": "GBTDYGBTDYGBTOYWWTOBBBBBB", "logged_sp": 1610},
    {"name": "run-1756", "cells": "YYYBBBBBLLGGGBBBTTTTBOOBB", "logged_sp": 730},
    {"name": "run-1806", "cells": "BYDDBBYGGGBYBOOTTTTBBLLRR", "logged_sp": 1225},
    {"name": "run-1806b", "cells": "BBBBTBBBLTYBBLTYGGGTYBBOO", "logged_sp": 820},
    {"name": "run-1815", "cells": "BOOBBTBGBBTLGBBTLGBBTBYYY", "logged_sp": 670},
    {"name": "run-1837", "cells": "BOOLLBTTTTBYYYBGGGBBBBBBB", "logged_sp": 600},
    {"name": "run-1928", "cells": "BBBDDBTTTTGGGRRBBOOBBBYYY", "logged_sp": 920},
    {"name": "run-1930", "cells": "BDDBTYYYBTBGGGTBBBBTBBOOB", "logged_sp": 350},
    {"name": "run-1931", "cells": "YBGOOYBGDBYBGDBBBBBBBTTTT", "logged_sp": 650},
    {"name": "run-1932", "cells": "LGDYBLGDYBBGBYBTTTTBBBOOB", "logged_sp": 1285},
    {"name": "run-1933", "cells": "YYYBBTTTTBBOGGGBOBBBBBLLB", "logged_sp": 735},
    {"name": "run-1937", "cells": "TTTTBYOOBBYGGGBYBBBBBDDBB", "logged_sp": 730},
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
    extra_chance: bool = EXTRA_CHANCE,
    blue_bonus: float | None = None,
) -> dict[str, Any]:
    """Play one board to the end with the live ``choose_ot_click``.

    The end condition is only ever checked **after a blue**: crossing
    ``ot_solver.EXTRA_CHANCE_SHIP_HITS`` on a ship cell arms the ending without
    triggering it, and testing every click would cut the board short there.
    """
    fleet = fleet_of(cells, clicks_budget=budget)
    observations: dict[int, str] = {}
    taken: set[int] = set()
    blues = 0
    hits = 0
    total = 0.0
    over = False

    while not over and len(taken) < GRID_CELLS:
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
            ship_hits=hits,
            policy=policy,
            extra_chance=extra_chance,
            risk_penalty=risk_penalty,
            blue_bonus=blue_bonus,
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
            over = ot_game_over(
                blues, hits, budget=budget, extra_chance=extra_chance
            )
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
        "paid_value": total + OT_CLICK_BONUS_SP * len(taken),
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
    extra_chance: bool = EXTRA_CHANCE,
    blue_bonus: float | None = None,
) -> dict[str, Any]:
    per_board: list[float] = []
    ceilings: list[float] = []
    blues: list[int] = []
    clicks: list[int] = []
    paid: list[float] = []
    colours: list[int] = []
    perfect = 0
    for entry in boards:
        result = simulate_ot_board(
            entry["cells"],
            policy=policy,
            budget=int(entry.get("budget") or DEFAULT_CLICKS_BUDGET),
            risk_penalty=risk_penalty,
            extra_chance=extra_chance,
            blue_bonus=blue_bonus,
        )
        per_board.append(result["base_value"])
        ceilings.append(result["ship_sp"])
        blues.append(result["clicks_paid"])
        clicks.append(result["clicks"])
        paid.append(result["paid_value"])
        colours.append(result["n_colors"])
        if result["clicks"] >= GRID_CELLS:
            perfect += 1
    n = len(boards) or 1
    return {
        "policy": policy,
        "risk_penalty": risk_penalty,
        "extra_chance": extra_chance,
        "blue_bonus": blue_bonus,
        "boards": len(boards),
        "avg_sp": sum(per_board) / n,
        "avg_ceiling": sum(ceilings) / n,
        "share_of_ceiling": (sum(per_board) / sum(ceilings)) if sum(ceilings) else 0.0,
        "avg_blues": sum(blues) / n,
        "avg_clicks": sum(clicks) / n,
        "avg_paid_sp": sum(paid) / n,
        "perfect": perfect,
        "per_board": per_board,
        "n_colors": colours,
        "names": [entry.get("name") for entry in boards],
    }


def split_by_colors(result: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Break a ``_score`` result down per ``Number of different colors``.

    The Extra Chance blue bonus wins at 6-7 colours and loses at 8-9, so an
    aggregate mean averages a real effect against a real regression and reports
    neither. Anything comparing policies should go through here.
    """
    out: dict[int, dict[str, Any]] = {}
    for colours in sorted(set(result["n_colors"])):
        rows = [
            (value, name)
            for value, name, n in zip(
                result["per_board"], result["names"], result["n_colors"]
            )
            if n == colours
        ]
        values = [value for value, _ in rows]
        out[colours] = {
            "boards": len(values),
            "avg_sp": sum(values) / len(values),
            "per_board": values,
            "names": [name for _, name in rows],
        }
    return out


def replay_known_boards(
    *,
    policy: str = DEFAULT_PROBE_POLICY,
    risk_penalty: float = RISK_PENALTY_SP,
    extra_chance: bool = EXTRA_CHANCE,
    blue_bonus: float | None = None,
) -> dict[str, Any]:
    """Replay the boards baked into :data:`KNOWN_BOARDS`."""
    boards = [dict(entry) for entry in KNOWN_BOARDS]
    result = _score(
        boards,
        policy=policy,
        risk_penalty=risk_penalty,
        extra_chance=extra_chance,
        blue_bonus=blue_bonus,
    )
    logged = [b["logged_sp"] for b in boards if b.get("logged_sp") is not None]
    result["logged_avg_sp"] = (sum(logged) / len(logged)) if logged else 0.0
    return result


def replay_logged_boards(
    path: str,
    *,
    policy: str = DEFAULT_PROBE_POLICY,
    risk_penalty: float = RISK_PENALTY_SP,
    extra_chance: bool = EXTRA_CHANCE,
    blue_bonus: float | None = None,
) -> dict[str, Any]:
    """Replay every fully-revealed ``$ot`` board in a minigame log."""
    boards = load_logged_boards(path)
    result = _score(
        boards,
        policy=policy,
        risk_penalty=risk_penalty,
        extra_chance=extra_chance,
        blue_bonus=blue_bonus,
    )
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
    extra_chance: bool = EXTRA_CHANCE,
    blue_bonus: float | None = None,
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
    result = _score(
        boards,
        policy=policy,
        risk_penalty=risk_penalty,
        extra_chance=extra_chance,
        blue_bonus=blue_bonus,
    )
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
