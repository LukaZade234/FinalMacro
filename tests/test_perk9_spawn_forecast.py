"""Perk 9: forecasting the spawns still to come, and spending the last clicks.

Two independent bugs let the daily click budget expire at 17/20:

1. ``estimate_opportunities_left`` returned ``pool − rolled``, a ceiling on
   *distinct characters* rather than a forecast of *spawns that will happen*.
   The tail of a pool is effectively unrollable, so that number plateaued and
   never fell to ``clicks_left``, which is the condition under which the value
   table drops its bar to zero.
2. ``passes_sphere_reaction`` applied ``types_allowed`` before the budget gate,
   and that list is normally missing blue and teal — five spawns in six — so
   almost nothing reached the bar to be judged by it.

The trap in fixing (1) is the arrival rate. Fitting it on one account's logs
gives ``0.37`` spawns per roll, but that is what share of *this* account's roll
space its perk-9 pool covers; an account with the same pool and a fifth of the
reach sees roughly 23 spawns a day rather than 140, and shipping ``0.37`` to
them is barely better than the bug. So the rate is measured per account from its
own counters, an unmeasured account keeps the old behaviour, and the last-hour
spend-down holds regardless of what the rate says.
"""

from __future__ import annotations

import datetime as dt
from math import exp

from macro.perk9_daily import hazard_interval, learned_hazard
from macro.perk9_threshold import (
    PERK9_SPENDDOWN_MINUTES,
    build_perk9_threshold_context,
    estimate_opportunities_left,
    forecast_spawns,
    is_spend_down_window,
)
from macro.rule_eval import passes_sphere_reaction
from macro.state import AccountState

UTC = dt.timezone.utc

# This account's own fitted rate, over 205 logged roll-hours. It lives here as a
# test fixture and in the docs, never as a shipped default — see the module
# docstring.
OBSERVED_HAZARD = 0.367
POOL = 154


def _state(
    *,
    pool: int | None = POOL,
    rolled: int | None = 0,
    hazard: float | None = None,
    rolls_left: int = 0,
) -> AccountState:
    state = AccountState()
    state.perk9_roll_pool = pool
    state.perk9_rolled_today = rolled
    state.perk9_hazard = hazard
    state.rolls_left = rolls_left
    return state


def _bar(
    state: AccountState,
    *,
    rolls_per_hour: int,
    now: dt.datetime,
    clicks: int,
    spend_down: bool | None = None,
):
    """(spawns forecast, EV bar) exactly as the live reactor would compute them.

    ``spend_down=False`` pins the window open so a test can show what the
    forecast alone does, without the last hour flattening the bar anyway.
    """
    spawns = estimate_opportunities_left(state, rolls_per_hour=rolls_per_hour, now=now)
    ctx = build_perk9_threshold_context(
        opportunities_left=spawns or 0,
        clicks_left=clicks,
        spend_down=is_spend_down_window(now) if spend_down is None else spend_down,
    )
    return spawns, (None if ctx is None else round(ctx.threshold(), 1))


def _rolled_after(rolls: int, *, hazard: float, pool: int = POOL, start: int = 0) -> int:
    """Pool characters rolled after ``rolls`` more rolls, per the urn model."""
    return start + round((pool - start) * (1.0 - exp(-hazard * rolls / pool)))


def _sphere_button(emoji: str) -> dict:
    return {"is_sphere": True, "emoji": emoji, "custom_id": "cmd s0"}


# --- the forecast itself ---


def test_forecast_grows_with_rolls_and_tops_out_at_the_unrolled_pool():
    counts = [
        forecast_spawns(pool=POOL, rolled=0, rolls_left=k, hazard=OBSERVED_HAZARD)
        for k in (0, 100, 500, 3000, 100_000)
    ]
    assert counts == sorted(counts)
    assert counts[0] == 0
    assert counts[-1] == POOL


def test_forecast_respects_what_is_already_rolled():
    assert forecast_spawns(
        pool=POOL, rolled=POOL, rolls_left=5000, hazard=OBSERVED_HAZARD
    ) == 0
    assert forecast_spawns(pool=POOL, rolled=0, rolls_left=500, hazard=0.0) == 0


# --- measuring the rate from the account's own counters ---


def test_a_measured_stretch_recovers_the_rate_that_produced_it():
    rolls = 500
    rolled = _rolled_after(rolls, hazard=0.05)
    depletion, counted = hazard_interval(
        pool=POOL, rolled_from=0, rolled_to=rolled, rolls=rolls
    )
    assert counted == rolls
    assert abs(depletion / counted - 0.05) < 0.002


def test_a_us_burst_between_stretches_does_not_inflate_the_rate():
    """A ``$us`` drain depletes the pool without belonging to the normal pace.

    Cutting it out means ending one stretch before it and starting the next from
    the post-drain ``rolled``: the depletion it caused is respected, its rolls
    are not counted. Dividing the whole day's ``rolled`` by the regular rolls
    alone would instead blame the drain's characters on ordinary rolling.
    """
    first_rolls, second_rolls = 500, 500
    after_first = _rolled_after(first_rolls, hazard=0.05)
    after_burst = after_first + 57  # a $us drain clearing 57 more in half an hour
    after_second = _rolled_after(second_rolls, hazard=0.05, start=after_burst)

    history: list[dict] = []
    depletion = 0.0
    rolls = 0
    for start, end, count in (
        (0, after_first, first_rolls),
        (after_burst, after_second, second_rolls),
    ):
        step, counted = hazard_interval(
            pool=POOL, rolled_from=start, rolled_to=end, rolls=count
        )
        depletion += step
        rolls += counted
    history.append({"date": "2026-09-01", "h0": depletion / rolls, "rolls": rolls})

    assert abs(learned_hazard(history) - 0.05) < 0.005
    # What counting the drain's spawns against regular rolls alone would give.
    naive, _ = hazard_interval(
        pool=POOL, rolled_from=0, rolled_to=after_second, rolls=first_rolls + second_rolls
    )
    assert naive / (first_rolls + second_rolls) > 0.13


def test_a_stretch_that_spawned_nothing_is_evidence_of_a_low_rate():
    depletion, rolls = hazard_interval(
        pool=POOL, rolled_from=40, rolled_to=40, rolls=300
    )
    assert depletion == 0.0
    assert rolls == 300


# --- the low-reach account the fitted constant would have failed ---


def test_a_low_reach_account_clicks_everything_it_can_reach():
    """``pool=154`` but only ~23 spawns a day: 20 clicks against 18 spawns.

    This is the test that fails if anyone hardcodes an arrival rate again. The
    pool ceiling says 153 spawns are still coming and holds a bar in the 30s;
    the account's own measured rate says 18, fewer than the clicks in hand, so
    the right bar is zero.
    """
    morning = dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC)
    spawns, bar = _bar(
        _state(rolled=1, hazard=0.05), rolls_per_hour=21, now=morning, clicks=20
    )
    assert spawns == 18
    assert bar == 0.0

    ceiling_spawns, ceiling_bar = _bar(
        _state(rolled=1), rolls_per_hour=21, now=morning, clicks=20
    )
    assert ceiling_spawns == 153
    assert ceiling_bar > 30.0


def test_an_unmeasured_account_keeps_the_pool_ceiling():
    """Cold start is the old behaviour, never a stranger's fitted number."""
    state = _state(rolled=1)
    assert state.perk9_hazard is None
    spawns, _bar_value = _bar(
        state, rolls_per_hour=62, now=dt.datetime(2026, 9, 1, 1, 0, tzinfo=UTC), clicks=20
    )
    assert spawns == POOL - 1


# --- the two real days from the session logs ---


def test_aug_29_would_no_longer_have_ended_with_four_clicks_in_hand():
    """23:02 UTC, ``rolled 127/154``, 4 clicks left: the bar must be on the floor.

    ``spend_down=False`` throughout, so this is the forecast doing the work and
    not the last hour covering for it.
    """
    at = dt.datetime(2026, 8, 29, 23, 2, tzinfo=UTC)
    spawns, bar = _bar(
        _state(rolled=127, hazard=OBSERVED_HAZARD),
        rolls_per_hour=62,
        now=at,
        clicks=4,
        spend_down=False,
    )
    assert spawns == 4
    assert bar == 0.0

    old_spawns, old_bar = _bar(
        _state(rolled=127), rolls_per_hour=62, now=at, clicks=4, spend_down=False
    )
    assert old_spawns == 27
    assert old_bar > 30.0


def test_a_click_in_hand_at_midday_is_still_worth_saving():
    """Sep 1, 14:05 UTC, ``rolled 136/154``, 1 click: real spawns are still coming."""
    state = _state(rolled=136, hazard=OBSERVED_HAZARD)
    midday = dt.datetime(2026, 9, 1, 14, 5, tzinfo=UTC)
    spawns, bar = _bar(state, rolls_per_hour=62, now=midday, clicks=1)
    assert spawns > 10
    assert bar > 50.0

    # The same state late on, with the spend-down pinned open so this is the
    # forecast relaxing on its own rather than the last-hour rule.
    late = dt.datetime(2026, 9, 1, 22, 30, tzinfo=UTC)
    late_spawns, late_bar = _bar(
        state, rolls_per_hour=62, now=late, clicks=1, spend_down=False
    )
    assert late_spawns < spawns
    assert late_bar < bar


def test_the_forecast_does_not_loosen_the_morning_on_a_high_reach_account():
    """The fix is for the end of the day; the start of it must be unchanged."""
    morning = dt.datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
    _spawns, bar = _bar(
        _state(rolled=1, hazard=OBSERVED_HAZARD),
        rolls_per_hour=62,
        now=morning,
        clicks=20,
    )
    _old_spawns, old_bar = _bar(
        _state(rolled=1), rolls_per_hour=62, now=morning, clicks=20
    )
    assert abs(bar - old_bar) < 1.0
    assert bar > 30.0


# --- the last hour ---


def test_the_spend_down_window_is_the_last_hour_before_the_utc_reset():
    assert is_spend_down_window(dt.datetime(2026, 9, 1, 23, 30, tzinfo=UTC))
    assert is_spend_down_window(
        dt.datetime(2026, 9, 1, 23, 0, tzinfo=UTC)
    ), f"exactly {PERK9_SPENDDOWN_MINUTES} minutes out is inside the window"
    assert not is_spend_down_window(dt.datetime(2026, 9, 1, 22, 59, tzinfo=UTC))


def test_the_last_hour_clicks_blue_even_with_spawns_still_forecast():
    """A click that expires in an hour is worth any sphere, whatever the model says."""
    fields = {"buttons": [_sphere_button("spB")]}
    rules = _rules()

    inside = build_perk9_threshold_context(
        opportunities_left=250, clicks_left=20, spend_down=True
    )
    assert inside.threshold() == 0.0
    assert passes_sphere_reaction(
        fields, rules, AccountState(), threshold_ctx=inside
    ).should_click

    outside = build_perk9_threshold_context(
        opportunities_left=250, clicks_left=20, spend_down=False
    )
    assert not passes_sphere_reaction(
        fields, rules, AccountState(), threshold_ctx=outside
    ).should_click


def test_the_first_roll_after_the_reset_still_refuses_blue():
    """2026-09-02 00:01 UTC: the macro clicked blue on the first rolls of the day.

    ``rolled_today`` was still yesterday's ``148/154`` — the reset had cleared
    every other perk-9 counter but not that one, and the ``$ohu8`` sent at
    00:00 had stamped the record fresh for the day so no ``$ohu9`` ever went
    out. Six spawns left against 20 clicks put the bar on the floor. With the
    reset clearing it the full pool is back in play and blue is refused again.
    """
    state = _state(pool=POOL, rolled=148, hazard=None)
    state.perk9_clicks_day = "2026-09-01"
    state.perk9_spawns_today = 148
    state.rollover_perk9_if_needed()

    just_after_reset = dt.datetime(2026, 9, 2, 0, 1, 50, tzinfo=UTC)
    spawns, bar = _bar(state, rolls_per_hour=62, now=just_after_reset, clicks=20)
    assert spawns == POOL
    assert bar > 30.0

    fields = {"buttons": [_sphere_button("spB")]}
    ctx = build_perk9_threshold_context(opportunities_left=spawns, clicks_left=20)
    assert not passes_sphere_reaction(
        fields, _rules(), AccountState(), threshold_ctx=ctx
    ).should_click


def test_the_spend_down_holds_without_any_learned_rate():
    """The one guarantee that does not depend on the estimate."""
    state = _state(rolled=1)
    assert state.perk9_hazard is None
    late = dt.datetime(2026, 9, 1, 23, 30, tzinfo=UTC)
    spawns, bar = _bar(state, rolls_per_hour=62, now=late, clicks=20)
    assert spawns == POOL - 1  # the old, far-too-high estimate
    assert bar == 0.0


def _rules():
    from macro.config import SphereReactionRules

    # The colours a live preset ships with: no blue, no teal.
    return SphereReactionRules(
        enabled=True,
        budget_aware=True,
        types_allowed=["spY", "spR", "spO", "spW", "spL", "spP", "spD", "spM", "spG"],
    )
