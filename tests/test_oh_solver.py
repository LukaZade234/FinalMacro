"""Tests for the $oh expected-value solver (macro/oh_solver.py).

The headline result — a face-down click beats a known revealed blue or teal
at every clicks-left level, so the shipped heuristic's "never click a
revealed blue/teal" rule is already optimal — is exactly the kind of claim
that is easy to get backwards with a sign error or a double-counted
probability. These tests pin the closed-form values against an independent
Monte Carlo rollout of the same decisions, not just against each other.
"""

from __future__ import annotations

import random
from functools import lru_cache

import pytest

from macro.oh_replay import OC_CELL, OH_CELL_SP, OH_FREE, OH_SPAWN_RATES, OH_UNVEILS
from macro.oh_solver import best_action, choose_oh_click_dp, solve


def test_value_grows_with_clicks_and_is_zero_at_none():
    assert solve(0, 0, 0) == 0.0
    values = [solve(c, 0, 0) for c in range(0, 6)]
    assert values == sorted(values)
    assert all(b > a for a, b in zip(values, values[1:]))


def test_hidden_beats_a_known_revealed_blue_or_teal_up_to_ten_clicks():
    """The headline finding: never worth cashing in a sitting blue/teal.

    A face-down click carries the exact same chance of resolving to blue or
    teal — and triggering the same unveil — plus a shot at every
    higher-value colour, so it should never be worse than taking a known
    one outright. Checked well past any realistic click budget (1-5, one
    logged account at 10).
    """
    for clicks_left in range(1, 11):
        assert best_action(clicks_left, 1, 0) == "hidden"
        assert best_action(clicks_left, 0, 1) == "hidden"
        assert best_action(clicks_left, 3, 3) == "hidden"


def test_solve_matches_independent_monte_carlo_rollout():
    """Cross-check the closed-form recursion against a from-scratch simulator.

    Deliberately does not import anything from ``oh_solver`` except the
    public ``best_action``/``solve`` — the unveil bookkeeping here is
    reimplemented independently so a bug shared between the DP's internal
    combinatorics and this check would be a coincidence, not a given.
    """
    memo_action = lru_cache(maxsize=None)(best_action)
    kinds = list(OH_SPAWN_RATES)
    weights = [OH_SPAWN_RATES[k] for k in kinds]

    def draw(rng: random.Random) -> str:
        return rng.choices(kinds, weights=weights, k=1)[0]

    def resolve_unveil(rng, blue_visible, teal_visible, queue, total):
        kind = draw(rng)
        if kind == OH_FREE:
            total += OH_CELL_SP[OH_FREE]
        elif kind == OC_CELL:
            pass
        elif kind == "spB":
            blue_visible += 1
        elif kind == "spT":
            teal_visible += 1
        else:
            queue.append(OH_CELL_SP[kind])
        return blue_visible, teal_visible, total

    def play(budget: int, rng: random.Random) -> float:
        total = 0.0
        clicks_left = budget
        blue_visible = 0
        teal_visible = 0
        queue: list[float] = []
        while clicks_left > 0:
            if queue:
                best = max(queue)
                total += best
                queue.remove(best)
                clicks_left -= 1
                continue
            action = memo_action(clicks_left, blue_visible, teal_visible)
            if action == "hidden":
                kind = draw(rng)
                if kind == OH_FREE:
                    total += OH_CELL_SP[OH_FREE]
                    continue
                clicks_left -= 1
                if kind == OC_CELL:
                    pass
                elif kind == "spB":
                    total += OH_CELL_SP["spB"]
                    for _ in range(OH_UNVEILS["spB"]):
                        blue_visible, teal_visible, total = resolve_unveil(
                            rng, blue_visible, teal_visible, queue, total
                        )
                elif kind == "spT":
                    total += OH_CELL_SP["spT"]
                    blue_visible, teal_visible, total = resolve_unveil(
                        rng, blue_visible, teal_visible, queue, total
                    )
                else:
                    total += OH_CELL_SP[kind]
            elif action == "spT":
                teal_visible -= 1
                clicks_left -= 1
                total += OH_CELL_SP["spT"]
                blue_visible, teal_visible, total = resolve_unveil(
                    rng, blue_visible, teal_visible, queue, total
                )
            elif action == "spB":
                blue_visible -= 1
                clicks_left -= 1
                total += OH_CELL_SP["spB"]
                for _ in range(OH_UNVEILS["spB"]):
                    blue_visible, teal_visible, total = resolve_unveil(
                        rng, blue_visible, teal_visible, queue, total
                    )
        return total

    rng = random.Random(2026)
    n = 30000
    for budget in (1, 5):
        mean = sum(play(budget, rng) for _ in range(n)) / n
        dp = solve(budget, 0, 0)
        # Loose tolerance: this is a statistical check, not exact equality —
        # it exists to catch a mismodelled formula (off by many SP), not to
        # pin the DP's value to Monte Carlo noise.
        assert mean == pytest.approx(dp, abs=0.5), (budget, mean, dp)


def test_choose_oh_click_dp_prefers_a_free_purple_over_everything():
    buttons = [
        {"custom_id": "cmd s0", "emoji": "spP", "kind": "sphere", "disabled": False},
        {"custom_id": "cmd s1", "emoji": "spW", "kind": "sphere", "disabled": False},
        {"custom_id": "cmd s2", "emoji": "spU", "kind": "sphere", "disabled": False},
    ]
    choice = choose_oh_click_dp(buttons, clicks_spent=0, clicks_budget=5)
    assert choice["custom_id"] == "cmd s0"


def test_choose_oh_click_dp_takes_an_always_take_colour_over_blue_or_hidden():
    buttons = [
        {"custom_id": "cmd s0", "emoji": "spG", "kind": "sphere", "disabled": False},
        {"custom_id": "cmd s1", "emoji": "spB", "kind": "sphere", "disabled": False},
        {"custom_id": "cmd s2", "emoji": "spU", "kind": "sphere", "disabled": False},
    ]
    choice = choose_oh_click_dp(buttons, clicks_spent=0, clicks_budget=5)
    assert choice["custom_id"] == "cmd s0"


def test_choose_oh_click_dp_prefers_hidden_over_a_revealed_blue():
    buttons = [
        {"custom_id": "cmd s0", "emoji": "spB", "kind": "sphere", "disabled": False},
        {"custom_id": "cmd s1", "emoji": "spU", "kind": "sphere", "disabled": False},
    ]
    choice = choose_oh_click_dp(buttons, clicks_spent=0, clicks_budget=5)
    assert choice["custom_id"] == "cmd s1"


def test_choose_oh_click_dp_takes_revealed_blue_rather_than_forfeit_the_click():
    """The one real gap the DP surfaces: no face-down cell left, budget remains.

    Quitting (returning ``None``) leaves guaranteed SP on the table — the
    shipped heuristic had this bug (see ``macro/sphere_game.py``); the DP
    chooser must not repeat it.
    """
    buttons = [
        {"custom_id": "cmd s0", "emoji": "spB", "kind": "sphere", "disabled": False},
    ]
    choice = choose_oh_click_dp(buttons, clicks_spent=0, clicks_budget=5)
    assert choice["custom_id"] == "cmd s0"


def test_choose_oh_click_dp_returns_none_when_nothing_clickable():
    assert choose_oh_click_dp([], clicks_spent=0, clicks_budget=5) is None
    exhausted = [
        {"custom_id": "cmd s0", "emoji": "spB", "kind": "sphere", "disabled": False},
    ]
    assert choose_oh_click_dp(exhausted, clicks_spent=5, clicks_budget=5) is None
