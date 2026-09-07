"""The perk-8 count is a belief, and a wrong one used to cost a whole night.

Reported 2026-09-07 with this stored record:

    last_clicked: 38 / 40   clicks_exhausted: false
    refill_at: 2026-09-08T00:00Z   updated_at: 2026-09-07T03:01Z

Mudae was at 40/40. `should_query_ohu8_on_refill` only re-asks on exhaustion or
a passed refill, so the macro could not learn it was wrong for ~21 hours, and
`rule_eval` skipped every paid non-perk-8 roll the whole time to save slots that
no longer existed. Power pinned at its cap and two `$dk` went unspent.
"""

from __future__ import annotations

import datetime as dt

from macro.config import KakeraReactionRules, MacroConfig
from macro.perk8_daily import Perk8DailyRecord
from macro.perk8_power import bar_is_pinned, hoarding_wastes_power, snapshot_from_state
from macro.perk8_recheck import (
    PERK8_SILENCE_SEC,
    POWER_PINNED_SEC,
    clear_recheck_flags,
    note_perk8_final_notice,
    note_perk8_seen,
    note_power_level,
    perk8_recheck_reason,
)
from macro.perk8_runtime import Perk8Action, opportunistic_decision
from macro.state import AccountState
from mudae.parsers.kakera import is_perk8_final_click, parse_kakera_claim

NOW = dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc)


def _ago(seconds: float) -> str:
    return (NOW - dt.timedelta(seconds=seconds)).isoformat()


def _state(**kw) -> AccountState:
    base = dict(
        power_percent=155.0,
        power_max_percent=155.0,
        kakera_clicks_today=38,
        perk8_click_max=40,
        perk8_priority_mode="active",
    )
    base.update(kw)
    return AccountState(**base)


def _rules(**kw) -> KakeraReactionRules:
    base = dict(enabled=True, perk_8_budget_mode=True, perk_8_power_save=True)
    base.update(kw)
    return KakeraReactionRules(**base)


# --- the reported record ----------------------------------------------------


def test_the_reported_record_never_re_queried_on_its_own():
    """The gate that existed: 38/40, not exhausted, refill a day out."""
    from macro.perk8_daily import should_query_ohu8_on_refill

    record = Perk8DailyRecord(
        clicks_exhausted=False,
        refill_at="2026-09-08T00:00:12+00:00",
        last_clicked=38,
        last_click_max=40,
    )
    assert should_query_ohu8_on_refill(record, now=NOW) is False
    # …and with nothing else to say otherwise, the cache stands.
    assert opportunistic_decision(
        record, pending=False, commands_blocked=False
    ) is Perk8Action.USE_CACHED
    # A recheck reason is the only thing that gets an $ohu8 sent.
    assert opportunistic_decision(
        record, pending=False, commands_blocked=False, recheck=True
    ) is Perk8Action.QUERY


# --- reason 1: Mudae said so ------------------------------------------------


def test_mudae_announcing_the_last_click_is_recognised():
    msg = (
        "**lukazade234** **+3,030** ($k) **+30** <:kakeraR:1>\n"
        "($op 8) <:kakera:2>/2 turns into 2x <:kakeraR:1> for today."
    )
    assert is_perk8_final_click(msg)
    assert parse_kakera_claim(msg).fields["perk8_final_click"] is True
    assert parse_kakera_claim(msg).fields["amount"] == 3030


def test_an_ordinary_perk8_click_is_not_the_final_notice():
    """The `($op 8)` tag alone rides along on every perk-8 bonus."""
    assert not is_perk8_final_click("**lukazade234** **+1,200** ($k) **+30** <:kakeraR:1>")
    assert "perk8_final_click" not in parse_kakera_claim(
        "**lukazade234** **+1,200** ($k) **+30** <:kakeraR:1>"
    ).fields


def test_the_final_notice_forces_a_recheck_even_at_a_believed_zero():
    """Confirming is how the flag clears, so it must not need remaining > 0."""
    state = _state(kakera_clicks_today=40)
    note_perk8_final_notice(state)
    reason = perk8_recheck_reason(state, remaining=0, power_pinned=False, now=NOW)
    assert reason is not None and reason.key == "final_notice"


def test_the_flag_clears_once_ohu8_has_answered():
    state = _state()
    note_perk8_final_notice(state)
    clear_recheck_flags(state, now=NOW)
    assert state.perk8_final_notice is False
    # The silence clock restarts from the answer, so it does not fire again.
    assert perk8_recheck_reason(state, remaining=2, power_pinned=False, now=NOW) is None


# --- reason 2: two hours without a perk-8 -----------------------------------


def test_two_quiet_hours_with_clicks_believed_left_re_queries():
    state = _state(perk8_last_seen_at=_ago(PERK8_SILENCE_SEC + 60))
    reason = perk8_recheck_reason(state, remaining=2, power_pinned=False, now=NOW)
    assert reason is not None and reason.key == "perk8_silence"
    assert "2.0h" in reason.detail


def test_a_recent_perk8_keeps_the_cache():
    state = _state(perk8_last_seen_at=_ago(PERK8_SILENCE_SEC - 60))
    assert perk8_recheck_reason(state, remaining=2, power_pinned=False, now=NOW) is None


def test_silence_says_nothing_once_the_budget_is_believed_spent():
    """Believing zero is the safe direction to be wrong in — it spends."""
    state = _state(perk8_last_seen_at=_ago(PERK8_SILENCE_SEC * 3))
    assert perk8_recheck_reason(state, remaining=0, power_pinned=False, now=NOW) is None


def test_seeing_a_perk8_character_restarts_the_clock():
    state = _state(perk8_last_seen_at=_ago(PERK8_SILENCE_SEC * 2))
    note_perk8_seen(state, now=NOW)
    assert perk8_recheck_reason(state, remaining=2, power_pinned=False, now=NOW) is None


# --- reason 3: the bar is pinned --------------------------------------------


def test_a_bar_pinned_for_ten_minutes_re_queries():
    state = _state(power_pinned_since=_ago(POWER_PINNED_SEC + 30))
    reason = perk8_recheck_reason(state, remaining=2, power_pinned=True, now=NOW)
    assert reason is not None and reason.key == "power_pinned"


def test_a_briefly_full_bar_is_not_an_alarm():
    state = _state(power_pinned_since=_ago(60))
    assert perk8_recheck_reason(state, remaining=2, power_pinned=True, now=NOW) is None


def test_spending_below_the_cap_clears_the_pinned_clock():
    state = _state(power_pinned_since=_ago(POWER_PINNED_SEC * 2))
    note_power_level(state, pinned=False)
    assert state.power_pinned_since == ""
    assert perk8_recheck_reason(state, remaining=2, power_pinned=False, now=NOW) is None


def test_the_pinned_clock_measures_from_the_first_sighting():
    state = _state(power_pinned_since="")
    note_power_level(state, pinned=True, now=NOW - dt.timedelta(minutes=30))
    first = state.power_pinned_since
    note_power_level(state, pinned=True, now=NOW)
    assert state.power_pinned_since == first


# --- the fail-open reserve --------------------------------------------------


def test_a_full_bar_counts_as_pinned():
    state = _state(power_percent=155.0)
    snap = snapshot_from_state(state, now=NOW)
    assert bar_is_pinned(snap, normal_cost=snap.normal_cost) is True


def test_a_bar_with_room_is_not_pinned():
    state = _state(power_percent=90.0)
    snap = snapshot_from_state(state, now=NOW)
    assert bar_is_pinned(snap, normal_cost=snap.normal_cost) is False


def test_hoarding_is_only_called_wasteful_at_the_cap():
    assert hoarding_wastes_power(_state(power_percent=155.0), _rules(), now=NOW) is True
    assert hoarding_wastes_power(_state(power_percent=80.0), _rules(), now=NOW) is False


def test_an_unknown_power_bar_never_forces_the_hoard_open():
    """No reading is not the same as a full bar."""
    state = _state(power_percent=None)
    assert hoarding_wastes_power(state, _rules(), now=NOW) is False


def test_the_saver_being_off_leaves_the_hoard_alone():
    state = _state(power_percent=155.0)
    assert hoarding_wastes_power(state, _rules(perk_8_power_save=False), now=NOW) is False


def test_a_pinned_bar_lets_paid_non_perk8_clicks_through():
    """The whole point: the wedge cannot outlive one poll of a full bar."""
    from macro.rule_eval import passes_kakera_reaction

    fields = {
        "perk_8": False,
        "buttons": [
            {"custom_id": "1", "emoji": "kakeraR", "is_kakera": True, "disabled": False}
        ],
    }
    rules = _rules()

    wedged = passes_kakera_reaction(
        fields, rules, _state(power_percent=155.0), message_id=1, now=NOW
    )
    saving = passes_kakera_reaction(
        fields, rules, _state(power_percent=60.0), message_id=1, now=NOW
    )

    assert wedged.should_click is True, wedged.reason
    # With room in the bar the hoard still applies, which is the behaviour that
    # makes perk-8 slots worth saving in the first place.
    assert saving.should_click is False, saving.reason
    assert "saving perk-8" in saving.reason
