# Mudae Tooling — Development Guide (archived reference)

> **Archived** 24 Aug 2026 — moved from repo root to `docs/archive/`.
> This is **not** a shipping spec. Use it when implementing Colblitz-style
> solvers or calculators listed in [`docs/TODO.md`](../TODO.md) (**Colblitz
> tools vs this app**). The live comparison and unlock order live there; fold
> any port into `macro/*_solver.py`, not a parallel `mudae-tools/` tree.
>
> Source site: [colblitz.com/mudae](https://colblitz.com/mudae/). Work one
> section at a time when handing to an LLM (see §0 below).

A complete implementation reference for rebuilding the feature set found on
`colblitz.com/mudae`: four sphere-minigame solvers (`$oh`, `$oc`, `$oq`, `$ot`),
four calculators (p9, bw, sp, dl), and a live Discord-driven solver.

Everything here is either (a) derived from first principles, (b) transcribed from
publicly documented formulas on the tool pages themselves, or (c) explicitly flagged
as **UNVERIFIED** — a constant or rule you must confirm empirically before trusting it.

Target language is Python 3.11+ (matches the existing FinalMacro stack). Nothing here
needs a GPU, a framework, or a server; every solver runs in milliseconds-to-seconds on
a laptop once its precomputation is cached.

---

## 0. How to use this document

### If you're implementing it yourself

Work top-down. Sections 1–5 (shared foundations + the four solvers) are the interesting
part and are mutually independent after Section 1. Sections 6–9 (calculators) are pure
arithmetic transcription and can be done in an afternoon each. Section 10 (live solver)
depends on everything else and should be last.

### If you're handing modules to an LLM

Each solver section is self-contained and written to be pasteable as a spec. The
recommended prompt shape:

> Implement the module described below as a single Python file. Follow the state
> representation and function signatures exactly. Where the spec says UNVERIFIED, read
> the value from `constants.py` rather than hardcoding it. Include the unit tests
> described in the "Validation" subsection.
>
> [paste one section]

Do **not** paste the whole document at once — it's long enough that the model will start
paraphrasing instead of implementing. One section per task.

### Confidence key

| Marker | Meaning |
|---|---|
| ✅ **CONFIRMED** | Publicly documented on the tool page, or provable from first principles |
| ⚠️ **UNVERIFIED** | My reconstruction from secondhand descriptions — validate before shipping |
| 🔬 **MEASURE** | A constant nobody publishes; you must collect data to fill it in |

---

## 1. Shared foundations

### 1.1 Repository layout

```
mudae-tools/
├── constants.py          # every game constant in one place, incl. TODO markers
├── grid.py               # coordinate helpers shared by all four solvers
├── solvers/
│   ├── __init__.py
│   ├── harvest.py        # $oh — Bellman DP over aggregate counts
│   ├── chest.py          # $oc — Bayesian inference over 24 red positions
│   ├── quest.py          # $oq — exact arrangement enumeration + scoring
│   └── trace.py          # $ot — constrained ship-placement enumeration
├── calculators/
│   ├── p9.py             # click/skip threshold DP
│   ├── bw.py             # keys-per-hour vs $bw curve
│   ├── sp.py             # sphere income model + upgrade ordering
│   └── dl.py             # disablelist set-cover ILP
├── sim/
│   ├── generators.py     # board generators for each game (ground truth)
│   ├── evaluate.py       # Monte Carlo policy evaluation harness
│   └── collect.py        # data-collection scripts for 🔬 MEASURE constants
├── live/
│   ├── parser.py         # Discord message → board state
│   ├── session.py        # per-user game state machine
│   └── server.py         # websocket push to browser
└── tests/
```

### 1.2 Coordinate convention

All four games are 5×5 grids. Use a single flat index `0..24`, row-major:

```
 0  1  2  3  4
 5  6  7  8  9
10 11 12 13 14
15 16 17 18 19
20 21 22 23 24
```

Index 12 is the centre. Convert to Discord's display coordinates (columns 1–5, rows
top-to-bottom) only at the UI boundary — never in solver logic.

`grid.py`:

```python
"""Shared 5x5 grid helpers. Flat index 0..24, row-major."""

N = 5
CELLS = tuple(range(N * N))
CENTRE = 12


def rc(i: int) -> tuple[int, int]:
    """Flat index -> (row, col)."""
    return divmod(i, N)


def idx(r: int, c: int) -> int:
    """(row, col) -> flat index."""
    return r * N + c


def in_bounds(r: int, c: int) -> bool:
    return 0 <= r < N and 0 <= c < N


def neighbours8(i: int) -> tuple[int, ...]:
    """The up-to-8 surrounding cells (King moves)."""
    r, c = rc(i)
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if in_bounds(nr, nc):
                out.append(idx(nr, nc))
    return tuple(out)


def same_line(i: int) -> tuple[int, ...]:
    """Cells sharing a row or column with i, excluding i itself."""
    r, c = rc(i)
    return tuple(
        j for j in CELLS
        if j != i and (rc(j)[0] == r or rc(j)[1] == c)
    )


def same_diagonal(i: int) -> tuple[int, ...]:
    """Cells on either 45-degree diagonal through i, excluding i itself."""
    r, c = rc(i)
    return tuple(
        j for j in CELLS
        if j != i and abs(rc(j)[0] - r) == abs(rc(j)[1] - c)
    )


# Precompute — these are hot paths in every solver.
NEIGHBOURS8 = tuple(neighbours8(i) for i in CELLS)
SAME_LINE = tuple(same_line(i) for i in CELLS)
SAME_DIAGONAL = tuple(same_diagonal(i) for i in CELLS)
NEIGHBOUR_MASK = tuple(
    sum(1 << j for j in NEIGHBOURS8[i]) for i in CELLS
)
```

### 1.3 The one architectural decision that matters

Every one of these solvers has the same shape:

1. **Belief** — the set of board configurations still consistent with what you've revealed.
2. **Evaluation** — for each candidate click, average the outcome over that belief.
3. **Lookahead** — recurse, because a click also changes the belief for future clicks.

Whether you can afford exact step 3 depends entirely on how big the belief space is:

| Game | Belief space | Exact DP feasible? |
|---|---|---|
| `$oq` Quest | 12,650 arrangements | Yes, with depth limits |
| `$oc` Chest | 24 red positions × board variants | Yes, trivially |
| `$oh` Harvest | Aggregate counts, not positions | Yes — state space is tiny |
| `$ot` Trace | 10⁵–10⁷ ship placements | Only with heavy pruning |

Design each solver so the **belief representation is a separate object** from the policy.
That lets you swap a greedy policy for a DP policy without touching the inference code,
and it's what makes the evaluation harness in §11 possible.

### 1.4 `constants.py` skeleton

```python
"""
All game constants. Values marked MEASURE are placeholders — fill them from
logged games (see sim/collect.py) before trusting any solver output.
"""

# ---------- $oh Harvest ----------------------------------------------------
HARVEST_CLICKS = 5              # CONFIRMED
HARVEST_PURPLE_SP = 5           # CONFIRMED — free action, no click cost
HARVEST_BLUE_SP = 10            # CONFIRMED — then reveals 3 covered cells
HARVEST_BLUE_REVEALS = 3        # CONFIRMED
HARVEST_TEAL_SP = 20            # CONFIRMED — then reveals 1 covered cell
HARVEST_TEAL_REVEALS = 1        # CONFIRMED
HARVEST_DARK_OUTCOMES = 9       # CONFIRMED — count only; distribution is MEASURE

# MEASURE: probability a freshly revealed covered cell is each type.
# Must sum to 1.0. Categories: purple / blue / teal / dark / flat_<value>.
HARVEST_REVEAL_DIST = {
    "purple": 0.10,
    "blue": 0.20,
    "teal": 0.15,
    "dark": 0.05,
    "flat_30": 0.20,
    "flat_55": 0.20,
    "flat_90": 0.10,
}

# MEASURE: chance that clicking a still-covered cell grants a bonus $oc instead
# of resolving to a sphere colour.
HARVEST_COVERED_OC_CHANCE = 0.02
HARVEST_OC_EV = 400.0           # MEASURE — expected SP of a bonus $oc

# ---------- $oc Chest ------------------------------------------------------
CHEST_CLICKS = 5                # CONFIRMED
CHEST_RED_SP = 150              # CONFIRMED
CHEST_RED_POSITIONS = 24        # CONFIRMED — centre cell is fixed, never red
# MEASURE: SP value of each hint colour when clicked.
CHEST_COLOUR_SP = {
    "red": 150,
    "orange": 0,    # MEASURE
    "yellow": 0,    # MEASURE
    "green": 0,     # MEASURE
    "teal": 0,      # MEASURE
    "blue": 0,      # MEASURE
}

# ---------- $oq Quest ------------------------------------------------------
QUEST_CLICKS = 7                # CONFIRMED
QUEST_PURPLES = 4               # CONFIRMED
QUEST_ARRANGEMENTS = 12650      # CONFIRMED — C(25,4)
QUEST_RED_SP = 150              # CONFIRMED — the 4th purple becomes red
QUEST_THEORETICAL_MAX = 381.9   # CONFIRMED — published avg upper bound
# MEASURE: SP for clicking a non-purple cell, keyed by its neighbour count.
QUEST_COLOUR_SP = {
    0: 20,   # blue   — MEASURE, ~20-55 range is documented
    1: 30,   # teal   — MEASURE
    2: 40,   # green  — MEASURE
    3: 50,   # yellow — MEASURE
    4: 55,   # orange — MEASURE
}
QUEST_PURPLE_SP = 0             # MEASURE — purple clicks are free; SP value unclear

# ---------- $ot Trace ------------------------------------------------------
TRACE_BLUE_BUDGET = 4           # CONFIRMED
TRACE_GRACE_SHIPS = 5           # CONFIRMED — Extra Chance ends at 5 ship hits
TRACE_BLUE_SP = 10              # CONFIRMED (per cell)
# (length, sp_per_cell) — CONFIRMED from the tool page
TRACE_SHIPS = {
    "teal":   (4, 20),
    "green":  (3, 35),
    "yellow": (3, 55),
    "orange": (2, 90),
}
TRACE_RARE = (2, 90)            # CONFIRMED — length 2, ~90 sp/cell
TRACE_RARE_COUNT = {6: 0, 7: 1, 8: 2, 9: 3}   # CONFIRMED, keyed by colour count

# ---------- Perk 9 ---------------------------------------------------------
# MEASURE: colour frequency + base SP for perk-9 sphere buttons.
# colblitz derived theirs from 55,249 observed rolls; you need your own sample.
P9_COLOURS = [
    # (name, base_sp, frequency)
    ("blue", 10, 0.30),
    ("teal", 20, 0.25),
    ("green", 35, 0.20),
    ("yellow", 55, 0.15),
    ("orange", 90, 0.08),
    ("red", 150, 0.02),
]
P9_BASE_CLICKS = 10             # CONFIRMED — daily cap is 10 + SP9 level
```

Everything downstream imports from here. Resist the urge to inline a number "just for
now" — the `MEASURE` values are the single biggest source of wrong answers in this whole
project, and you want exactly one place to fix them.

---

## 2. `$oh` Harvest — Bellman DP over aggregate counts

**Goal:** 5 clicks, maximise total SP. Purple is free and never costs a click.

**Best available approach:** exact backward-induction DP. This is the one game where the
optimal policy is genuinely cheap to compute, because *position doesn't matter* — only
how many buttons of each type are visible.

### 2.1 Rules ✅ CONFIRMED

The board starts fully covered. Buttons resolve as follows:

| Button | Effect | Click cost |
|---|---|---|
| Purple | +5 SP | **free** |
| Blue | +10 SP, then reveals 3 covered cells | 1 |
| Teal | +20 SP, then reveals 1 covered cell | 1 |
| Dark | Transforms into a random sphere type (9 outcomes) | 1 |
| Flat colour | Its face value, deterministic; cell is consumed | 1 |
| Still-covered | Small chance of granting a bonus `$oc`, otherwise resolves to a random colour | 1 |

⚠️ **UNVERIFIED — resolve this first.** When you click a dark cell, does the click
*also* collect the resulting sphere (i.e. dark behaves as "roll a random button and fire
it"), or does the cell merely transform, leaving you to spend a second click on it? The
DP below implements the first reading behind a flag `DARK_RESOLVES_IMMEDIATELY = True`.
Ten manual games will settle it.

### 2.2 State representation

The key insight: **positions are irrelevant in harvest.** Blue reveals "3 covered cells"
— any 3, uniformly — so two boards with the same counts are strategically identical.

```
state = (k, n_cov, n_blue, n_teal, n_dark, flats)
```

- `k` — clicks remaining (0..5)
- `n_cov` — covered cells remaining
- `n_blue`, `n_teal`, `n_dark` — visible buttons of each type
- `flats` — sorted-descending tuple of visible flat values, **truncated to length k**

That truncation is the second insight. Flat buttons are deterministic and interact with
nothing: if you're ever going to click flats, you click the highest-value ones. So with
`k` clicks left, flats beyond the top `k` can never be optimal and are dropped from the
state. This collapses an unbounded state component into at most 5 values and is what
makes the table small enough to enumerate exhaustively.

Reachable state count is in the low tens of thousands. `functools.cache` is sufficient;
you do not need a hand-rolled table.

### 2.3 The recursion

```
V(k, state) = max over available actions a of Q(a)

V(0, ·) = 0

Q(flat v)  = v + V(k-1, state - that flat)
Q(blue)    = 10 + E_reveals[ V(k-1, state') ]     # 3 draws from covered
Q(teal)    = 20 + E_reveals[ V(k-1, state') ]     # 1 draw from covered
Q(dark)    = E_type[ Q(that type at k) ]          # if resolving immediately
Q(covered) = p_oc * (EV_oc + V(k-1, state - 1 covered))
           + (1-p_oc) * E_type[ resolve as that type ]
```

Purple never appears as an action: whenever a reveal produces purple, add +5 to the
running value and don't decrement `k`. Free actions fold into the transition, not the
action set.

### 2.4 Reference implementation

```python
"""solvers/harvest.py — exact Bellman DP for the $oh minigame."""

from functools import cache
from itertools import combinations_with_replacement
from math import factorial

import constants as C

DARK_RESOLVES_IMMEDIATELY = True   # UNVERIFIED — see 2.1

# Reveal categories, normalised once at import.
_DIST = dict(C.HARVEST_REVEAL_DIST)
_TOTAL = sum(_DIST.values())
_DIST = {k: v / _TOTAL for k, v in _DIST.items()}
_CATS = tuple(_DIST.keys())
_PROBS = tuple(_DIST[c] for c in _CATS)


def _flat_value(cat: str) -> int | None:
    """'flat_55' -> 55; anything else -> None."""
    return int(cat.split("_")[1]) if cat.startswith("flat_") else None


def _multinomial_outcomes(n: int):
    """
    Yield (counts_per_category, probability) for n independent draws.
    n is 1 or 3 in practice, so the combinatorics are trivial.
    """
    for combo in combinations_with_replacement(range(len(_CATS)), n):
        counts = [0] * len(_CATS)
        for i in combo:
            counts[i] += 1
        coeff = factorial(n)
        prob = 1.0
        for ci, cnt in enumerate(counts):
            coeff //= factorial(cnt)
            prob *= _PROBS[ci] ** cnt
        yield tuple(counts), coeff * prob


def _apply_reveals(state, counts):
    """
    Apply a multinomial reveal outcome to a state.
    Returns (new_state, free_sp) where free_sp is purple income.
    """
    k, n_cov, n_blue, n_teal, n_dark, flats = state
    revealed = sum(counts)
    n_cov -= revealed
    free_sp = 0
    flats = list(flats)
    for ci, cnt in enumerate(counts):
        if cnt == 0:
            continue
        cat = _CATS[ci]
        if cat == "purple":
            free_sp += cnt * C.HARVEST_PURPLE_SP
        elif cat == "blue":
            n_blue += cnt
        elif cat == "teal":
            n_teal += cnt
        elif cat == "dark":
            n_dark += cnt
        else:
            flats.extend([_flat_value(cat)] * cnt)
    flats.sort(reverse=True)
    return (k, n_cov, n_blue, n_teal, n_dark, tuple(flats[:k])), free_sp


def _trim(state):
    """Re-truncate the flat list after k changes."""
    k, n_cov, n_blue, n_teal, n_dark, flats = state
    return (k, n_cov, n_blue, n_teal, n_dark, tuple(flats[:k]))


@cache
def value(state) -> float:
    """Expected SP from this state under optimal play."""
    return max((q for _, q in actions(state)), default=0.0)


@cache
def actions(state) -> tuple[tuple[str, float], ...]:
    """[(action_name, expected_value), ...] sorted best-first."""
    k, n_cov, n_blue, n_teal, n_dark, flats = state
    if k == 0:
        return ()
    out = []

    # --- flat: only the best one is ever worth considering ---
    if flats:
        rest = _trim((k - 1, n_cov, n_blue, n_teal, n_dark, flats[1:]))
        out.append((f"flat:{flats[0]}", flats[0] + value(rest)))

    # --- blue: +10 then 3 reveals ---
    if n_blue:
        out.append(("blue", C.HARVEST_BLUE_SP + _reveal_ev(
            (k - 1, n_cov, n_blue - 1, n_teal, n_dark, flats),
            C.HARVEST_BLUE_REVEALS,
        )))

    # --- teal: +20 then 1 reveal ---
    if n_teal:
        out.append(("teal", C.HARVEST_TEAL_SP + _reveal_ev(
            (k - 1, n_cov, n_blue, n_teal - 1, n_dark, flats),
            C.HARVEST_TEAL_REVEALS,
        )))

    # --- dark: becomes a random type ---
    if n_dark:
        base = (k, n_cov, n_blue, n_teal, n_dark - 1, flats)
        ev = 0.0
        for cat, p in zip(_CATS, _PROBS):
            ev += p * _resolve_as(base, cat)
        out.append(("dark", ev))

    # --- covered: gamble ---
    if n_cov:
        base = (k, n_cov - 1, n_blue, n_teal, n_dark, flats)
        p_oc = C.HARVEST_COVERED_OC_CHANCE
        ev = p_oc * (C.HARVEST_OC_EV + value(_trim(
            (k - 1, n_cov - 1, n_blue, n_teal, n_dark, flats))))
        for cat, p in zip(_CATS, _PROBS):
            ev += (1 - p_oc) * p * _resolve_as(base, cat)
        out.append(("covered", ev))

    out.sort(key=lambda t: -t[1])
    return tuple(out)


def _reveal_ev(state_after_click, n_reveals: int) -> float:
    """Expected value after spending a click and triggering n reveals."""
    k, n_cov = state_after_click[0], state_after_click[1]
    n_reveals = min(n_reveals, n_cov)
    if n_reveals == 0:
        return value(_trim(state_after_click))
    ev = 0.0
    for counts, prob in _multinomial_outcomes(n_reveals):
        new_state, free_sp = _apply_reveals(state_after_click, counts)
        ev += prob * (free_sp + value(new_state))
    return ev


def _resolve_as(base_state, cat: str) -> float:
    """
    Value of a click that turns into `cat`. base_state already has the
    source cell removed and still has k clicks (the click is spent here).
    """
    k, n_cov, n_blue, n_teal, n_dark, flats = base_state
    if cat == "purple":
        # Free: keeps the click.
        return C.HARVEST_PURPLE_SP + value(_trim(base_state))
    if cat == "blue":
        return C.HARVEST_BLUE_SP + _reveal_ev(
            (k - 1, n_cov, n_blue, n_teal, n_dark, flats),
            C.HARVEST_BLUE_REVEALS)
    if cat == "teal":
        return C.HARVEST_TEAL_SP + _reveal_ev(
            (k - 1, n_cov, n_blue, n_teal, n_dark, flats),
            C.HARVEST_TEAL_REVEALS)
    if cat == "dark":
        if not DARK_RESOLVES_IMMEDIATELY:
            return value(_trim((k - 1, n_cov, n_blue, n_teal, n_dark + 1, flats)))
        ev = 0.0
        for c2, p2 in zip(_CATS, _PROBS):
            if c2 == "dark":
                continue        # avoid infinite regress; renormalise below
            ev += p2 * _resolve_as(base_state, c2)
        return ev / (1 - _DIST["dark"])
    v = _flat_value(cat)
    return v + value(_trim((k - 1, n_cov, n_blue, n_teal, n_dark, flats)))


def recommend(state) -> tuple[str, float]:
    """Public entry point: best action and its EV."""
    acts = actions(_trim(state))
    return acts[0] if acts else ("none", 0.0)
```

### 2.5 UI behaviour

The tool page describes an interaction worth copying exactly, because it's the part users
get wrong:

- Grid starts fully covered (`?`).
- The user sets each cell's colour as it's revealed in Discord.
- **Purple is always clicked immediately and is never counted** against the budget. Make
  this impossible to get wrong in the UI — auto-consume purple on entry rather than
  trusting the user to remember.
- A "Record a click" control decrements the counter separately from updating the grid,
  because in Discord those are two different moments.
- Cells that were clicked and consumed get marked `Clicked` and drop out of the DP state
  entirely (right-click as a shortcut).

### 2.6 Validation

1. **Degenerate check:** with `k=1` and only flats visible, the recommendation must be
   the largest flat, and `value` must equal it exactly.
2. **Monotonicity:** `value(k+1, s) >= value(k, s)` for every state. An extra click can
   never hurt.
3. **Purple never costs:** construct a state, add a purple reveal, confirm `k` is
   unchanged and value rose by exactly 5.
4. **Monte Carlo agreement:** run 100k simulated games under the DP policy (see §11) and
   confirm the empirical mean matches `value(initial_state)` to within sampling error.
   If it doesn't, your simulator and your DP disagree about the rules — and one of them
   is what the Discord bot actually does.

---

## 3. `$oc` Chest — Bayesian inference over 24 red positions

**Goal:** 5 clicks, find the red sphere (150 SP) while maximising total SP.

**Best available approach:** exact posterior over red positions, then Bellman DP.
The belief space is tiny (24 hypotheses), so full lookahead is cheap. The *hard* part
isn't the algorithm — it's pinning down the board generator.

### 3.1 Rules ✅ CONFIRMED

- 5×5 grid, one hidden red sphere. The **centre cell is fixed** and is never red, leaving
  **24 possible red positions**.
- Every other cell's colour encodes its geometric relationship to the red sphere.
- 5 clicks. Red pays 150 SP; other colours pay less but every click has value.

### 3.2 The colour semantics ⚠️ UNVERIFIED

Two independent third-party solvers describe the colour scheme, and they don't quite
agree. Reconciling them gives:

| Colour | Meaning relative to red |
|---|---|
| Red | The target itself |
| Orange | Adjacent (King-move neighbour) |
| Yellow | On a diagonal through red |
| Green | In the same row or column as red |
| Teal | On a line/diagonal through red, but not selected as orange/yellow/green |
| Blue | Not on any line or diagonal through red |

And one solver states fixed counts: **2 orange, 3 yellow, 4 green**, with teal filling
the remaining lines and diagonals.

**Why this can't be the whole story.** If yellow is drawn from diagonal cells *after*
removing orange cells, some red positions have too few diagonal cells left to pick 3.
Example: red at index 6 (row 1, col 1) has 6 diagonal cells, four of which are also
adjacent — if both oranges land on diagonals you can still pick 3, but the constraint is
tight and for some positions it breaks. So either the precedence differs, the counts vary
by position, or orange/yellow/green are drawn from overlapping pools independently.

**Do not guess this.** Play 30–50 games, log every full board, and fit the generator.
Specifically record: red position, and the exact set of cells of each colour. Then check
whether the counts (2/3/4) hold universally and what pool each is drawn from.

### 3.3 The architecture that survives being wrong

Because the generator is uncertain, **isolate it behind one function** and make
everything else generator-agnostic:

```python
def enumerate_boards(red: int) -> list[dict[int, str]]:
    """
    Return every board consistent with the red sphere at `red`.
    Each board maps cell index -> colour name.
    This is the ONLY function that encodes the generator's rules.
    """
```

If you later discover the rules differ, you rewrite this one function and every solver,
heatmap, and EV number downstream updates for free. Cache the output — it's constant.

**Fallback if the generator stays unknown.** You can still build a working solver from a
purely empirical likelihood model: estimate `P(colour at cell j | red at position i)`
directly from logged games, and do naive Bayes over the 24 hypotheses. This ignores the
fixed-count correlations so it's slightly less sharp, but it needs no rule reconstruction
at all and it degrades gracefully. Implement this first if you want something working
today; upgrade to exact enumeration once the generator is confirmed.

### 3.4 The weighting subtlety that most solvers get wrong ✅ CONFIRMED

Different red positions admit different numbers of consistent boards. A corner red has
few adjacent/diagonal/line cells and therefore few board variants; a central red has many.

If you sample uniformly over *boards*, you implicitly assume central reds are more likely
— which is wrong. **Each of the 24 red positions is equally likely.** The correct weight
of a single board `b` with red at `i` is:

```
w(b) = (1/24) * (1 / |boards(i)|)
```

The tool page exposes both counts side by side (raw vs. weighted) precisely so you can
see how skewed a branch is. Compute posteriors on the *weighted* count, always.

```python
def posterior(revealed: dict[int, str]) -> dict[int, float]:
    """P(red at i | revealed cells), correctly weighted."""
    scores = {}
    for i in RED_POSITIONS:                    # the 24 non-centre cells
        boards = enumerate_boards(i)
        consistent = sum(
            1 for b in boards
            if all(b[cell] == col for cell, col in revealed.items())
        )
        if consistent:
            # (1/24) cancels in normalisation; keep the 1/|boards(i)| term.
            scores[i] = consistent / len(boards)
    total = sum(scores.values())
    return {i: s / total for i, s in scores.items()}
```

### 3.5 The Bellman DP ✅ CONFIRMED

Published verbatim on the tool page:

```
EV(state, k) = max over cells c of:
    Σ_x  P(colour at c = x | state) × ( value(x) + EV(state + reveal(c=x), k−1) )
```

In words: for each candidate cell, consider every colour it could turn out to be; for
each outcome, add that colour's SP to the best achievable future SP from the resulting
state; pick the cell maximising the weighted average.

```python
from functools import lru_cache
import constants as C


@lru_cache(maxsize=None)
def ev(revealed_key: tuple, k: int) -> tuple[float, int | None]:
    """
    Returns (expected_sp, best_cell). `revealed_key` is a sorted tuple of
    (cell, colour) pairs so it hashes.
    """
    if k == 0:
        return 0.0, None
    revealed = dict(revealed_key)
    post = posterior(revealed)
    best_val, best_cell = -1.0, None

    for c in CELLS:
        if c in revealed or c == CENTRE:
            continue
        # Distribution of colours at c under the current posterior.
        dist = colour_distribution(c, post)
        total = 0.0
        for colour, p in dist.items():
            if p <= 0:
                continue
            child = tuple(sorted(list(revealed_key) + [(c, colour)]))
            future, _ = ev(child, k - 1)
            total += p * (C.CHEST_COLOUR_SP[colour] + future)
        if total > best_val:
            best_val, best_cell = total, c

    return best_val, best_cell
```

`colour_distribution(c, post)` marginalises: for each red hypothesis `i` weighted by
`post[i]`, what fraction of `i`'s consistent boards show each colour at `c`.

Branching is 24 cells × ~6 colours × 5 plies. That's large but the posterior collapses
fast (most colour outcomes are impossible given the state), so real-world node counts are
small. Memoise on the revealed set and it's instant after the first call.

### 3.6 Why the solver won't always click the highest red-probability cell ✅ CONFIRMED

Worth putting in your UI as a help text, because users will ask:

- Every click has value regardless of colour. A cell with 5% red probability but heavy
  orange/yellow weighting can beat an 8%-red cell that's mostly teal when it misses.
- Early clicks buy **information**. A cell that resolves more uncertainty can unlock
  better clicks 3–5 even at slightly lower immediate EV — and the DP captures this
  automatically, since each cell's value already includes the best achievable future.
- Once red is found, there's no benefit to finding it again; weighting naturally shifts
  to the high-value non-red colours.

A "show red candidate positions" overlay (border every unrevealed cell that could still
be red on at least one consistent board) is genuinely useful, but make it clear it's a
*possibility* marker, not a recommendation.

### 3.7 Validation

1. `sum(posterior(...).values()) == 1.0` for every reachable state.
2. Revealing a real board's colours one at a time must never drive the true red position's
   posterior to zero. This is the single best test — run it over thousands of generated
   boards and it catches every generator/inference mismatch.
3. `ev({}, 5)` should be reproducible and stable across runs.
4. Monte Carlo: DP policy should beat a "highest red probability" greedy policy on average
   SP. If it doesn't, your value table is wrong.

---

## 4. `$oq` Quest — exact arrangement enumeration

**Goal:** 7 clicks, reveal purple spheres. The 4th purple becomes **red** (150 SP).

**Best available approach:** exhaustive enumeration of all 12,650 arrangements, filtered
by every reveal, scored by `α·P(purple) + β·Gini`. This is fully specified, cheap, and
hits ~95% success. A depth-limited expectimax on top pushes it to ~98%.

This is the cleanest of the four games — no unknown generator, no unknown probabilities.
If you implement one solver, make it this one.

### 4.1 Rules ✅ CONFIRMED

- 5×5 grid, **4 hidden purples**, placed uniformly at random. `C(25,4) = 12,650` equally
  likely arrangements.
- Clicking a non-purple cell reveals a colour encoding **how many of its up-to-8
  neighbours are purple**:

| Colour | Purple neighbours |
|---|---|
| Blue | 0 |
| Teal | 1 |
| Green | 2 |
| Yellow | 3 |
| Orange | 4 |

- **Purple clicks are free.** The 4th purple transforms into a red sphere worth 150 SP and
  *does* cost a click.
- 7 clicks total. Published benchmark: theoretical max 381.9 avg SP.

It's Minesweeper with a bounded click budget and a jackpot tile.

### 4.2 Belief representation

```python
from itertools import combinations
from grid import CELLS, NEIGHBOURS8

ALL_ARRANGEMENTS = [
    frozenset(c) for c in combinations(CELLS, 4)
]   # 12,650 — precompute once at import, ~1 MB
```

A reveal at cell `c` showing `n` purple neighbours filters:

```python
def filter_arrangements(arrangements, cell, n_neighbours):
    """Keep only arrangements consistent with this reveal."""
    nb = NEIGHBOURS8[cell]
    return [
        a for a in arrangements
        if cell not in a and sum(1 for x in nb if x in a) == n_neighbours
    ]
```

Filtering 12,650 sets is sub-millisecond. Do not optimise this prematurely — but if you
want it fast anyway, represent arrangements as 25-bit ints and use
`popcount(arrangement & NEIGHBOUR_MASK[cell])`, which is ~20× quicker.

`P(purple at j)` is then exact counting, no estimation:

```python
def purple_probs(arrangements) -> dict[int, float]:
    total = len(arrangements)
    counts = dict.fromkeys(CELLS, 0)
    for a in arrangements:
        for cell in a:
            counts[cell] += 1
    return {c: counts[c] / total for c in CELLS}
```

On an empty board every cell sits at 4/25 = 16%. After a few reveals cells snap toward
0% or 100%.

### 4.3 The MIXED scorer ✅ CONFIRMED

Published parameters: **α = 1.0, β = 0.1**.

```
score(cell) = α · P(purple at cell) + β · Gini(cell)
Gini(cell)  = 1 − Σ_outcome P(outcome)²
```

Gini impurity measures how *informative* a reveal is. If a cell is almost certainly going
to show blue, its reveal teaches you nothing (Gini ≈ 0). If it could plausibly show any of
five colours, whatever it shows eliminates a lot of arrangements (Gini ≈ 1).

The tiny β weight means Gini acts purely as a **tie-breaker** among cells with near-equal
purple probability. Its main effect is on the opening move: on an empty board every cell
has identical P(purple), so Gini is what correctly pushes you toward centre cells, which
have 8 neighbours and therefore far more discriminating reveals than corners with 3.

That single change is most of the gap between the published 81% (pure P(purple)) and 95%
(MIXED) success rates.

```python
import constants as C

ALPHA, BETA = 1.0, 0.1


def outcome_distribution(arrangements, cell) -> dict:
    """P(each outcome) at `cell`: 'purple', or a neighbour count 0..4."""
    total = len(arrangements)
    dist = {}
    nb = NEIGHBOURS8[cell]
    for a in arrangements:
        if cell in a:
            key = "purple"
        else:
            key = sum(1 for x in nb if x in a)
        dist[key] = dist.get(key, 0) + 1
    return {k: v / total for k, v in dist.items()}


def gini(dist: dict) -> float:
    return 1.0 - sum(p * p for p in dist.values())


def recommend(arrangements, revealed: set[int]) -> int:
    best, best_score = None, -1.0
    for cell in CELLS:
        if cell in revealed:
            continue
        dist = outcome_distribution(arrangements, cell)
        p_purple = dist.get("purple", 0.0)
        score = ALPHA * p_purple + BETA * gini(dist)
        if score > best_score:
            best, best_score = cell, score
    return best
```

### 4.4 Published strategy benchmarks ✅ CONFIRMED

Reproduce these numbers with your own simulator — they're the best regression test you'll
get for the whole project.

| Strategy | Avg SP | Success | Efficiency |
|---|---|---|---|
| Random | 174.5 | 11.5% | 45.7% |
| Mean field | 190.3 | 24.2% | 49.8% |
| Constraint propagation | 280.5 | 69.9% | 73.4% |
| Exact P(purple) | 296.8 | 81.1% | 77.7% |
| **MIXED α=1.0 β=0.1** | **342.7** | **95.4%** | **89.7%** |
| Bellman DP (v4) | 356.3 | 98.1% | 93.3% |
| Theoretical max | 381.9 | 100% | 100% |

Success = fraction of boards where the red sphere was clicked.
Efficiency = avg score ÷ theoretical max.

If your MIXED implementation lands within ~1% of 342.7 avg SP and 95% success over
100k games, it's correct.

### 4.5 Beating MIXED: depth-limited expectimax

The published DP gains ~14 SP over MIXED. Full Bellman DP over belief states is expensive
(the state is the surviving arrangement set), but you can capture most of the gain with
bounded lookahead and MIXED as the leaf evaluator:

```python
def expectimax(arrangements, revealed, clicks_left, purples_found, depth=2):
    """
    Returns (expected_sp, best_cell).
    At depth 0, fall back to MIXED's greedy choice as a leaf estimate.
    """
    if clicks_left == 0 or not arrangements:
        return 0.0, None
    if depth == 0:
        cell = recommend(arrangements, revealed)
        return leaf_estimate(arrangements, revealed, clicks_left), cell

    best, best_val = None, -1.0
    for cell in candidate_cells(arrangements, revealed, top_k=6):
        dist = outcome_distribution(arrangements, cell)
        total = 0.0
        for outcome, p in dist.items():
            if p <= 0:
                continue
            child = filter_by_outcome(arrangements, cell, outcome)
            if outcome == "purple":
                # Free click, unless it's the 4th (red).
                is_red = purples_found + 1 == C.QUEST_PURPLES
                sp = C.QUEST_RED_SP if is_red else C.QUEST_PURPLE_SP
                nk = clicks_left - 1 if is_red else clicks_left
                sub, _ = expectimax(child, revealed | {cell}, nk,
                                    purples_found + 1, depth - 1)
            else:
                sp = C.QUEST_COLOUR_SP[outcome]
                sub, _ = expectimax(child, revealed | {cell},
                                    clicks_left - 1, purples_found, depth - 1)
            total += p * (sp + sub)
        if total > best_val:
            best, best_val = cell, total
    return best_val, best
```

Two things make this tractable:

- **`candidate_cells(..., top_k=6)`** — only expand the 6 highest-MIXED-scoring cells
  rather than all 25. Branching drops from 25 to 6 with almost no quality loss.
- **`depth=2` or `3`** — beyond that, returns diminish sharply because the arrangement set
  collapses so fast that MIXED and DP agree anyway.

Measure it. If depth-2 expectimax doesn't beat MIXED by at least a few SP in your
harness, ship MIXED and move on — the complexity isn't worth it.

### 4.6 Recommended cell overlays

The tool page exposes four per-cell numbers. All are cheap given `outcome_distribution`,
and they make the solver debuggable by eye:

| Overlay | Meaning |
|---|---|
| **P%** | Chance of being purple. 16% everywhere initially; narrows fast. |
| **M** | The ranking value, `P + 0.1×Gini`. Highest M = recommendation. |
| **G** | Gini impurity. 0 = reveal is predictable; near 1 = highly informative. |
| **EV** | Expected SP from clicking, averaged over reveal colours. |

Also show "arrangements remaining" — it drops from 12,650 to single digits over a game
and is the single clearest signal that your filtering is working.

### 4.7 Validation

1. **Ground-truth survival:** generate a random arrangement, simulate reveals from it, and
   assert the true arrangement is always in the surviving set. Run 100k times. Any failure
   is a neighbour-counting bug.
2. **Opening probability:** on an empty board every cell must be exactly 4/25.
3. **Blue elimination:** after a blue reveal at cell `c`, `P(purple)` must be exactly 0
   for all 8 neighbours of `c`.
4. **Benchmark match:** reproduce the table in §4.4.

---

## 5. `$ot` Trace — constrained ship-placement enumeration

**Goal:** find ships (free) while spending at most 4 blue clicks. Battleship with a twist.

**Best available approach:** enumerate ship placements *consistent with reveals* via
bitmask DFS, then a two-phase policy. This is the hardest of the four and the one where
colblitz keeps the most hidden (their scorer is "learned" and the weights aren't
published). You will not exactly match their solver — but the phase structure and the
constraint engine are the bulk of the value, and both are reconstructable.

### 5.1 Rules ✅ CONFIRMED

Board is 5×5. Every cell belongs to exactly one ship, or is blue (empty). Ships are
horizontal or vertical contiguous segments with **no overlap**:

| Ship | Length | SP per cell | Present? |
|---|---|---|---|
| Teal | 4 | 20 | always |
| Green | 3 | 35 | always |
| Yellow | 3 | 55 | always |
| Orange | 2 | 90 | always |
| Rare | 2 | ~90 | 0 in 6-colour, 1 in 7, 2 in 8, 3 in 9 |
| Blue | — | 10 | all remaining cells |

**Click budget:** ship hits are **free**. Only hitting a blue cell costs budget, and you
have **4 blue clicks**.

**Extra Chance:** while you've hit fewer than **5 ship cells total**, each blue click
extends the game rather than ending it. Once you hit 5 ship cells, Extra Chance shuts off
and the next blue click ends the game immediately.

**Perfect game:** use constraint inference to locate all blue cells *before* hitting 5
ship cells, then collect every remaining ship cell for free.

That last line is the whole strategy in one sentence, and it's why the phase split exists.

### 5.2 Placement enumeration

Do **not** enumerate all boards then filter — the raw space is 10⁵–10⁷ depending on
colour count. Instead apply constraints *during* the DFS. Represent each placement as a
25-bit occupancy mask:

```python
"""solvers/trace.py — placement enumeration for $ot."""

from grid import N, CELLS, idx
import constants as C


def placements(length: int) -> list[int]:
    """All bitmasks for a ship of the given length, horizontal and vertical."""
    out = []
    for r in range(N):
        for c in range(N - length + 1):
            out.append(sum(1 << idx(r, c + k) for k in range(length)))
    for c in range(N):
        for r in range(N - length + 1):
            out.append(sum(1 << idx(r + k, c) for k in range(length)))
    return out


PLACEMENTS = {L: placements(L) for L in (2, 3, 4)}


def enumerate_boards(colour_count: int, constraints, limit=None):
    """
    Yield consistent boards as tuples of (ship_name, mask).

    `constraints` carries what's been revealed:
      - known_ship:  set of cells known to be part of SOME ship
      - known_blue:  set of cells known to be empty
      - known_colour: {cell: ship_name} where the exact ship is known
    """
    n_rare = C.TRACE_RARE_COUNT[colour_count]
    ships = [
        ("teal", 4), ("green", 3), ("yellow", 3), ("orange", 2),
    ] + [(f"rare{i}", 2) for i in range(n_rare)]

    blue_mask = sum(1 << c for c in constraints.known_blue)
    results = []

    def dfs(i, occupied, chosen):
        if limit is not None and len(results) >= limit:
            return
        if i == len(ships):
            # Every known-ship cell must be covered by some placement.
            for cell in constraints.known_ship:
                if not (occupied >> cell) & 1:
                    return
            results.append(tuple(chosen))
            return

        name, length = ships[i]
        for m in PLACEMENTS[length]:
            if m & occupied:            # overlap
                continue
            if m & blue_mask:           # covers a known-empty cell
                continue
            # Exact-colour constraints: this ship must cover cells assigned
            # to it, and must not cover cells assigned to a different ship.
            ok = True
            for cell, want in constraints.known_colour.items():
                covered = (m >> cell) & 1
                if want == name and not covered:
                    ok = False
                    break
                if want != name and covered:
                    ok = False
                    break
            if ok:
                dfs(i + 1, occupied | m, chosen + [(name, m)])

    dfs(0, 0, [])
    return results
```

**Performance notes.** Order the ships longest-first (done above) — the length-4 teal has
only 20 placements and prunes hardest. On an empty 9-colour board the count is large; if
the initial enumeration is too slow, either (a) cache the empty-board result to disk once,
or (b) pass `limit=50_000` and treat the result as a uniform sample, which is statistically
fine for EV estimates. After two or three reveals the space collapses to thousands and
exact enumeration is instant.

Rare ships are interchangeable in shape but not in identity, so `rare0`/`rare1`/`rare2`
produce permutation-equivalent boards. Deduplicate by sorting rare masks before storing,
unless you specifically need to identify *which* rare colour is where.

### 5.3 Derived quantities

```python
def cell_stats(boards, cell):
    """P(blue) and expected SP for one cell, across consistent boards."""
    total = len(boards)
    blue = 0
    sp = 0.0
    for b in boards:
        for name, mask in b:
            if (mask >> cell) & 1:
                sp += sp_per_cell(name)
                break
        else:
            blue += 1
            sp += C.TRACE_BLUE_SP
    return blue / total, sp / total


def sp_per_cell(name: str) -> int:
    if name.startswith("rare"):
        return C.TRACE_RARE[1]
    return C.TRACE_SHIPS[name][1]
```

`P(blue) = 0` means the cell is **guaranteed** to be a ship across every consistent board.
Those cells are free hits and should always be taken first in Phase 2.

### 5.4 Two-phase policy ✅ CONFIRMED structure, ⚠️ UNVERIFIED weights

**Phase 1 — Extra Chance active (ship hits < 5).** Blue clicks don't end the game, so
you're free to probe. The objective is to *map the blue cells* before you accidentally
accumulate 5 ship hits. Score each cell as a blend of:

| Term | Meaning |
|---|---|
| `t_blue` | P(cell is blue) — high means safe to probe now |
| `t_info` / `t_gini` | Information gain: how much this reveal shrinks the board set |
| `t_ev` / `t_var_sp` | Expected SP and its variance across consistent boards |
| `t_rare_id` | Bonus for cells that help identify which rare colours are in play |

colblitz uses a learned scorer here and doesn't publish the weights. Start with a hand-set
linear blend and tune it against your simulator:

```python
PHASE1_WEIGHTS = {          # UNVERIFIED — tune these empirically
    "blue": 1.0,
    "info": 0.4,
    "ev": 0.1,
    "rare_id": 0.15,
}
```

Tuning is a 4-parameter optimisation against average SP over ~20k simulated games.
Coordinate descent over a coarse grid converges in minutes and gets you most of the way;
CMA-ES if you want to be thorough. This is the single highest-leverage tuning job in the
project.

**Phase 2 — Extra Chance off (ship hits ≥ 5).** The next blue click ends the game, so the
rule is simple and near-optimal:

1. If any cell has `P(blue) == 0`, click it. Free, guaranteed, zero risk. Repeat.
2. Otherwise you're gambling. Rank by expected SP weighted against the risk of ending the
   run: `score = (1 − P(blue)) × E[ship SP] − P(blue) × E[remaining value forfeited]`.

Step 1 alone captures most of Phase 2's value. Implement it first and verify that a
"perfect game" (all blues located before the 5th ship hit) collects every ship cell.

### 5.5 Validation

1. **Ground truth survival:** generate a real board, feed its reveals in, assert it stays
   in the consistent set. Same test as quest — same importance.
2. **Placement sanity:** no two ships overlap; total ship cells = 4+3+3+2+2·n_rare.
3. **P(blue)=0 correctness:** any cell flagged guaranteed-ship must actually be a ship on
   the ground-truth board, every time, across 100k boards. A single failure means your
   constraint propagation is unsound and Phase 2 will end games early.
4. **Perfect-game rate:** track how often the policy locates all blues before the 5th ship
   hit. This is your headline metric for Phase 1 tuning.

### 5.6 Honest expectations

colblitz labels their trace solver BETA and backs it with both a precomputed policy table
and a learned scorer, with a greedy emergency fallback. You're rebuilding the constraint
engine (fully doable, described above) plus a hand-tuned scorer (worse than learned, but
in the same ballpark). Expect to land close to their heuristic path, not their policy
table. That's fine — the constraint engine is what makes the tool useful, and the scorer
is a knob you can keep turning.

---

## 6. Perk 9 Calculator — click/skip threshold DP

**Goal:** you get a limited number of sphere-button clicks per day and more sphere rolls
than clicks. Which colours are worth spending a click on, and when?

This one is fully published and is the easiest calculator to get exactly right.

### 6.1 Expected value per click ✅ CONFIRMED

```
EV(colour) = (base_sp × (1 + double_chance) + flat_bonus) × (1 + shop9_bonus)
```

- `double_chance` — from `$bonus`, "twice the sphere button value"
- `flat_bonus` — from `$bonus`, "Additional spheres: +N"
- `shop9_bonus` — SP9 level × 0.10 (+10% per level)
- Daily click cap = `10 + SP9_level`

### 6.2 Static strategy ✅ CONFIRMED

Pick a fixed set of colours to always click, skip the rest. Try every threshold (skip the
`k` lowest-EV colours, for each `k`) and keep the best.

```
P(click)      = 1 − Σ freq(skipped colours)
EV(click)     = Σ freq(clicked) × EV(clicked)     # over clicked colours only
X ~ Binomial(rMax, P(click))                       # clickable buttons in a day
E[clicks used] = Σ_{j=0}^{cMax−1} P(X > j)         # capped by the daily budget
E[SP/day]      = EV(click) × E[clicks used]
```

That `E[clicks used]` identity (sum of tail probabilities) is the neat bit — it's the
expectation of `min(X, cMax)` without enumerating the distribution.

### 6.3 DP-optimal strategy ✅ CONFIRMED

The static threshold is wasteful: early in the day, with many rolls left, you can afford
to be picky; late in the day, with rolls running out, a click you don't spend is wasted.
So the threshold should *fall* as the day progresses.

Define `V(r, c)` = expected total SP from `r` rolls and `c` clicks remaining:

```
V(0, c) = 0                     # no rolls left
V(r, 0) = 0                     # no clicks left
V(r, c) = Σ freq(colour) × max[ EV(colour) + V(r−1, c−1),   # click
                                V(r−1, c) ]                  # skip
```

And the decision rule falls straight out:

```
threshold(r, c) = V(r−1, c) − V(r−1, c−1)      # the value of keeping a click
click if EV(colour) ≥ threshold(r, c), else skip
```

The threshold is literally the opportunity cost of the click. It shrinks as rolls run out,
which is why colours you'd skip in the morning become worth clicking at 23:00.

```python
"""calculators/p9.py"""

import constants as C


def build_policy(colours, r_max: int, c_max: int):
    """
    colours: [(name, ev, freq), ...]
    Returns (V, threshold) as 2D lists indexed [r][c].
    """
    V = [[0.0] * (c_max + 1) for _ in range(r_max + 1)]
    for r in range(1, r_max + 1):
        for c in range(1, c_max + 1):
            total = 0.0
            for _name, ev, freq in colours:
                click = ev + V[r - 1][c - 1]
                skip = V[r - 1][c]
                total += freq * max(click, skip)
            V[r][c] = total

    threshold = [[0.0] * (c_max + 1) for _ in range(r_max + 1)]
    for r in range(1, r_max + 1):
        for c in range(1, c_max + 1):
            threshold[r][c] = V[r - 1][c] - V[r - 1][c - 1]
    return V, threshold


def advise(threshold, colour_ev: float, rolls_left: int, clicks_left: int) -> bool:
    """Live advisor: should I click this button right now?"""
    if clicks_left <= 0 or rolls_left <= 0:
        return False
    return colour_ev >= threshold[rolls_left][clicks_left]
```

`V[r_max][c_max]` is your expected SP/day. Render `threshold` as a heatmap — it's the
single most useful output, because it turns the whole model into a lookup table you can
read at a glance.

### 6.4 Character-count calculator

"How many perk-9 characters do I need before I can afford to skip the cheap colours?"

Each perk-9 character is guaranteed to roll once per day, so `r_max = n_p9_chars`. Given a
skip set with click probability `p`, you want enough rolls that you'll fill your click
budget with high confidence:

```
X ~ Binomial(n, p)
find the smallest n such that P(X ≥ c_max) ≥ confidence
```

```python
from math import comb


def chars_needed(p_click: float, c_max: int, confidence: float = 0.9) -> int:
    n = c_max
    while n < 10_000:
        # P(X >= c_max) = 1 - P(X <= c_max - 1)
        cdf = sum(comb(n, k) * p_click**k * (1 - p_click)**(n - k)
                  for k in range(c_max))
        if 1.0 - cdf >= confidence:
            return n
        n += 1
    return -1
```

Let the user toggle which colours are in the skip set and live-update the table.

### 6.5 The frequency table 🔬 MEASURE

Everything above is exact given `freq(colour)`. colblitz built theirs from 55,249 observed
rolls; that dataset isn't published, so you need your own. Log every perk-9 sphere button
you see: colour, base SP. A few thousand samples gets the common colours tight; the rare
high-value ones need more, and they're exactly the ones the threshold decision hinges on.

Until you have data, seed with plausible values and label every output as provisional.
Wrong frequencies produce a confidently wrong threshold table, which is worse than no
table at all.

---

## 7. `$bw` / Key EV Calculator

**Goal:** every roll you sink into `$bw` buys spawn bonus but costs you a net roll. Find
the `$bw` that maximises keys per hour.

All formulas below are ✅ **CONFIRMED** — published verbatim on the tool page. But read
§7.7 before trusting the absolute numbers.

### 7.1 Net rolls

```
net_rolls(bw) = base_rolls + setrolls − bw − bk
```

### 7.2 Spawn bonus at each `$bw`

The bonus shown in `$bonus` combines several sources. Strip out the `$bw` portion, keep
the rest (`$k`, slash, `$kt`/`$tuto`) as a fixed offset, then recompute at every
hypothetical `$bw`.

Wish bonus from `$bw`, by tier:

| Rolls | Bonus each |
|---|---|
| 1–5 | +20% |
| 6–15 | +15% |
| 16–100 | +10% |
| 101–200 | +5% |
| 201+ | +1% |

Extra **starwish** bonus from `$bw`, by tier:

| Rolls | Bonus each |
|---|---|
| 1–100 | +10% |
| 101–200 | +5% |
| 201+ | +1% |

```python
def wish_bw_bonus(bw: int) -> float:
    tiers = [(5, 20), (10, 15), (85, 10), (100, 5)]
    total, remaining = 0.0, bw
    for count, rate in tiers:
        take = min(remaining, count)
        total += take * rate
        remaining -= take
        if remaining <= 0:
            return total
    return total + remaining * 1


def starwish_bw_bonus(bw: int) -> float:
    tiers = [(100, 10), (100, 5)]
    total, remaining = 0.0, bw
    for count, rate in tiers:
        take = min(remaining, count)
        total += take * rate
        remaining -= take
        if remaining <= 0:
            return total
    return total + remaining * 1
```

Totals:

```
wish_bonus = wish_bw_bonus(bw) + k_bonus + slash_bonus
sw_bonus   = wish_bonus + starwish_bw_bonus(bw) + kt_bonus_sw
```

Slash commands add a flat **+10%** to both wish and starwish.

### 7.3 Spawn chance

A character's spawn rate ≈ its weight ÷ total pool weight.

```
weight(wish)     = 1 + (wish_bonus(bw) + perk1) / 100
weight(starwish) = 1 + (sw_bonus(bw)  + perk1) / 100

p = char_weight / (base_pool + char_weight + Σ other wishlist weights)
```

Base pool contributes 1 per character; wishlist characters contribute their boosted
weights. Perk 1 comes from adjacent wishlist neighbours, with shop upgrade 1 feeding a
portion back to the character itself (10% per level, 0–10).

### 7.4 Keys per spawn

Three independent sources, so expectations just add:

```
keys = 1                    # guaranteed
     + kt_key_pct / 100     # KT tower, global, from $bonus
     + perk4_pct / 100      # perk 4, per character
```

Perk 4 levels: lv1 +4%, lv2 +8%, lv3 +12%, lv4 +16%, lv5 +20%, lv6 +25%, fully upgraded +30%.

### 7.5 The objective

```
EV_keys_per_hour(char, bw) = net_rolls(bw) × p(char, bw) × keys(char)
```

Sweep `bw` from 0 to max, evaluate, take the argmax. That's it — no calculus, no solver.
The curve is unimodal in practice, but sweep anyway; it's 200 evaluations.

Report three optima, because they genuinely differ:

- **Overall** — maximises EV summed across the whole wishlist.
- **Starwish** — counts only starwish keys. Peaks at *higher* `$bw`, because starwishes get
  an extra bw-scaled bonus on top of the wish bonus.
- **Per-character** — for one selected character; lands somewhere else again if that
  character is a starwish or has unusual perks.

### 7.6 Two corrections that move the answer

**persrare rerolls.** With `$persrare` active, a roll landing on a claimed non-wish
character is rerolled up to `N` times:

```
r = C / totalWt(bw)                      # claimed fraction of pool weight
P'_wish      = p_wish × (1 − r^N) / (1 − r)
P'_unclaimed = p_uncl × (1 − r^N) / (1 − r)
P'_claimed   = r^N
```

Where `C` = count of claimed non-wish characters, `N` = reroll limit (1–10; N=1 means no
rerolling). This is bw-dependent: at lower `$bw` the total pool weight is smaller, so `r`
is larger and the reroll benefit is greater — meaning **persrare shifts the optimum
downward**, by an amount growing with C's share of the pool.

**Hourly caps.**

```
Key cap:      effective_keys(bw) = min(total_ev(bw), 2200)
Slash split:  slash_rolls    = min(net_rolls(bw), 1440)
              overflow_rolls = net_rolls(bw) − slash_rolls
              ev(bw) = slash_rolls × p_slash × keys
                     + overflow_rolls × p_no_slash × keys
```

You can't earn more than 2,200 keys/hour — excess is wasted, so report the *lowest* `$bw`
that reaches the cap. And Discord rate-limits slash commands to ~1,440/hour; rolls beyond
that must use `$`-prefix and lose the +10% slash bonus.

### 7.7 Accuracy disclaimer ✅ CONFIRMED (and worth repeating in your UI)

The exact roll-chance formulas are **not publicly documented**. Everything above is the
Mudae community's best reconstruction. Known gaps:

- Starwishes spawn more often than the formula predicts, especially with large wishlists.
- persrare modelling is inaccurate at high `$persrare` values.
- Not modelled at all: wishprotect, `$wishk`, `$wishseries`, perk 6 / shop 6.
- Exact pool size is hard to compute because of disablelist / antidisablelist overlaps.

**However** — and this is the important part — the *optimal `$bw` recommendation stays
roughly correct*, because near-constant scaling factors shift the EV curve up or down
without moving its peak. Treat absolute keys/hr as relative comparison only. Put that
sentence in the UI; it's the difference between a useful tool and a misleading one.

### 7.8 Input parsing

Users paste raw `$bonus` and `$wlsz+z!` output. Parse leniently: scan for the lines you
care about with regex and ignore everything else (timestamps, usernames, stray text). Both
"select and copy" and "right-click → Copy Text" should work. Show the extracted values in
editable fields so users can override a bad parse, with a "reparse" button.

---

## 8. Sphere Upgrades Calculator (`spcalc`)

**Goal:** given your account state, which sphere upgrade should you buy next?

The most complex tool on the site, and — helpfully — the most exhaustively documented.
Every constant below is ✅ **CONFIRMED** from the tool page.

### 8.1 Income model

```
sp/day = base_daily + OP9_sp + OP5_OP8_sp + OP10_sp + SP2_sp + SP5_sp + SP10_sp
```

**Base daily minigames.** `base = 4 × EV($oh) + PP × EV($oc) + PP × EV($oq)` where
`EV(reward) = base × (1 + double_chance) + clicks × flat_bonus`, and PP by premium tier is
`[1,2,2,2]` for `$oc` and `[0,0,1,1]` for `$oq`.

**OP9 sphere buttons.** Each OP9 character spawns one button/day, times P(rolling at least
one wish that day). Click cap is `10 + SP9_level`, shared across all OP9 chars. When spawns
exceed the cap, reuse the §6 DP to decide which colours to click:

```
EV(colour)  = (base × (1 + double_chance) + flat_bonus) × (1 + SP9_level × 0.10)
V(r, c)     = Σ freq(colour) × max[EV(colour) + V(r−1,c−1), V(r−1,c)]
OP9_sp/day  = V(spawns, click_budget)
OP9_oq      = expected_clicks × P($oq proc) × EV($oq)
```

**OP5+OP8 kakera clicks.** Assume 4 buttons/day per character, limited by react power:

```
total_power = max_power × (1 + num_dk)          # num_dk = [1,2,2,3] by premium
clicks 1–40:  cost react_cost/4, OP5 at face value
clicks 41+:   cost react_cost/2, OP5 doubled
OP5_OP8_sp = pre × (12 or 19) + post × (12 or 19) × 2 + clicks × pp3_bonus
```

lv4 chars give 12 sp/click, lv6 give 19. Click lv6 first.

**SP5 `$ot` procs.** 0.014% per SP5 level per sphere earned from an OP5 click:

```
SP5_chance = SP5_level × 0.00014
SP5_sp     = Σ clicks × SP5_chance × sp_per_click × EV($ot)
EV($ot)    = 834.65 × (1 + double) + 21 × flat
```

**SP2 megaspheres.** Each claimed roll has a 1/50 chance of spawning one; chains up to 5×,
and OP2 raises the free-chain chance (every 100 OP2 lv5+ chars guarantees one continuation):

```
p_spawn  = 1 − (49/50)^(claimed_rolls_per_day)
free(k)  = clamp((OP2_chars − 100×(k−1)) / 100, 0, 1)
E[mg/day] = Σ_{k=1..5} p_spawn^k × Π free(j)
SP2_sp   = E[mg/day] × 3 × SP2_level × EV(component)
```

Each megasphere holds `3 × SP2_level` component spheres. Most are regular colours (not
affected by double chance or flat bonus); a small fraction give special rewards that are.

**OP10 passive income.** Tiered, decreasing marginal rate:

```
sp = min(n,100)×20 + min(n−100,100)×8 + min(n−200,100)×4
   + min(n−300,200)×2 + max(n−500,0)×2
OP10_oq = oq_pct × EV($oq)
oq_pct  = min(n,100)×1.0 + min(n−100,400)×0.5    # as a percentage
```

**SP10 `$ot` procs.** Once daily, on your first `$oh`:

```
SP10_sp = SP10_level × 0.0025 × min(fully_upgraded_chars, 120) × EV($ot)
```

### 8.2 Why greedy ROI is wrong

A naive optimiser picks `argmax Δrate / cost` at each step. Two things break it:

**The time problem.** It ignores how long you must *save* to afford the upgrade. A slightly
less efficient but cheaper upgrade you can buy today, earning from today, beats a more
efficient one that needs a week of saving during which you earn nothing extra.

Fix with a discounted infinite-horizon objective:

```
V = Σ rate_i × (e^(−δ·t_i) − e^(−δ·t_{i+1}))/δ  +  final_rate × e^(−δ·t_end)/δ
δ = 1 / discount_days          # default 365
```

Near-term income counts more; the trailing perpetuity keeps long-run rate relevant.

**The synergy problem.** Some upgrades are worthless alone. SP9 does nothing without OP9
characters; OP2 does nothing without SP2. Greedy evaluates each in isolation and may delay
a pair indefinitely when taking a small short-term hit to unlock both is correct.

Fix by evaluating **coupled clusters jointly** — exact Bellman DP over orderings within
each cluster (OP9+SP9, OP2+SP2, OP5+OP8), then a rolling-window merge to interleave the
cluster orderings into one global sequence.

```python
CLUSTERS = [
    ("op9_sp9", ["OP9", "SP9"]),
    ("op2_sp2", ["OP2", "SP2"]),
    ("op5_op8", ["OP5", "OP8"]),
]

def optimise(state, upgrades, discount_days=365, window=4):
    """
    1. For each cluster, DP over all internal orderings (small: <= 6! per cluster).
    2. Merge cluster sequences with a rolling window of size `window`,
       scoring each candidate interleaving by the discounted objective.
    3. Return the flat ordered list of purchases.
    """
```

Offer both modes in the UI, as the original does: **Greedy** (instant, ROI per step) and
**Optimize** (slower, handles synergies). Greedy is the honest fallback when the DP times
out.

### 8.3 Modelling assumptions to document ✅ CONFIRMED

State these in the UI. Users will otherwise assume more precision than exists:

- All OP9 characters are modelled as wished (overstates OP9 value for unwished ones).
- All OP5+OP8 characters are modelled as soulmates; non-soulmates have higher effective
  react costs and aren't modelled.
- Assumes you save full react power and spend all `$dk` on OP8 clicks.
- Assumes every affordable react button is clicked each day.
- OP1 bonuses are averaged across the wishlist rather than computed per character, and are
  ignored once P(rolling your wishes daily) > 99%.
- Fully-upgraded characters give 23 sp/click in game but the model uses 19, slightly
  undervaluing them.

### 8.4 Output

A table of ordered actions with: action, count, cost, wait time, cumulative cost,
resulting sp/day, and Δrate per 1k cost. Add checkboxes so users can mark steps done and
resume later — the plan spans weeks, and that's the feature people actually come back for.

---

## 9. Disablelist Calculator (`dlcalc`)

**Goal:** pick which bundles to `$disable` to maximise the number of disabled characters,
subject to slot count and per-pool limits.

This is the only tool here that's a classic textbook problem, which makes it the easiest
to get *right* and the easiest to get *slow*.

### 9.1 The problem

Bundles overlap, each bundle spans multiple pools, each pool has a cap on how many
characters may be disabled, and you have a fixed number of `$disable` slots. That's a
**maximum coverage problem with multiple knapsack constraints** — NP-hard in general, very
tractable at this size.

### 9.2 Exact ILP formulation

```
variables:
    x_b ∈ {0,1}     bundle b is selected
    y_c ∈ {0,1}     character c is disabled

maximise:   Σ_c y_c

subject to: y_c ≤ Σ_{b ∋ c} x_b        for all c   (only covered chars count)
            Σ_b x_b ≤ slots                        (slot budget)
            Σ_{c ∈ pool p} y_c ≤ limit_p  ∀ pool p (pool caps)
            x_b = 1  for b ∈ force_include
            x_b = 0  for b ∈ force_exclude
```

The `y_c ≤ Σ x_b` linking constraint is what handles overlap correctly — a character
covered by three selected bundles still counts once.

### 9.3 The scaling trick that makes it fast

Mudae has hundreds of thousands of characters, so one `y_c` per character is too many.
But characters are only distinguishable by **which set of bundles contains them**. Group
them into equivalence classes ("atoms"): all characters belonging to exactly the same
bundle-set collapse into one variable with a weight equal to the class size.

```python
from collections import defaultdict

def build_atoms(bundle_members: dict[str, set[int]]):
    """char -> frozenset(bundles containing it), then group."""
    membership = defaultdict(set)
    for bundle, chars in bundle_members.items():
        for c in chars:
            membership[c].add(bundle)
    atoms = defaultdict(list)
    for c, bundles in membership.items():
        atoms[frozenset(bundles)].append(c)
    return atoms      # frozenset(bundles) -> [chars]
```

This typically cuts the variable count by two or three orders of magnitude and turns a
hopeless model into one CP-SAT solves in seconds.

### 9.4 Implementation with OR-Tools

```python
"""calculators/dl.py"""

from ortools.sat.python import cp_model


def solve(atoms, pool_of, slots, pool_limits,
          force_include=(), force_exclude=(), time_limit=60.0):
    model = cp_model.CpModel()
    bundles = sorted({b for key in atoms for b in key})

    x = {b: model.NewBoolVar(f"x_{b}") for b in bundles}
    y = {key: model.NewBoolVar(f"y_{i}") for i, key in enumerate(atoms)}

    for key, var in y.items():
        model.AddMaxEquality(var, [x[b] for b in key])

    model.Add(sum(x.values()) <= slots)

    for pool, limit in pool_limits.items():
        model.Add(
            sum(y[key] * count_in_pool(atoms[key], pool, pool_of)
                for key in atoms) <= limit
        )

    for b in force_include:
        model.Add(x[b] == 1)
    for b in force_exclude:
        model.Add(x[b] == 0)

    model.Maximize(sum(y[key] * len(atoms[key]) for key in atoms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = [b for b in bundles if solver.Value(x[b])]
        return chosen, solver.ObjectiveValue(), status == cp_model.OPTIMAL
    return [], 0, False
```

On Bazzite (immutable Fedora), install into a venv or a toolbox container rather than the
base image: `python -m venv .venv && .venv/bin/pip install ortools`.

### 9.5 Fast mode

Offer greedy as the default, matching the original's "Fast search":

```python
def greedy(atoms, slots, pool_limits, pool_of):
    """Repeatedly take the bundle adding the most new characters."""
    chosen, covered = [], set()
    while len(chosen) < slots:
        best, best_gain = None, 0
        for b in candidate_bundles(atoms, chosen):
            gain = new_chars(b, covered, atoms)
            if gain > best_gain and fits_pool_limits(b, covered, pool_limits, pool_of):
                best, best_gain = b, gain
        if best is None:
            break
        chosen.append(best)
        covered |= chars_in(best, atoms)
    return chosen
```

It's instant and usually good, but it can't look ahead or reason about overlap — two
bundles that are individually mediocre but jointly cover a huge disjoint set will be
missed. Present it honestly: *"Advanced search is slower and may not prove optimality
within the time limit, but always returns at least as good a result as fast search."*
Seed the CP-SAT model with the greedy solution as a hint to guarantee that property.

### 9.6 Extra features worth having

- **Toggles** (Hentai, Western, Real Life, Disturbing Imagery) — those characters are
  already disabled, so remove them from the universe before solving.
- **Desired series/characters** — soft constraints. Add a penalty term to the objective
  for covering them, but keep pool limits as hard constraints, since hitting the cap has
  to take priority.
- **Evaluate current** — parse a pasted `$disable` command and report per-pool stats plus
  how many desired characters survive. This is the feature users actually open the tool
  for, and it needs no solver at all.

### 9.7 The real work is data

The algorithm is a day's work. The bundle-to-character mapping is the hard part, and it
has to be kept current as Mudae's database changes. Sources worth looking at rather than
rebuilding from scratch: `github.com/LilJamJam/MudaeDB` (scraped database, bundle overlap
files) and `github.com/PRCSakura/Mudae-DL-Builds` (maintained ready-made builds). Design
your data layer to ingest a refreshable dump, not a hardcoded snapshot.

---

## 10. Live solver architecture

**Goal:** you play in Discord; recommendations update automatically as the board changes,
with no copying or clicking in a second UI.

This is the part of colblitz's stack that's genuinely undocumented — none of the parsing
logic is described anywhere on the site. It's also the part with the most engineering per
unit of algorithm.

### 10.1 How it works end to end

```
Mudae posts/edits a game message
        ↓
Bot receives on_message_edit (needs Message Content intent)
        ↓
parser.py: message → BoardState
        ↓
session.py: match to a user's active game, diff against previous state
        ↓
solver: recommend(state)
        ↓
websocket push → browser renders board + recommendation
```

Each button click in Discord triggers a **message edit**, not a new message. That's the
event you hook. The board is fully re-serialised on every edit, so you never need to
reconstruct history — you just re-parse.

### 10.2 Parsing 🔬 the part you have to figure out yourself

The board lives in the message's **component rows** (5 rows × 5 buttons for these games),
not the embed body. Each button carries an emoji and a style. Map emoji ID → colour with a
lookup table you build once by observation:

```python
EMOJI_TO_COLOUR = {
    # "<:name:id>" or the raw emoji id -> colour name. MEASURE: fill from
    # live messages; log every unknown emoji rather than crashing.
}


def parse_board(message) -> BoardState:
    cells = []
    for row in message.components:
        for button in row.children:
            cells.append(classify(button))
    if len(cells) != 25:
        raise ParseError(f"expected 25 buttons, got {len(cells)}")
    return BoardState(cells=cells, game=detect_game(message))


def classify(button):
    if button.disabled and button.emoji is None:
        return "clicked"
    emoji_key = str(button.emoji)
    if emoji_key not in EMOJI_TO_COLOUR:
        log_unknown_emoji(emoji_key)      # never crash on a new sphere colour
        return "unknown"
    return EMOJI_TO_COLOUR[emoji_key]
```

Build this defensively. Mudae adds colours and changes emoji; an unknown emoji should
degrade to "unknown" and get logged, not take down the session.

Detect the game type from the embed title or the button layout — `$oh` has mixed button
types from the start, `$oq`/`$oc` start fully covered, `$ot` shows a colour-count
indicator.

### 10.3 Session state

```python
@dataclass
class Session:
    user_id: int
    channel_id: int
    message_id: int
    game: str                 # "harvest" | "chest" | "quest" | "trace"
    board: BoardState
    clicks_used: int
    sp_earned: int
    history: list[BoardState]
```

Key it on `message_id` — one Discord message is one game. Expire sessions after ~15
minutes of inactivity so abandoned games don't accumulate.

Derive `clicks_used` by **diffing consecutive board states** rather than trusting a
counter. In harvest especially, purple clicks are free, so a naive increment-per-edit
counter drifts immediately. Diff, classify what changed, and decide whether it consumed
budget.

### 10.4 Bot permissions and scope

The bot needs to *read messages* in the sphere channels, and that's all — no slash
commands, no writes. Invite with `scope=bot` and read-message permissions only.

Worth pre-empting in your own UI, because colblitz had to: Discord's authorisation dialog
always shows "Create commands" regardless of what you request. It's hardcoded by Discord
and can't be removed. Say so up front or you'll field the question repeatedly.

**One caveat on the automation side.** A proper bot account reading messages it's been
invited to is standard Discord API usage. Driving a *user* account programmatically
(self-bot libraries such as `discord.py-self`) is against Discord's Terms of Service and
carries a real ban risk regardless of how carefully it's done. Those are different
architectures with different consequences — worth being deliberate about which one you're
building, especially if this ever goes beyond your own account.

### 10.5 Push transport

WebSocket per logged-in user, keyed by Discord OAuth identity. On each parsed edit, push:

```json
{
  "type": "board_update",
  "game": "quest",
  "cells": ["covered", "blue", "purple", "..."],
  "clicks_used": 3,
  "recommendation": {"cell": 12, "reason": "P=0.83, M=0.87"},
  "overlays": {"P": [], "M": [], "G": [], "EV": []}
}
```

Solving must not block the event loop. Quest and chest are fast enough to run inline;
harvest is instant once its DP table is warm; **trace enumeration is not** — run it in a
`ProcessPoolExecutor` with a concurrency cap, exactly as the changelog on the real site
shows they eventually had to.

### 10.6 Performance notes worth stealing

colblitz's public changelog is essentially a list of the scaling problems this design
hits. Free lessons:

- Reuse a single `httpx.AsyncClient` rather than creating one per request.
- Cap concurrency on subprocess-based solvers (they added a limit to `spcalc`).
- Offload blocking disk/glob/stat work to an executor.
- Pre-aggregate stats into summary tables instead of computing over raw rows.
- Two-phase polling for long-running jobs: submit, then poll for the result.

Design for these on day one and you skip the rewrite.

---

## 11. Simulators and the evaluation harness

**Build the simulators before the solvers.** This is the single most important piece of
process advice in this document.

Every solver here depends on constants you don't have and rules you're partly guessing at.
A simulator gives you ground truth to test against, lets you reproduce the published
benchmark tables, and turns "is my solver good?" from an argument into a number.

### 11.1 Board generators

```python
"""sim/generators.py"""

import random
from itertools import combinations
from grid import CELLS


def gen_quest() -> frozenset[int]:
    """4 purples uniformly at random. CONFIRMED correct."""
    return frozenset(random.sample(CELLS, 4))


def gen_chest() -> dict[int, str]:
    """UNVERIFIED — depends on the generator reconstruction in §3.2."""
    red = random.choice(RED_POSITIONS)
    return random.choice(enumerate_boards(red))


def gen_trace(colour_count: int) -> list[tuple[str, int]]:
    """Random non-overlapping ship placement. CONFIRMED rules."""
    while True:
        board = try_place_all(colour_count)
        if board is not None:
            return board


def gen_harvest() -> list[str]:
    """MEASURE — needs the reveal distribution to be real."""
    return [sample_colour() for _ in CELLS]
```

### 11.2 The harness

```python
"""sim/evaluate.py"""

def evaluate(policy, generator, n_games=100_000, seed=0):
    """
    Returns {avg_sp, success_rate, efficiency, p50, p95, elapsed}.
    `policy` is a callable: (observation) -> cell_index.
    """
```

Report the same three columns the published tables use — **avg SP, success rate,
efficiency** — so you can compare directly.

### 11.3 Targets

| Game | Metric | Target |
|---|---|---|
| Quest | Avg SP / success | 342.7 / 95.4% (MIXED), 356.3 / 98.1% (DP) |
| Quest | Theoretical max | 381.9 |
| Harvest | DP value vs simulated mean | agree within sampling error |
| Chest | DP policy vs max-red-probability greedy | DP strictly better |
| Trace | Perfect-game rate | maximise; no published baseline |

Quest is the calibration point for the whole project. If your quest numbers match the
published table, your enumeration, filtering, and evaluation harness are all sound — and
that's most of the machinery the other three solvers reuse.

### 11.4 Data collection

```python
"""sim/collect.py — fill in the MEASURE constants."""
```

Log every real game you play, in full: initial board, every reveal, every click, SP
awarded per click, final total. Store as newline-delimited JSON, one game per line. Then:

| Constant | Fit from |
|---|---|
| `HARVEST_REVEAL_DIST` | Colour histogram of revealed covered cells |
| `HARVEST_COVERED_OC_CHANCE` | Fraction of covered clicks granting `$oc` |
| `CHEST_COLOUR_SP` / `QUEST_COLOUR_SP` | SP awarded per click, grouped by colour |
| Chest generator | Full boards → verify the 2/3/4 counts and their draw pools |
| `P9_COLOURS` frequencies | Colour histogram of perk-9 button spawns |

Rough sample sizes: a few hundred games pins the common colours; the rare high-value
outcomes need thousands, and those are exactly the ones your thresholds hinge on. Start
logging on day one — the data collection is the long pole, not the code.

---

## 12. Suggested build order

| # | Task | Why here | Rough effort |
|---|---|---|---|
| 1 | `grid.py`, `constants.py`, repo skeleton | Everything depends on it | 1 hour |
| 2 | Quest simulator + evaluation harness | Ground truth before solvers | half a day |
| 3 | **Quest solver (MIXED)** | Fully specified, benchmarkable, immediately useful | 1 day |
| 4 | Reproduce the §4.4 benchmark table | Proves the whole harness | few hours |
| 5 | Data collection logger | Long lead time — start it early | half a day |
| 6 | Harvest DP | Small state space, self-contained | 1 day |
| 7 | p9 calculator | Pure arithmetic, high daily value | half a day |
| 8 | Chest — empirical-likelihood version | Works without the generator | 1 day |
| 9 | Chest — exact, once the generator is confirmed | Needs logged data from step 5 | 1 day |
| 10 | dl calculator | Independent; data ingest is the real work | 2 days |
| 11 | Trace enumeration + Phase 2 | Phase 2 alone is most of the value | 2 days |
| 12 | Trace Phase 1 scorer + tuning | Diminishing returns; tune against the harness | open-ended |
| 13 | bw calculator | Transcription, plus lenient input parsing | 1–2 days |
| 14 | sp calculator | Most complex model, least urgent | 3 days |
| 15 | Live solver | Depends on all of the above | 1 week+ |

**If you only build one thing:** the quest solver. Fully specified, no unknown constants,
a published benchmark to verify against, and it's the minigame where good play differs
most from intuition.

---

## 13. Open questions to resolve

Ordered by how much they block progress.

1. **Chest board generator** (§3.2) — blocks exact chest inference. Resolve by logging
   30–50 full boards and fitting the 2/3/4 colour counts against red position.
2. **Harvest reveal distribution** (§2.1, `HARVEST_REVEAL_DIST`) — the DP is exact but its
   answers are only as good as this table.
3. **Harvest dark-cell semantics** (§2.1) — does clicking dark also collect the resulting
   sphere, or only transform the cell? Ten games settles it.
4. **Per-colour SP values** for chest and quest — needed for EV, not for finding the
   target. Solvers work without them; EV displays don't.
5. **Perk-9 colour frequencies** (§6.5) — wrong values here produce a confidently wrong
   threshold table.
6. **Trace Phase 1 weights** (§5.4) — not blocking; tune indefinitely against the harness.
7. **Trace rare-ship values** — "~90 sp/cell" is approximate; confirm whether rares differ
   from orange.

---

## 14. Sources and prior art

Everything algorithmic in this document comes from the "How it works" sections that
colblitz publishes on each tool page — those are unusually complete, and sections 6–9 are
close to a full functional spec in prose. What isn't published: the trace learned scorer
and policy table, the perk-9 frequency dataset (55,249 observed rolls), the bundle
database, and the entire Discord parsing layer.

Other community implementations worth reading, since several publish actual source:

| Project | Covers | Source |
|---|---|---|
| Svess | `$oh` `$oc` `$oq` `$ot` solvers + simulators | `github.com/Svessinn/Mudae` — public, Python |
| GabrielP | `$oq` solver | `github.com/GAP22/oq-solver` — public |
| ShrimpandGGrits | `$oc` + `$oq` solver | `github.com/ShrimpandGGrits/mudae-sphere-solver` — public |
| Glass | `$ot` visualiser | `tksglass.github.io/OT` — GitHub Pages, source likely at `github.com/tksglass/OT` |
| LilJamJam | Scraped character/bundle database | `github.com/LilJamJam/MudaeDB` |
| PRCSakura | Maintained `$dl` builds | `github.com/PRCSakura/Mudae-DL-Builds` |

Svess's is the most useful reference — it's Python, it covers all four games, and it
includes simulators as well as solvers. Read it before writing the trace enumerator in
particular.

Tools with no public source found (closed, or client-side only): kelinimo's Grid Game
Solvers, xrock's `$oc`/`$oq` helpers, zavex's `$oq`/`$ot` solvers, and colblitz's own
tools — which solve server-side in Python, so there's no client JS to inspect at all.
