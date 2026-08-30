"""Constraint solver for the Mudae ``$ot`` battleship minigame.

``$ot`` hides a fleet of straight, contiguous ships on the 5×5 grid. The grid
message states the rules and, crucially, the fleet size::

    You can click 4 times on the buttons below (2 minutes).
    All colors are free (they don't consume clicks) except for the blue spheres
    Identical colors follow one another on the same row or column. ...
    Spheres to find: teal = 4, green = 3, yellow = 3, rarer spheres = 2.
    Number of different colors: 6

So the fleet is known before the first click. Teal (4), green (3) and yellow
(3) are always present; ``Number of different colors: N`` gives **N − 4**
length-2 ships — always orange plus ``N − 5`` rares drawn from light, dark,
red and rainbow. *Which* rares is not stated, only how many.

============ ======= ============ ========== ==============
``N``        2-ships  ship cells   blue cells configurations
============ ======= ============ ========== ==============
6             2       14           11            597,408
7             3       16            9          1,890,960
8             4       18            7          3,082,032
9             5       20            5          2,485,616
============ ======= ============ ========== ==============

Counting, not enumerating
-------------------------
Those configuration counts are far too large to enumerate per decision, and
they do not need to be. A configuration is a teal placement, a green
placement, a yellow placement, and a set of ``k`` disjoint dominoes on
whatever is left. There are only **5,520** legal (teal, green, yellow)
triples, and the dominoes are counted rather than listed by
:func:`_packings`, a memoised DP over the free region. Per-cell marginals
fall out of one identity::

    configurations where cell c is NOT covered by a domino
        == packings(free_region without c, k)

so ``covered(c) = packings(free, k) - packings(free \\ {c}, k)``.

That is exact — it reproduces the brute-force DFS counts above — and costs
0.28s from a cold cache, 0.09s after one observation and ~0.002s once three
cells are known. Cheap enough that the probe rule can afford a full one-ply
lookahead (:data:`LOOKAHEAD_TOP_K`).

Rules the policy is built on
----------------------------
* Ship cells are **free**; only blue costs a click. The budget is 4.
* :data:`EXTRA_CHANCE` is off: the game is assumed to end on the 4th blue
  regardless of how many ship cells have been hit. Mudae's "Extra Chance"
  reportedly suspends that below 5 ship hits, but neither logged game ever
  reached 4 blues while under 5 hits, so nothing here can confirm it and the
  conservative reading is the one that cannot throw a game away.
* Under that rule ship hits never matter, which makes clicking any cell with
  ``P(blue) = 0`` strictly dominant — free SP, free information, no risk.
  The only real decision is which cell to probe when nothing is certain.

The probe rule
--------------
Take every certain ship first, then probe by
``ev(c) - RISK_PENALTY_SP * P(blue at c)``. Maximising plain EV — the obvious
rule, and the one the 7 real boards prefer — is measurably the *worst* member
of that family once there are enough boards to tell; see
:data:`RISK_PENALTY_SP` for the sweep and for why the penalty is tuned low
rather than high.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations
from typing import Any, Mapping

from macro.minigame_board import GRID_CELLS, sphere_buttons
from mudae.constants import SPHERE_BASE_SP, canonical_sphere_emoji

GRID_SIZE = 5
_FULL_MASK = (1 << GRID_CELLS) - 1

BLUE = "B"
# Ships that are on every board, as (colour, length).
FIXED_SHIPS: tuple[tuple[str, int], ...] = (("T", 4), ("G", 3), ("Y", 3))
# Every length-2 ship colour. Orange is always present; the rest are the
# "rarer spheres" the message counts but does not name.
TWO_CELL_COLORS: tuple[str, ...] = ("O", "L", "D", "R", "W")
RARE_COLORS: tuple[str, ...] = ("L", "D", "R", "W")
# A revealed length-2 cell whose colour we could not identify. Geometrically
# it constrains exactly as much as a named one — only its SP is unknown.
UNKNOWN_TWO = "2"

OT_COLORS = frozenset(BLUE) | {colour for colour, _ in FIXED_SHIPS} | set(TWO_CELL_COLORS)
OT_OBSERVATIONS = OT_COLORS | {UNKNOWN_TWO}

# SP each cell pays. Blue/teal/green/yellow/orange/red/rainbow are the shared
# `SPHERE_BASE_SP` ladder. Light and dark have no fixed value anywhere in
# Mudae — they transform on click — so these are the measured means, the same
# figures `macro.oh_replay.OH_CELL_SP` carries.
OT_CELL_SP: dict[str, float] = {
    "B": float(SPHERE_BASE_SP["spB"]),
    "T": float(SPHERE_BASE_SP["spT"]),
    "G": float(SPHERE_BASE_SP["spG"]),
    "Y": float(SPHERE_BASE_SP["spY"]),
    "O": float(SPHERE_BASE_SP["spO"]),
    "L": 76.0,
    "D": 104.0,
    "R": float(SPHERE_BASE_SP["spR"]),
    "W": float(SPHERE_BASE_SP["spW"]),
}

# Relative chance of each rare being one of the board's length-2 ships. No
# published table exists, so these are the Colblitz $oh per-cell spawn rates
# on the assumption that ship rarity tracks sphere rarity. Seven known boards
# are far too few to fit this — treat it as an assumption the bakeoff can
# sweep, not a measurement.
OT_RARE_WEIGHTS: dict[str, float] = {"L": 2.96, "D": 1.46, "R": 0.22, "W": 0.04}

DEFAULT_CLICKS_BUDGET = 4
# See the module docstring. Flipping this on is a rules change, not a policy
# change, and needs a real board to confirm it first. When on, blues stop
# ending the game until EXTRA_CHANCE_SHIP_HITS ship cells have been hit —
# which would make "probe first, harvest last" the winning shape instead.
# `macro.ot_replay.simulate_ot_board` honours it too, so the harness can price
# the difference before anyone commits to it.
EXTRA_CHANCE = False
EXTRA_CHANCE_SHIP_HITS = 5

_EMOJI_TO_OT: dict[str, str] = {
    "spB": "B",
    "spT": "T",
    "spG": "G",
    "spY": "Y",
    "spO": "O",
    "spL": "L",
    "spD": "D",
    "spR": "R",
    "sp": "R",
    "spW": "W",
}

_COLORS_RE = re.compile(r"number\s+of\s+different\s+colou?rs\s*:\s*\*{0,2}(\d+)", re.IGNORECASE)


# --- Board geometry ---------------------------------------------------------


def _segments(length: int) -> tuple[int, ...]:
    """Every straight contiguous placement of a ship of ``length``, as bitmasks."""
    out: list[int] = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE - length + 1):
            mask = 0
            for step in range(length):
                mask |= 1 << (row * GRID_SIZE + col + step)
            out.append(mask)
    for col in range(GRID_SIZE):
        for row in range(GRID_SIZE - length + 1):
            mask = 0
            for step in range(length):
                mask |= 1 << ((row + step) * GRID_SIZE + col)
            out.append(mask)
    return tuple(out)


# 20 placements for length 4, 30 for length 3, 40 for length 2.
SEGMENTS: dict[int, tuple[int, ...]] = {length: _segments(length) for length in (2, 3, 4)}

_DOMINOES = SEGMENTS[2]
_DOMINO_SET = frozenset(_DOMINOES)
# Dominoes keyed by their lowest cell — the DP only ever extends forward.
_FWD_DOMINOES: tuple[tuple[int, ...], ...] = tuple(
    tuple(d for d in _DOMINOES if (d & -d).bit_length() - 1 == cell)
    for cell in range(GRID_CELLS)
)
_DOMINOES_AT: tuple[tuple[int, ...], ...] = tuple(
    tuple(d for d in _DOMINOES if d >> cell & 1) for cell in range(GRID_CELLS)
)

# Distinct (region, count, forced) states stay in the tens of thousands per
# fleet size and are shared across every triple, so a generous bound keeps the
# whole working set resident without growing without limit in a long session.
_PACKING_CACHE_SIZE = 1 << 18


@lru_cache(maxsize=_PACKING_CACHE_SIZE)
def _packings(region: int, count: int, forced: int) -> int:
    """Ways to lay ``count`` disjoint dominoes in ``region``, covering ``forced``.

    ``region`` and ``forced`` are 25-bit cell masks. Cells outside ``region``
    are unavailable (a ship, or a revealed blue); cells in ``forced`` are known
    to belong to *some* length-2 ship and so must end up covered.
    """
    if forced & ~region:
        return 0
    if count == 0:
        return 1 if forced == 0 else 0
    if region.bit_count() < 2 * count:
        return 0
    lowest = region & -region
    cell = lowest.bit_length() - 1
    total = 0
    if not (forced & lowest):
        total = _packings(region ^ lowest, count, forced)
    for domino in _FWD_DOMINOES[cell]:
        if domino & region != domino:
            continue
        total += _packings(region & ~domino, count - 1, forced & ~domino)
    return total


# --- Fleet ------------------------------------------------------------------


@dataclass(frozen=True)
class OtFleet:
    """The ships on one board, as the grid message describes them."""

    n_colors: int
    clicks_budget: int = DEFAULT_CLICKS_BUDGET

    @property
    def two_ships(self) -> int:
        """Length-2 ships: orange plus ``n_colors - 5`` rares."""
        return self.n_colors - 4

    @property
    def ship_cells(self) -> int:
        return 10 + 2 * self.two_ships

    @property
    def blue_cells(self) -> int:
        return GRID_CELLS - self.ship_cells


def fleet_for_colors(
    n_colors: int, *, clicks_budget: int = DEFAULT_CLICKS_BUDGET
) -> OtFleet:
    return OtFleet(n_colors=int(n_colors), clicks_budget=int(clicks_budget))


def parse_ot_fleet(
    content: str, *, clicks_budget: int = DEFAULT_CLICKS_BUDGET
) -> OtFleet | None:
    """Read ``Number of different colors: N`` off the grid message.

    The click budget is *not* parsed here — ``macro.sphere_game`` already owns
    that regex, so a caller passes what ``parse_clicks_allowed`` gave it rather
    than this module keeping a second copy.
    """
    match = _COLORS_RE.search(content or "")
    if not match:
        return None
    n_colors = int(match.group(1))
    if not 6 <= n_colors <= 9:
        return None
    return fleet_for_colors(n_colors, clicks_budget=clicks_budget)


@lru_cache(maxsize=8)
def _triple_weights(
    two_ships: int,
) -> tuple[tuple[tuple[int, int, int], ...], tuple[int, ...]]:
    """Every legal (teal, green, yellow) triple and how many boards each admits."""
    triples: list[tuple[int, int, int]] = []
    weights: list[int] = []
    for teal in SEGMENTS[4]:
        for green in SEGMENTS[3]:
            if teal & green:
                continue
            teal_green = teal | green
            for yellow in SEGMENTS[3]:
                if yellow & teal_green:
                    continue
                free = _FULL_MASK & ~(teal_green | yellow)
                admits = _packings(free, two_ships, 0)
                if admits:
                    triples.append((teal, green, yellow))
                    weights.append(admits)
    return tuple(triples), tuple(weights)


def sample_fleet_placement(
    fleet: OtFleet, rng: Any
) -> tuple[int, int, int, list[int]]:
    """A uniformly random legal placement, as ``(teal, green, yellow, dominoes)``.

    Sampled by walking the same DP that counts placements — pick a triple in
    proportion to how many boards it admits, then unpick the dominoes one
    branch at a time — so it is exactly uniform over the configuration space
    :func:`enumerate_ot` reasons about, with nothing materialised.
    """
    triples, weights = _triple_weights(fleet.two_ships)
    teal, green, yellow = rng.choices(triples, weights=weights, k=1)[0]
    region = _FULL_MASK & ~(teal | green | yellow)
    count = fleet.two_ships
    chosen: list[int] = []
    while count:
        pick = rng.randrange(_packings(region, count, 0))
        lowest = region & -region
        cell = lowest.bit_length() - 1
        weight = _packings(region ^ lowest, count, 0)
        if pick < weight:
            region ^= lowest
            continue
        pick -= weight
        for domino in _FWD_DOMINOES[cell]:
            if domino & region != domino:
                continue
            weight = _packings(region & ~domino, count - 1, 0)
            if pick < weight:
                chosen.append(domino)
                region &= ~domino
                count -= 1
                break
            pick -= weight
    return teal, green, yellow, chosen


def expected_two_cell_sp(fleet: OtFleet, seen: set[str] | frozenset[str]) -> float:
    """Mean SP of a length-2 cell whose colour has not been revealed yet.

    The board carries orange plus ``k - 1`` rares. Once some of those colours
    are on the table the rest are drawn from what is left, weighted by
    :data:`OT_RARE_WEIGHTS`. Same-length ships are interchangeable, so an
    unidentified domino cell is worth the mean of the colours still unaccounted
    for.
    """
    seen_two = {colour for colour in seen if colour in TWO_CELL_COLORS}
    remaining_rares = [colour for colour in RARE_COLORS if colour not in seen_two]
    seen_rares = len([colour for colour in seen_two if colour != "O"])
    needed = max(0, min(fleet.two_ships - 1 - seen_rares, len(remaining_rares)))
    base = ["O"] if "O" not in seen_two else []

    total_weight = 0.0
    total_value = 0.0
    for combo in combinations(remaining_rares, needed):
        weight = 1.0
        for colour in combo:
            weight *= OT_RARE_WEIGHTS[colour]
        colours = base + list(combo)
        if not colours:
            continue
        total_value += weight * sum(OT_CELL_SP[c] for c in colours) / len(colours)
        total_weight += weight
    if not total_weight:
        return OT_CELL_SP["O"]
    return total_value / total_weight


# --- Observations -----------------------------------------------------------


def emoji_to_ot_color(emoji: str) -> str | None:
    key = canonical_sphere_emoji(emoji)
    if not key or key == "spU":
        return None
    return _EMOJI_TO_OT.get(key)


def observations_from_buttons(buttons: list[dict[str, Any]]) -> dict[int, str]:
    obs: dict[int, str] = {}
    for index, button in enumerate(sphere_buttons(buttons)):
        if index >= GRID_CELLS:
            break
        colour = emoji_to_ot_color((button.get("emoji") or "").strip())
        if colour:
            obs[index] = colour
    return obs


def merge_observations(*sources: dict[int, str]) -> dict[int, str]:
    merged: dict[int, str] = {}
    for source in sources:
        for index, colour in source.items():
            if colour not in OT_OBSERVATIONS:
                continue
            previous = merged.get(index)
            if previous is not None and previous != colour:
                # A named colour supersedes the generic "some length-2 ship".
                if previous == UNKNOWN_TWO and colour in TWO_CELL_COLORS:
                    merged[index] = colour
                    continue
                if colour == UNKNOWN_TWO and previous in TWO_CELL_COLORS:
                    continue
                raise ValueError(f"conflicting colour at {index}: {previous} vs {colour}")
            merged[index] = colour
    return merged


# --- Marginals --------------------------------------------------------------


@dataclass(frozen=True)
class OtMarginals:
    """Per-cell configuration counts, by what the cell turns out to be.

    ``blue``/``teal``/``green``/``yellow``/``two`` partition ``total`` for
    every cell. ``pinned`` breaks ``two`` down for colours whose ship has been
    identified — a cell adjacent to a revealed orange might be that same
    orange ship, which is worth 90 rather than the blended
    :attr:`unknown_two_sp`.
    """

    fleet: OtFleet
    total: int
    blue: tuple[int, ...]
    teal: tuple[int, ...]
    green: tuple[int, ...]
    yellow: tuple[int, ...]
    two: tuple[int, ...]
    unknown_two_sp: float
    pinned: Mapping[str, tuple[int, ...]] = field(default_factory=dict)

    def p_blue(self, cell: int) -> float:
        if not self.total:
            return 0.0
        return self.blue[cell] / self.total

    def is_certain_ship(self, cell: int) -> bool:
        """True when no surviving configuration leaves this cell empty."""
        return bool(self.total) and self.blue[cell] == 0

    def unpinned_two(self, cell: int) -> int:
        pinned = sum(counts[cell] for counts in self.pinned.values())
        return max(0, self.two[cell] - pinned)

    def ev(self, cell: int) -> float:
        """Expected SP from clicking ``cell``."""
        if not self.total:
            return 0.0
        value = (
            self.blue[cell] * OT_CELL_SP["B"]
            + self.teal[cell] * OT_CELL_SP["T"]
            + self.green[cell] * OT_CELL_SP["G"]
            + self.yellow[cell] * OT_CELL_SP["Y"]
        )
        for colour, counts in self.pinned.items():
            value += counts[cell] * OT_CELL_SP[colour]
        value += self.unpinned_two(cell) * self.unknown_two_sp
        return value / self.total

    def outcomes(self, cell: int) -> list[tuple[str, float]]:
        """``(observation, probability)`` for each way ``cell`` can resolve.

        Length-2 outcomes collapse to :data:`UNKNOWN_TWO`. Which rare it turns
        out to be changes that cell's payout but not the geometry, and the
        geometry is what a lookahead is asking about.
        """
        if not self.total:
            return []
        out: list[tuple[str, float]] = []
        for colour, counts in (
            (BLUE, self.blue),
            ("T", self.teal),
            ("G", self.green),
            ("Y", self.yellow),
            (UNKNOWN_TWO, self.two),
        ):
            if counts[cell]:
                out.append((colour, counts[cell] / self.total))
        return out

    def outcome_sp(self, cell: int, outcome: str) -> float:
        """SP paid when ``cell`` resolves to ``outcome``.

        :data:`UNKNOWN_TWO` blends the identified ships adjacent to this cell
        with :attr:`unknown_two_sp` for the ones still unnamed.
        """
        if outcome != UNKNOWN_TWO:
            return OT_CELL_SP.get(outcome, 0.0)
        covered = self.two[cell]
        if not covered:
            return self.unknown_two_sp
        value = sum(
            counts[cell] * OT_CELL_SP[colour] for colour, counts in self.pinned.items()
        )
        value += self.unpinned_two(cell) * self.unknown_two_sp
        return value / covered

    def entropy(self, cell: int) -> float:
        """Shannon entropy (bits) of what ``cell`` will turn out to be."""
        total = 0.0
        for _, probability in self.outcomes(cell):
            if probability > 0.0:
                total -= probability * math.log2(probability)
        return total


def _empty_marginals(fleet: OtFleet) -> OtMarginals:
    zeros = (0,) * GRID_CELLS
    return OtMarginals(
        fleet=fleet,
        total=0,
        blue=zeros,
        teal=zeros,
        green=zeros,
        yellow=zeros,
        two=zeros,
        unknown_two_sp=0.0,
        pinned={},
    )


def _mask_of(cells: list[int]) -> int:
    mask = 0
    for cell in cells:
        mask |= 1 << cell
    return mask


def enumerate_ot(fleet: OtFleet, observations: Mapping[int, str]) -> OtMarginals:
    """Exact per-cell marginals over every fleet placement matching ``observations``.

    Returns zeroed marginals when nothing is consistent, which in practice
    means the colour count was misread — callers should treat ``total == 0``
    as "no information", not as "the board is impossible".

    Memoised on the observation set: a game loop typically asks for the stats
    line and then for a click on the very same state, and the lookahead probe
    revisits states as it scores candidates.
    """
    return _enumerate_cached(fleet, tuple(sorted(observations.items())))


@lru_cache(maxsize=512)
def _enumerate_cached(
    fleet: OtFleet, observations: tuple[tuple[int, str], ...]
) -> OtMarginals:
    return _enumerate(fleet, dict(observations))


def _enumerate(fleet: OtFleet, observations: Mapping[int, str]) -> OtMarginals:
    blue_mask = 0
    forced = 0
    fixed_cells: dict[str, list[int]] = {"T": [], "G": [], "Y": []}
    two_cells: dict[str, list[int]] = {}

    for cell, colour in observations.items():
        if not 0 <= cell < GRID_CELLS:
            continue
        bit = 1 << cell
        if colour == BLUE:
            blue_mask |= bit
        elif colour in fixed_cells:
            fixed_cells[colour].append(cell)
        elif colour == UNKNOWN_TWO:
            forced |= bit
        elif colour in TWO_CELL_COLORS:
            two_cells.setdefault(colour, []).append(cell)
            forced |= bit

    # A colour seen on two cells identifies its whole ship; one cell only says
    # which dominoes are still possible.
    required: list[tuple[str, int]] = []
    singles: dict[str, int] = {}
    for colour, cells in two_cells.items():
        if len(cells) == 1:
            singles[colour] = cells[0]
            continue
        if len(cells) > 2:
            return _empty_marginals(fleet)
        mask = _mask_of(cells)
        if mask not in _DOMINO_SET:
            return _empty_marginals(fleet)
        required.append((colour, mask))

    required_mask = 0
    for _, mask in required:
        if required_mask & mask:
            return _empty_marginals(fleet)
        required_mask |= mask
    forced &= ~required_mask

    count = fleet.two_ships - len(required)
    if count < 0:
        return _empty_marginals(fleet)

    # A fixed-length ship can never sit on a blue, on a known length-2 cell, or
    # on a cell already revealed as a different fixed colour.
    two_mask = forced | required_mask
    banned = {
        colour: blue_mask
        | two_mask
        | _mask_of([c for other, cells in fixed_cells.items() if other != colour for c in cells])
        for colour in fixed_cells
    }
    options = {
        colour: [
            segment
            for segment in SEGMENTS[length]
            if not segment & banned[colour]
            and all(segment >> cell & 1 for cell in fixed_cells[colour])
        ]
        for colour, length in FIXED_SHIPS
    }

    total = 0
    blue = [0] * GRID_CELLS
    teal = [0] * GRID_CELLS
    green = [0] * GRID_CELLS
    yellow = [0] * GRID_CELLS
    two = [0] * GRID_CELLS
    pinned: dict[str, list[int]] = {colour: [0] * GRID_CELLS for colour in two_cells}

    for teal_mask in options["T"]:
        for green_mask in options["G"]:
            if teal_mask & green_mask:
                continue
            teal_green = teal_mask | green_mask
            for yellow_mask in options["Y"]:
                if yellow_mask & teal_green:
                    continue
                base = teal_green | yellow_mask
                free = _FULL_MASK & ~(base | blue_mask)
                if required_mask & ~free:
                    continue
                region = free & ~required_mask
                matches = _packings(region, count, forced)
                if not matches:
                    continue
                total += matches

                for mask, counts in (
                    (teal_mask, teal),
                    (green_mask, green),
                    (yellow_mask, yellow),
                    (blue_mask, blue),
                ):
                    rest = mask
                    while rest:
                        bit = rest & -rest
                        counts[bit.bit_length() - 1] += matches
                        rest ^= bit

                rest = region
                while rest:
                    bit = rest & -rest
                    cell = bit.bit_length() - 1
                    uncovered = _packings(region & ~bit, count, forced)
                    blue[cell] += uncovered
                    two[cell] += matches - uncovered
                    rest ^= bit

                for colour, mask in required:
                    rest = mask
                    while rest:
                        bit = rest & -rest
                        cell = bit.bit_length() - 1
                        two[cell] += matches
                        pinned[colour][cell] += matches
                        rest ^= bit

                for colour, seen_cell in singles.items():
                    for domino in _DOMINOES_AT[seen_cell]:
                        if domino & region != domino:
                            continue
                        uses = _packings(
                            region & ~domino, count - 1, forced & ~domino
                        )
                        if not uses:
                            continue
                        rest = domino
                        while rest:
                            bit = rest & -rest
                            pinned[colour][bit.bit_length() - 1] += uses
                            rest ^= bit

    if not total:
        return _empty_marginals(fleet)

    return OtMarginals(
        fleet=fleet,
        total=total,
        blue=tuple(blue),
        teal=tuple(teal),
        green=tuple(green),
        yellow=tuple(yellow),
        two=tuple(two),
        unknown_two_sp=expected_two_cell_sp(fleet, set(two_cells)),
        pinned={colour: tuple(counts) for colour, counts in pinned.items()},
    )


# --- Policy -----------------------------------------------------------------

# Probe rules, for when no cell is a certain ship. Which one ships is a
# measurement (`scripts/ot_bakeoff.py --sweep-risk`), not a judgement call —
# and the measurement reversed the obvious answer. On the 7 real boards plain
# greedy EV looks best (1043 SP); at 200 generated boards it is the *worst* of
# the family under both generators, because it walks into blue cells that a
# little caution would have avoided. Seven boards could not see that.
PROBE_POLICIES = ("greedy", "safe", "risk", "mixed", "lookahead")
DEFAULT_PROBE_POLICY = "risk"

# "mixed" adds an information term to the EV, the way $oq's shipped hunt scores
# `P(purple) + 0.1 x Gini`. The units are SP per bit.
MIXED_INFO_WEIGHT = 10.0

# What a wasted blue click costs beyond its own 10 SP — the ship cell it stops
# us reaching. `risk` scores `ev(c) - RISK_PENALTY_SP * P(blue at c)`, which is
# the whole family in one knob: 0 is `greedy` exactly, and a large enough
# penalty is `safe` exactly.
#
# 60 is deliberately at the *low* end of what scores well. Sweeping 200
# generated boards (`--sweep-risk`), every penalty from 30 up beats greedy, and
# the two generators then disagree about how much further to go: `uniform`
# plateaus from 60 (+30.6 SP, and nothing in the sweep reaches significance),
# while `sequential` keeps climbing all the way to 1000 (+86.3 SP, t=4.92).
# Caution is clearly right; how much is a property of the prior, not of the
# game. The real boards break the tie downward — at 90 and above, one logged
# board collapses from 667 SP to **40**, because the policy spends all four
# blues on the four safest-looking cells and never commits to a ship. 60 keeps
# the whole plateau under `uniform`, stays significant under `sequential`
# (+33.8, t=2.08), scores best on the two hand-played boards, and stays on the
# committing side of that cliff.
RISK_PENALTY_SP = 60.0

# One-ply lookahead re-derives marginals per (candidate, outcome), so it scores
# only the most promising candidates. Five outcomes x this many candidates is
# ~0.06s mid-game and a few seconds on the second click of the game.
LOOKAHEAD_TOP_K = 6


def _hidden_clickable(buttons: list[dict[str, Any]]) -> list[int]:
    out: list[int] = []
    for index, button in enumerate(sphere_buttons(buttons)):
        if index >= GRID_CELLS:
            break
        if not button.get("custom_id") or button.get("disabled"):
            continue
        out.append(index)
    return out


def _button_at(buttons: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    cells = sphere_buttons(buttons)
    if 0 <= index < len(cells):
        return cells[index]
    return None


def harvest_value(marginals: OtMarginals, cells: list[int]) -> float:
    """Total SP of the cells in ``cells`` that are certain ships.

    This is what a probe *unlocks*: everything it proves safe can then be taken
    for free, so it is the right terminal value for a lookahead.
    """
    return sum(marginals.ev(cell) for cell in cells if marginals.is_certain_ship(cell))


def _lookahead_score(
    fleet: OtFleet,
    observations: Mapping[int, str],
    marginals: OtMarginals,
    cell: int,
    hidden: list[int],
    blues_left: int,
) -> float:
    """Expected SP from clicking ``cell``, plus whatever that reveal unlocks.

    A blue that spends the last click ends the board, so it unlocks nothing —
    which is the whole reason a probe can be worth less than its own EV.
    """
    score = 0.0
    others = [index for index in hidden if index != cell]
    for outcome, probability in marginals.outcomes(cell):
        payout = marginals.outcome_sp(cell, outcome)
        if outcome == BLUE and blues_left <= 1 and not EXTRA_CHANCE:
            score += probability * payout
            continue
        after = dict(observations)
        after[cell] = outcome
        resolved = enumerate_ot(fleet, after)
        score += probability * (payout + harvest_value(resolved, others))
    return score


def choose_ot_cell(
    fleet: OtFleet,
    observations: Mapping[int, str],
    hidden: list[int],
    *,
    marginals: OtMarginals | None = None,
    policy: str = DEFAULT_PROBE_POLICY,
    blues_left: int = DEFAULT_CLICKS_BUDGET,
    risk_penalty: float = RISK_PENALTY_SP,
) -> int | None:
    """Index of the next cell to click, or ``None`` when there is nothing left."""
    if not hidden:
        return None
    marginals = marginals if marginals is not None else enumerate_ot(fleet, observations)
    if not marginals.total:
        # Observations do not match this fleet — most likely a misread colour
        # count. Stay deterministic rather than guessing at random.
        return hidden[0]

    # Certain ships are free SP and cannot end the game, so they always come
    # first; the ordering only matters because the board expires in 2 minutes.
    certain = [cell for cell in hidden if marginals.is_certain_ship(cell)]
    if certain:
        return max(certain, key=lambda cell: (marginals.ev(cell), -cell))

    if policy == "safe":
        return min(hidden, key=lambda cell: (marginals.p_blue(cell), -marginals.ev(cell), cell))
    if policy == "risk":
        return max(
            hidden,
            key=lambda cell: (
                marginals.ev(cell) - risk_penalty * marginals.p_blue(cell),
                -cell,
            ),
        )
    if policy == "mixed":
        return max(
            hidden,
            key=lambda cell: (
                marginals.ev(cell) + MIXED_INFO_WEIGHT * marginals.entropy(cell),
                -cell,
            ),
        )
    if policy == "lookahead":
        ranked = sorted(hidden, key=lambda cell: (-marginals.ev(cell), cell))
        shortlist = ranked[:LOOKAHEAD_TOP_K]
        return max(
            shortlist,
            key=lambda cell: (
                _lookahead_score(
                    fleet, observations, marginals, cell, hidden, blues_left
                ),
                -cell,
            ),
        )
    return max(hidden, key=lambda cell: (marginals.ev(cell), -cell))


def choose_ot_click(
    buttons: list[dict[str, Any]],
    observations: Mapping[int, str],
    *,
    fleet: OtFleet,
    blues_spent: int = 0,
    policy: str = DEFAULT_PROBE_POLICY,
    risk_penalty: float = RISK_PENALTY_SP,
    rng: Any | None = None,
) -> dict[str, Any] | None:
    """Pick the next button to click, or ``None`` when the game is over."""
    del rng  # picks are deterministic; kept for parity with the other solvers
    if not EXTRA_CHANCE and blues_spent >= fleet.clicks_budget:
        return None
    hidden = [index for index in _hidden_clickable(buttons) if index not in observations]
    cell = choose_ot_cell(
        fleet,
        observations,
        hidden,
        policy=policy,
        blues_left=max(0, fleet.clicks_budget - blues_spent),
        risk_penalty=risk_penalty,
    )
    if cell is None:
        return None
    return _button_at(buttons, cell)


def solver_stats(
    fleet: OtFleet,
    observations: Mapping[int, str],
    *,
    hidden: list[int] | None = None,
    policy: str = DEFAULT_PROBE_POLICY,
) -> dict[str, Any]:
    cells = (
        hidden
        if hidden is not None
        else [index for index in range(GRID_CELLS) if index not in observations]
    )
    marginals = enumerate_ot(fleet, observations)
    certain = [cell for cell in cells if marginals.is_certain_ship(cell)]
    best = choose_ot_cell(fleet, observations, cells, marginals=marginals, policy=policy)
    return {
        "configurations": marginals.total,
        "certain_ships": len(certain),
        "certain_sp": harvest_value(marginals, cells),
        "best_index": -1 if best is None else best,
        "best_ev": 0.0 if best is None else marginals.ev(best),
        "best_p_blue": 0.0 if best is None else marginals.p_blue(best),
        "phase": "harvest" if certain else "probe",
    }


def format_solver_stats(
    fleet: OtFleet,
    observations: Mapping[int, str],
    *,
    hidden: list[int] | None = None,
    policy: str = DEFAULT_PROBE_POLICY,
) -> str:
    stats = solver_stats(fleet, observations, hidden=hidden, policy=policy)
    if not stats["configurations"]:
        return "solver: no fleet placement matches observations"
    best = stats["best_index"]
    if best < 0:
        return f"solver: {stats['configurations']:,} placements"
    row, col = divmod(best, GRID_SIZE)
    return (
        f"solver: {stats['configurations']:,} placements · {stats['phase']}"
        f" · {stats['certain_ships']} certain ({stats['certain_sp']:.0f} sp)"
        f" · next ({row + 1},{col + 1})"
        f" pB={stats['best_p_blue']:.0%} ev={stats['best_ev']:.1f}"
    )
