"""Precomputed boards for the Mudae ``$oq`` (Orb Quest) minigame.

Each world is one placement of 4 purple spheres on the 5×5 grid (12,650 total).
Non-purple cells show the count of adjacent purples (0–4), matching Minesweeper
logic with purple as the mines you want to find.
"""

from __future__ import annotations

from itertools import combinations

GRID_SIZE = 5
GRID_CELLS = GRID_SIZE * GRID_SIZE

NEIGHBORS: tuple[frozenset[int], ...] = tuple(
    frozenset(
        (r + dr) * GRID_SIZE + (c + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if (dr or dc)
        and 0 <= r + dr < GRID_SIZE
        and 0 <= c + dc < GRID_SIZE
    )
    for r in range(GRID_SIZE)
    for c in range(GRID_SIZE)
)

ALL_WORLDS: tuple[tuple[int, int, int, int], ...] = ()
WORLD_OUTCOMES: tuple[tuple[int, ...], ...] = ()
# (cell_index, outcome + 1) -> world indices where that cell shows that outcome.
# Outcome -1 (purple) is stored as key offset 0.
CONSTRAINT: dict[tuple[int, int], tuple[int, ...]] = {}


def _build() -> None:
    global ALL_WORLDS, WORLD_OUTCOMES, CONSTRAINT
    if ALL_WORLDS:
        return

    worlds: list[tuple[int, int, int, int]] = []
    outcomes: list[tuple[int, ...]] = []
    constraint_lists: dict[tuple[int, int], list[int]] = {}

    for mines in combinations(range(GRID_CELLS), 4):
        mine_set = frozenset(mines)
        row: list[int] = []
        for cell in range(GRID_CELLS):
            if cell in mine_set:
                value = -1
            else:
                value = sum(1 for n in NEIGHBORS[cell] if n in mine_set)
            row.append(value)
        wi = len(worlds)
        worlds.append(mines)
        outcomes.append(tuple(row))
        for cell, value in enumerate(row):
            key = (cell, value + 1)
            constraint_lists.setdefault(key, []).append(wi)

    ALL_WORLDS = tuple(worlds)
    WORLD_OUTCOMES = tuple(outcomes)
    CONSTRAINT = {key: tuple(indices) for key, indices in constraint_lists.items()}


def ensure_built() -> None:
    _build()
