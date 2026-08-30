"""Validate the $oq, $oh and $ot models against real logged boards.

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


# --- $oh: the unveil mechanic ----------------------------------------------
#
# Logged $oh clicks carry an `unveiled` field (the cell indices a click
# exposed), written by an external enrichment step. It is the ground truth
# behind macro/oh_replay's reveal model, so pin it here.


def _unveil_events() -> list[tuple[str, int, list[int]]]:
    out = []
    for row in _rows("oh"):
        for click in row.get("clicks", []):
            unveiled = click.get("unveiled")
            cell = click.get("cell")
            if unveiled is not None and cell is not None:
                out.append((click.get("emoji"), cell, unveiled))
    if not out:
        pytest.skip("no `unveiled` data in this log")
    return out


def test_blue_unveils_three_and_teal_unveils_one():
    counts = Counter((emoji, len(u)) for emoji, _cell, u in _unveil_events())
    assert counts[("spB", 3)] > 50
    assert counts[("spT", 1)] > 20
    # No blue ever unveils a number other than 3, nor teal other than 1.
    assert not [k for k in counts if k[0] == "spB" and k[1] != 3]
    assert not [k for k in counts if k[0] == "spT" and k[1] != 1]


def test_unveiled_cells_are_uniform_random_not_adjacent():
    """Position does not matter — which is what licenses a counts-based DP.

    If unveils favoured neighbours, the solver would need to reason about
    board geometry; they do not.
    """
    events = _unveil_events()

    def neighbours(index: int) -> set[int]:
        row, col = divmod(index, 5)
        return {
            (row + dr) * 5 + (col + dc)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr or dc) and 0 <= row + dr < 5 and 0 <= col + dc < 5
        }

    total = adjacent = 0
    for _emoji, cell, unveiled in events:
        near = neighbours(cell)
        for target in unveiled:
            total += 1
            adjacent += target in near
    observed = adjacent / total
    # Expected share if targets were drawn uniformly from the other cells.
    expected = sum(len(neighbours(i)) for i in range(GRID_CELLS)) / GRID_CELLS / 24
    assert abs(observed - expected) < 0.06, (
        f"unveils land adjacent {observed:.1%} of the time vs {expected:.1%} by chance"
    )


# --- $ot --------------------------------------------------------------------
#
# The whole solver rests on two claims the grid message makes: ships are
# straight contiguous runs, and `Number of different colors: N` means the fleet
# is teal-4, green-3, yellow-3 and N-4 length-2 ships. Both are checked here
# against boards Mudae actually produced, so a rules change shows up as a test
# failure rather than as quietly worse play.


def _ot_boards() -> list[str]:
    from macro.ot_replay import board_from_emojis

    out = []
    for row in _rows("ot"):
        cells = board_from_emojis(row["board"])
        if cells is not None:
            out.append(cells)
    if not out:
        pytest.skip("no fully revealed $ot boards in the log")
    return out


def test_ot_ships_are_straight_contiguous_runs():
    """'Identical colors follow one another on the same row or column.'"""
    from macro.ot_replay import ship_segments
    from macro.ot_solver import SEGMENTS

    for cells in _ot_boards():
        masks = ship_segments(cells)
        assert masks is not None, cells
        for colour, mask in masks.items():
            length = mask.bit_count()
            assert mask in SEGMENTS[length], f"{colour} in {cells} is not a straight ship"


def test_ot_fleet_matches_the_declared_colour_count():
    """N colours means teal-4, green-3, yellow-3 and N-4 dominoes, orange among them."""
    from macro.ot_replay import ship_segments
    from macro.ot_solver import fleet_for_colors

    for cells in _ot_boards():
        masks = ship_segments(cells)
        fleet = fleet_for_colors(len(set(cells)))
        assert masks["T"].bit_count() == 4
        assert masks["G"].bit_count() == 3
        assert masks["Y"].bit_count() == 3
        dominoes = [c for c, m in masks.items() if m.bit_count() == 2]
        assert len(dominoes) == fleet.two_ships
        assert "O" in dominoes
        assert set(dominoes) - {"O"} <= {"L", "D", "R", "W"}
        assert cells.count("B") == fleet.blue_cells


def test_ot_boards_are_reachable_by_the_enumerator():
    """Each logged board survives being told its own contents."""
    from macro.ot_solver import enumerate_ot, fleet_for_colors

    for cells in _ot_boards():
        fleet = fleet_for_colors(len(set(cells)))
        observations = {index: colour for index, colour in enumerate(cells)}
        assert enumerate_ot(fleet, observations).total == 1, cells


def test_ot_blue_cells_pay_the_same_ten_sp_as_everywhere_else():
    """Blue is not worthless in $ot — the logged clicks scored it at 10."""
    from macro.ot_solver import OT_CELL_SP

    blues = [
        click
        for row in _rows("ot")
        for click in (row.get("clicks") or [])
        if click.get("emoji") == "spB"
    ]
    assert blues, "no blue clicks logged"
    assert all(click["base_sp"] == OT_CELL_SP["B"] for click in blues)
    # ...and every one of them was charged against the budget, while no ship
    # click ever was. That asymmetry is the whole game.
    assert all(click["paid"] for click in blues)
    ships = [
        click
        for row in _rows("ot")
        for click in (row.get("clicks") or [])
        if click.get("emoji") != "spB"
    ]
    assert ships and not any(click["paid"] for click in ships)


def _ot_game_shape(row: dict) -> tuple[int, int, bool] | None:
    """``(blues, ship hits before the last blue, board fully revealed)``."""
    clicks = row.get("clicks") or []
    if not clicks or row.get("reason") != "done":
        return None
    blues = hits = hits_at_last_blue = 0
    for click in clicks:
        if click.get("emoji") == "spB":
            blues += 1
            hits_at_last_blue = hits
        else:
            hits += 1
    revealed = "spU" not in (row.get("board") or [])
    return blues, hits_at_last_blue, revealed


def test_ot_extra_chance_decides_whether_the_fourth_blue_ends_the_game():
    """The rule `macro.ot_solver.ot_game_over` encodes, as logged.

    A blue ends the board only when it is the 4th-or-later *and* at least
    ``EXTRA_CHANCE_SHIP_HITS`` ship cells have already been clicked. The ten
    games of 2026-08-30 split on exactly that: nine reached their 4th blue with
    6-16 ship hits and Mudae revealed the board, while the tenth reached it with
    3 hits, kept the grid live, and was abandoned mid-game by a loop that
    stopped itself at the budget — so its board row is still full of ``spU``.

    A fully-revealed board is therefore the log's own record that the game
    really ended — *unless* we clicked all 25 cells ourselves, which under Extra
    Chance is a perfect game and reveals the board without ending it.
    """
    from macro.minigame_board import GRID_CELLS
    from macro.ot_solver import EXTRA_CHANCE_SHIP_HITS, ot_game_over

    checked = 0
    for row in _rows("ot"):
        shape = _ot_game_shape(row)
        if shape is None:
            continue
        blues, hits_at_last_blue, revealed = shape
        clicks = row.get("clicks") or []
        assert row.get("clicks_budget") == 4
        assert blues == row.get("clicks_paid")
        if len(clicks) >= GRID_CELLS:
            continue  # perfect game: we revealed it, Mudae did not
        if not revealed:
            # Never finished: the last blue must have been survivable.
            assert hits_at_last_blue < EXTRA_CHANCE_SHIP_HITS, row.get("time")
            continue
        checked += 1
        assert clicks[-1]["emoji"] == "spB", "ends on a blue"
        assert ot_game_over(blues, hits_at_last_blue), row.get("time")
    assert checked, "no finished $ot games in the log"


def test_ot_rare_ship_frequencies_still_match_the_shipped_weights():
    """`OT_RARE_WEIGHTS` is measured, so the log is allowed to contradict it.

    It used to be the $oh per-cell spawn rates, which predicted 1.2 reds and
    0.2 rainbows across the rare slots we had and were badly wrong on both.
    This does not re-fit the numbers — 26 slots is far too few — it only fails
    when a colour has drifted far enough that they should be re-derived.
    """
    from macro.ot_solver import OT_RARE_WEIGHTS, RARE_COLORS

    seen: dict[str, int] = {colour: 0 for colour in RARE_COLORS}
    for cells in _ot_boards():
        for colour in set(cells) & set(RARE_COLORS):
            seen[colour] += 1
    total = sum(seen.values())
    if total < 20:
        pytest.skip(f"only {total} rare ship slots logged so far")

    weight_total = sum(OT_RARE_WEIGHTS.values())
    for colour, count in seen.items():
        expected = total * OT_RARE_WEIGHTS[colour] / weight_total
        # Poisson-ish: 3 standard deviations, floored so a rare colour turning
        # up twice when 0.5 was expected does not fail on its own.
        allowed = max(3.0, 3.0 * (expected ** 0.5))
        assert abs(count - expected) <= allowed, (
            f"{colour}: {count} of {total} rare slots vs {expected:.1f} expected"
            " — re-derive OT_RARE_WEIGHTS"
        )
