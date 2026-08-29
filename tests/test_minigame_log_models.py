"""Validate the $oq and $oh models against real logged boards.

These pin the *game rules* the solvers assume, using boards Mudae actually
generated. The log lives outside the repo (it carries guild/channel ids, so
it is gitignored) — when it is absent these tests skip rather than fail.

Provenance: `docs/minigames_to_use.jsonl`, 263 rows spanning 2026-08-25 to
2026-08-29. At the time of writing: 101 `$oc`, 96 `$oh`, 64 `$oq`, 2 `$ot`.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from macro.oq_worlds import GRID_CELLS, NEIGHBORS, ensure_built
import macro.oq_worlds as oq_worlds

_LOG = Path(__file__).resolve().parent.parent / "docs" / "minigames_to_use.jsonl"

# $oq: purple is the target; the auto-revealed 4th shows as red or rainbow.
_OQ_MINE = {"spP", "spR", "spW"}
# Non-mine cells show their adjacent-mine count as a colour.
_OQ_ADJACENCY_COLOUR = {"spB": 0, "spT": 1, "spG": 2, "spY": 3, "spO": 4}

# $oh sphere spawn rates (Colblitz), as a share of all 25 cells. The table
# sums to 98%; the missing 2% are $oc spawns, which are indistinguishable
# from an unclicked cell and so can only be hit by luck.
_OH_SPAWN_PCT = {
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
}
_OC_SPAWN_PCT = 100.0 - sum(_OH_SPAWN_PCT.values())


def _rows(game: str) -> list[dict]:
    if not _LOG.exists():
        pytest.skip(f"{_LOG.name} not present (gitignored local log)")
    out = []
    for line in _LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("game") == game and len(row.get("board") or []) == GRID_CELLS:
            out.append(row)
    if not out:
        pytest.skip(f"no ${game} rows in {_LOG.name}")
    return out


# --- $oq: the world model ---------------------------------------------------


def _oq_boards() -> list[list[str]]:
    return [r["board"] for r in _rows("oq") if "spU" not in r["board"]]


def test_oq_boards_have_exactly_four_mines():
    for board in _oq_boards():
        assert sum(1 for c in board if c in _OQ_MINE) == 4


def test_oq_colours_are_exactly_the_adjacent_mine_count():
    """Every non-mine cell is Minesweeper-consistent with the 4 mines."""
    for board in _oq_boards():
        mines = {i for i, c in enumerate(board) if c in _OQ_MINE}
        for index, colour in enumerate(board):
            if colour in _OQ_MINE:
                continue
            adjacent = sum(1 for n in NEIGHBORS[index] if n in mines)
            assert _OQ_ADJACENCY_COLOUR[colour] == min(adjacent, 4), (
                f"cell {index} shows {colour} but has {adjacent} adjacent mines"
            )


def test_every_logged_oq_placement_exists_in_the_enumerated_worlds():
    ensure_built()
    known = {tuple(sorted(w)) for w in oq_worlds.ALL_WORLDS}
    for board in _oq_boards():
        placement = tuple(sorted(i for i, c in enumerate(board) if c in _OQ_MINE))
        assert placement in known


def test_oq_mine_placement_is_consistent_with_a_uniform_prior():
    """Chi-square over per-cell mine frequency; the solver assumes uniform."""
    boards = _oq_boards()
    seen = Counter()
    for board in boards:
        for index, colour in enumerate(board):
            if colour in _OQ_MINE:
                seen[index] += 1
    expected = len(boards) * 4 / GRID_CELLS
    chi = sum((seen.get(i, 0) - expected) ** 2 / expected for i in range(GRID_CELLS))
    assert chi < 36.4, f"chi-square {chi:.1f} exceeds the p=0.05 critical value"


def test_oq_auto_reveal_rainbow_rate_matches_the_replay_constant():
    from macro.oq_replay import OQ_RAINBOW_RATE

    boards = _oq_boards()
    auto = [b for b in boards if sum(1 for c in b if c == "spP") == 3]
    if len(auto) < 20:
        pytest.skip("too few auto-reveal events to check the rate")
    rainbow = sum(1 for b in auto if "spW" in b) / len(auto)
    assert abs(rainbow - OQ_RAINBOW_RATE) < 0.10


# --- $oh: the spawn distribution -------------------------------------------


def test_oh_spawn_rates_match_the_published_table():
    """Colblitz's per-colour rates, checked against revealed cells.

    Tolerance is deliberately loose (2 points, 0.5 for the rare colours):
    ~2,300 revealed cells is a thin sample for anything under 1%.
    """
    rows = _rows("oh")
    cells = Counter(c for r in rows for c in r["board"])
    total = sum(cells.values())
    for emoji, expected in _OH_SPAWN_PCT.items():
        got = cells[emoji] / total * 100
        tolerance = 0.5 if expected < 3 else 2.0
        assert abs(got - expected) <= tolerance, (
            f"{emoji}: logged {got:.2f}% vs published {expected:.2f}%"
        )


def test_oh_unrevealed_cells_match_the_implied_oc_spawn_rate():
    """The 2% the published table omits shows up as never-revealed cells.

    An $oc spawn is indistinguishable from an unclicked cell, so it stays
    `spU` on the final board. Games abandoned early are excluded — they
    leave many unrevealed cells for an unrelated reason.
    """
    rows = _rows("oh")
    complete = [r for r in rows if sum(1 for c in r["board"] if c == "spU") <= 2]
    assert len(complete) > 50
    leftover = sum(sum(1 for c in r["board"] if c == "spU") for r in complete)
    rate = leftover / (len(complete) * GRID_CELLS) * 100
    assert abs(rate - _OC_SPAWN_PCT) < 1.0, (
        f"unrevealed {rate:.2f}%/cell vs implied $oc spawn {_OC_SPAWN_PCT:.2f}%"
    )


def test_oh_board_colours_are_all_known_sphere_types():
    rows = _rows("oh")
    seen = {c for r in rows for c in r["board"]}
    assert seen <= set(_OH_SPAWN_PCT) | {"spU"}
