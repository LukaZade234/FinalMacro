"""Expected-value solver for the Mudae ``$oh`` sphere-grid minigame.

Every cell is an independent draw from :data:`macro.oh_replay.OH_SPAWN_RATES`,
and Colblitz's reveal mechanic is positionless (26.8% of unveils land next to
the clicked cell against 24.0% expected by chance — see
``docs/MUDAE_LOGIC.md``'s ``$oh`` section), so the board carries no
geometry worth modelling. What is worth modelling is the one real decision the
shipped heuristic in :func:`macro.sphere_game.choose_oh_click` still gets by
a fixed rule rather than a computed one: whether to spend a click on an
already-**revealed** blue or teal sphere, or gamble it on a face-down cell.

Every other choice already has a provably dominant answer and needs no DP:

* A revealed **purple** (``spP``) never costs a click and is worth strictly
  more than leaving it, so it is always taken first.
* A revealed **green/yellow/dark/light/orange/red/rainbow** always pays more
  than a single click's expected value even before any of blue/teal's unveil
  bonus is counted (their cheapest member, green at 35 SP, already clears the
  ~20 SP a face-down click nets), so any of them sitting revealed is always
  the next click — no comparison needed, and no reason to ever delay one:
  its value does not decay and taking it does not cost a future option.

That leaves **blue** (10 SP, unveils 3 more cells for free) and **teal**
(20 SP, unveils 1) as the only spheres worth weighing against a face-down
click's ~20 SP expectation — and the answer is not a fixed rule, because a
face-down click's own expected value already includes the same unveil chain
whenever it happens to turn up blue or teal, so the comparison is between two
compound, budget-dependent quantities rather than two fixed numbers. That is
exactly what :func:`solve` computes, by backward induction over
``(clicks_left, blue_visible, teal_visible)``: small integers, since neither
count can exceed what the remaining clicks could ever have unveiled.

**Purple is free money and is folded out of the state entirely** — both the
occasional purple a face-down click turns up (it does not spend the click, so
it is a geometric bonus added to that click's expected value) and any purple
an unveil turns up (it sits revealed and is claimed on the very next click at
zero cost, so its 5 SP is credited immediately rather than modelled as
competing for a future turn). Likewise the seven always-take colours are
settled the instant they appear (:func:`_settle_queue`) rather than carried
as state — the only thing ever worth deciding is blue-vs-teal-vs-hidden.
"""

from __future__ import annotations

from functools import lru_cache
from itertools import product
from typing import Any

from macro.oh_replay import (
    OC_CELL,
    OH_CELL_SP,
    OH_FREE,
    OH_HIDDEN,
    OH_SPAWN_RATES,
    OH_UNVEILS,
)

# The 9 spheres that cost a click and pay SP (excludes the free purple and
# the invisible $oc bucket, which is never a click target — it looks and
# behaves exactly like an unrevealed cell either way, see module docstring).
_PAID_KEYS = [k for k in OH_SPAWN_RATES if k not in (OH_FREE, OC_CELL)]
# Blue and teal are the only paid spheres with a side effect (an unveil), so
# they are the only ones ever worth holding back a click for.
_HOLD_KEYS = frozenset(OH_UNVEILS)
# Everything else pays enough on its own (see module docstring) to be a
# dominant, no-lookahead take whenever revealed.
_ALWAYS_TAKE_KEYS = [k for k in _PAID_KEYS if k not in _HOLD_KEYS]

_TOTAL_RATE = sum(OH_SPAWN_RATES.values())
# What a single unveiled — or blindly clicked-and-immediately-resolved —
# cell turns out to be, as (kind, probability) over all 11 possibilities.
_SINGLE_CELL_OUTCOMES: tuple[tuple[str, float], ...] = tuple(
    (kind, rate / _TOTAL_RATE) for kind, rate in OH_SPAWN_RATES.items()
)

_P_FREE = OH_SPAWN_RATES[OH_FREE] / _TOTAL_RATE
# A face-down click that lands on the free purple does not spend the click,
# so the click keeps going until it lands on something that does. That is a
# geometric series over "another free purple", collapsed to a closed form:
# renormalising the other 10 outcomes to sum to 1, plus the expected count of
# free purples drawn along the way (each worth OH_CELL_SP[spP]).
_CLICK_OUTCOMES: tuple[tuple[str, float], ...] = tuple(
    (kind, prob / (1.0 - _P_FREE))
    for kind, prob in _SINGLE_CELL_OUTCOMES
    if kind != OH_FREE
)
_CLICK_FREE_BONUS = (_P_FREE / (1.0 - _P_FREE)) * OH_CELL_SP[OH_FREE]

# Every combination of what blue's 3 unveiled cells turn out to be, collapsed
# to (probability, free_bonus_sp, blue_delta, teal_delta, queue) — only the
# aggregate matters, never which of the 3 physical cells produced it. Built
# once at import time; each state's blue-click branch reuses it rather than
# re-enumerating 1,000 combinations per call.
_TRIPLE_UNVEIL_OUTCOMES: tuple[tuple[float, float, int, int, tuple[float, ...]], ...]


def _combined_unveil_outcomes(
    count: int,
) -> tuple[tuple[float, float, int, int, tuple[float, ...]], ...]:
    """Aggregate outcomes for unveiling ``count`` cells (1 for teal, 3 for blue).

    Two combos can share a key — same blue/teal delta, same queue — while
    differing in how many of the ``count`` cells happened to be a free
    purple, since purple touches none of those three. Their free-purple
    credit must be probability-weighted and summed, not just kept from
    whichever combo the enumeration visits last for that key, so
    ``combined_free`` accumulates ``prob * free_bonus`` rather than
    overwriting — and is returned already weighted, added in
    :func:`_after_unveil` without a second multiply by the key's probability.
    """
    combined_prob: dict[tuple[int, int, tuple[float, ...]], float] = {}
    combined_free: dict[tuple[int, int, tuple[float, ...]], float] = {}
    for combo in product(_SINGLE_CELL_OUTCOMES, repeat=count):
        prob = 1.0
        free_bonus = 0.0
        blue_delta = 0
        teal_delta = 0
        queue: list[float] = []
        for kind, kind_prob in combo:
            prob *= kind_prob
            if kind == OH_FREE:
                free_bonus += OH_CELL_SP[OH_FREE]
            elif kind == OC_CELL:
                continue  # behaves exactly like an unrevealed cell either way
            elif kind == "spB":
                blue_delta += 1
            elif kind == "spT":
                teal_delta += 1
            else:
                queue.append(OH_CELL_SP[kind])
        key = (blue_delta, teal_delta, tuple(sorted(queue, reverse=True)))
        combined_prob[key] = combined_prob.get(key, 0.0) + prob
        combined_free[key] = combined_free.get(key, 0.0) + prob * free_bonus
    return tuple(
        (prob, combined_free[key], key[0], key[1], key[2])
        for key, prob in combined_prob.items()
    )


_SINGLE_UNVEIL_OUTCOMES = _combined_unveil_outcomes(1)
_TRIPLE_UNVEIL_OUTCOMES = _combined_unveil_outcomes(3)


def _settle_queue(clicks_left: int, queue: tuple[float, ...]) -> tuple[int, float]:
    """Spend clicks on the always-take queue, highest first, until either runs out.

    Dominant and order-free in value terms (see module docstring) — the only
    thing order affects is which items still fit inside ``clicks_left``, so
    highest-first is the only order that ever matters.
    """
    banked = 0.0
    remaining = clicks_left
    for value in queue:  # already sorted highest-first at construction
        if remaining <= 0:
            break
        banked += value
        remaining -= 1
    return remaining, banked


def _after_unveil(
    clicks_left: int,
    blue_visible: int,
    teal_visible: int,
    outcomes: tuple[tuple[float, float, int, int, tuple[float, ...]], ...],
) -> float:
    """Expected value of the state reached after an unveil resolves.

    ``clicks_left`` has already been charged for the click that triggered the
    unveil; the unveiled cells themselves cost nothing. ``free_bonus`` is
    already a probability-weighted contribution (see
    :func:`_combined_unveil_outcomes`), so only ``banked`` and the recursive
    value — both constant across every combo folded into this key — are
    scaled by ``prob`` here.
    """
    total = 0.0
    for prob, free_bonus, blue_delta, teal_delta, queue in outcomes:
        settled_clicks, banked = _settle_queue(clicks_left, queue)
        total += free_bonus + prob * (
            banked
            + _value(settled_clicks, blue_visible + blue_delta, teal_visible + teal_delta)
        )
    return total


def _ev_click_hidden(clicks_left: int, blue_visible: int, teal_visible: int) -> float:
    total = _CLICK_FREE_BONUS
    remaining_clicks = clicks_left - 1
    for kind, prob in _CLICK_OUTCOMES:
        if kind == OC_CELL:
            total += prob * _value(remaining_clicks, blue_visible, teal_visible)
        elif kind == "spB":
            total += prob * (
                OH_CELL_SP["spB"]
                + _after_unveil(
                    remaining_clicks, blue_visible, teal_visible, _TRIPLE_UNVEIL_OUTCOMES
                )
            )
        elif kind == "spT":
            total += prob * (
                OH_CELL_SP["spT"]
                + _after_unveil(
                    remaining_clicks, blue_visible, teal_visible, _SINGLE_UNVEIL_OUTCOMES
                )
            )
        else:
            total += prob * (
                OH_CELL_SP[kind] + _value(remaining_clicks, blue_visible, teal_visible)
            )
    return total


def _ev_click_teal(clicks_left: int, blue_visible: int, teal_visible: int) -> float:
    remaining_clicks = clicks_left - 1
    return OH_CELL_SP["spT"] + _after_unveil(
        remaining_clicks, blue_visible, teal_visible - 1, _SINGLE_UNVEIL_OUTCOMES
    )


def _ev_click_blue(clicks_left: int, blue_visible: int, teal_visible: int) -> float:
    remaining_clicks = clicks_left - 1
    return OH_CELL_SP["spB"] + _after_unveil(
        remaining_clicks, blue_visible - 1, teal_visible, _TRIPLE_UNVEIL_OUTCOMES
    )


@lru_cache(maxsize=None)
def _value(clicks_left: int, blue_visible: int, teal_visible: int) -> float:
    """Optimal expected additional SP from here, with no always-take queue pending."""
    if clicks_left <= 0:
        return 0.0
    best = _ev_click_hidden(clicks_left, blue_visible, teal_visible)
    if teal_visible > 0:
        best = max(best, _ev_click_teal(clicks_left, blue_visible, teal_visible))
    if blue_visible > 0:
        best = max(best, _ev_click_blue(clicks_left, blue_visible, teal_visible))
    return best


def solve(clicks_left: int, blue_visible: int = 0, teal_visible: int = 0) -> float:
    """Optimal expected SP still obtainable with ``clicks_left`` clicks.

    ``blue_visible`` / ``teal_visible`` are how many blue / teal spheres are
    currently sitting revealed and unclicked — 0 for a fresh board with no
    always-take colours or blue/teal on it yet.
    """
    return _value(int(clicks_left), int(blue_visible), int(teal_visible))


def best_action(clicks_left: int, blue_visible: int, teal_visible: int) -> str:
    """Which action attains :func:`solve`'s value: ``"hidden"``, ``"spT"`` or ``"spB"``.

    Ties resolve toward the face-down click, since the DP finds them exactly
    equal only to floating-point noise and there is no reason to prefer
    either — it is the caller's job to have already handled the always-take
    queue and free purples before asking this.
    """
    clicks_left, blue_visible, teal_visible = int(clicks_left), int(blue_visible), int(teal_visible)
    options = [("hidden", _ev_click_hidden(clicks_left, blue_visible, teal_visible))]
    if teal_visible > 0:
        options.append(("spT", _ev_click_teal(clicks_left, blue_visible, teal_visible)))
    if blue_visible > 0:
        options.append(("spB", _ev_click_blue(clicks_left, blue_visible, teal_visible)))
    return max(options, key=lambda item: item[1])[0]


def choose_oh_click_dp(
    buttons: list[dict[str, Any]],
    *,
    clicks_spent: int = 0,
    clicks_budget: int = 5,
    rng: Any = None,
) -> dict[str, Any] | None:
    """DP-driven drop-in for :func:`macro.sphere_game.choose_oh_click`.

    Same preference order for anything with a dominant answer — free purple,
    then the highest-paying always-take colour — and only calls into
    :func:`best_action` for the blue-vs-teal-vs-hidden choice, exactly the one
    decision that is not dominant. See the module docstring for why the rest
    needs no solver.
    """
    import random

    chooser = rng or random
    clicks_left = clicks_budget - clicks_spent

    free_purples: list[dict[str, Any]] = []
    always_take: list[dict[str, Any]] = []
    blue_buttons: list[dict[str, Any]] = []
    teal_buttons: list[dict[str, Any]] = []
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
            hidden.append(button)
        elif emoji == "spB":
            blue_buttons.append(button)
        elif emoji == "spT":
            teal_buttons.append(button)
        elif emoji in _ALWAYS_TAKE_KEYS:
            always_take.append(button)

    if free_purples:
        return free_purples[0]
    if always_take:
        return max(always_take, key=lambda b: OH_CELL_SP.get(str(b.get("emoji")), 0.0))
    if clicks_left <= 0:
        return None

    action = best_action(clicks_left, len(blue_buttons), len(teal_buttons))
    if action == "spT" and teal_buttons:
        return teal_buttons[0]
    if action == "spB" and blue_buttons:
        return blue_buttons[0]
    if hidden:
        return chooser.choice(hidden)
    if teal_buttons:
        return teal_buttons[0]
    if blue_buttons:
        return blue_buttons[0]
    return None
