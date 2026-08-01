"""Tests for $ohu8 parsing and perk-8 daily reset logic."""

from __future__ import annotations

import datetime as dt

from macro.perk8_daily import (
    PERK8_MIN_ROLL_POOL,
    Perk8DailyRecord,
    Perk8PriorityMode,
    apply_cached_perk8,
    load_perk8_record,
    mark_perk8_exhausted,
    mode_from_ohu8_fields,
    mudae_daily_date,
    next_daily_reset,
    refresh_exhausted_if_refill_passed,
    save_perk8_record,
    should_query_ohu8_on_refill,
    should_skip_ohu8_until_refill,
    update_record_from_ohu8,
)
from macro.rule_eval import passes_kakera_reaction
from macro.config import KakeraReactionRules
from macro.state import AccountState
from mudae.parsers.ohu8 import (
    is_ohu8_response,
    parse_ohu8,
    parse_perk8_clicked,
    parse_perk8_rolled_pool,
    parse_refill_minutes,
)

_OHU8_SAMPLE = (
    "(Perk 8) Clicked today: **12**/40. Rolled today: **0**/15\n"
    "11h 09 min before the refill."
)

_OHU8_NEW_SAMPLE = (
    "0 $oh left for today, 0 $oc, 0 $oq and 0 $ot (+1 stored).\n"
    "8h 28 min before the refill. 3/15 buttons clicked.\n"
    "Next :spM: has 0% chance to be free.\n"
    "Stock: 2,001 :sp:"
)


def test_ohu8_response_detection():
    assert is_ohu8_response(_OHU8_SAMPLE)
    assert is_ohu8_response(_OHU8_NEW_SAMPLE)
    assert not is_ohu8_response("Clicked today without perk label")


def test_ohu8_parser_fields():
    parsed = parse_ohu8(_OHU8_SAMPLE)
    assert parsed.fields["perk8_clicked_today"] == 12
    assert parsed.fields["perk8_click_max"] == 40
    assert parsed.fields["perk8_rolled_today"] == 0
    assert parsed.fields["perk8_roll_pool"] == 15
    assert parsed.fields["perk8_refill_minutes"] == 11 * 60 + 9


def test_ohu8_new_format_parser_fields():
    parsed = parse_ohu8(_OHU8_NEW_SAMPLE)
    assert parsed.fields["perk8_clicked_today"] == 3
    assert parsed.fields["perk8_click_max"] == 15
    assert parsed.fields["perk8_refill_minutes"] == 8 * 60 + 28


def test_ohu8_clicked_and_rolled_helpers():
    assert parse_perk8_clicked(_OHU8_SAMPLE) == (12, 40)
    assert parse_perk8_rolled_pool(_OHU8_SAMPLE) == (0, 15)
    assert parse_refill_minutes(_OHU8_SAMPLE) == 669


def test_mode_from_ohu8_done_at_max():
    mode = mode_from_ohu8_fields({"perk8_clicked_today": 40, "perk8_click_max": 40})
    assert mode is Perk8PriorityMode.DONE


def test_mode_from_ohu8_insufficient_pool():
    mode = mode_from_ohu8_fields(
        {
            "perk8_clicked_today": 0,
            "perk8_click_max": 40,
            "perk8_roll_pool": PERK8_MIN_ROLL_POOL - 1,
        }
    )
    assert mode is Perk8PriorityMode.INSUFFICIENT_POOL


def test_mode_from_ohu8_active():
    mode = mode_from_ohu8_fields(
        {
            "perk8_clicked_today": 5,
            "perk8_click_max": 40,
            "perk8_roll_pool": 15,
        }
    )
    assert mode is Perk8PriorityMode.ACTIVE


def test_should_skip_ohu8_until_refill():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2026-06-23T20:00:00+00:00",
        last_clicked=40,
        last_click_max=40,
    )
    assert should_skip_ohu8_until_refill(record, now=now) is True
    assert should_query_ohu8_on_refill(record, now=now) is False


def test_should_query_ohu8_on_refill_after_refill():
    now = dt.datetime(2026, 6, 23, 21, 0, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2026-06-23T20:00:00+00:00",
        last_clicked=40,
        last_click_max=40,
    )
    assert should_skip_ohu8_until_refill(record, now=now) is False
    assert should_query_ohu8_on_refill(record, now=now) is True


def test_refresh_exhausted_clears_on_new_utc_day_before_refill_at():
    """Exhausted yesterday but refill_at still in future — daily reset already happened."""
    now = dt.datetime(2026, 7, 7, 0, 14, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2026-07-07T22:10:31+00:00",
        updated_at="2026-07-06T22:10:31+00:00",
    )
    refresh_exhausted_if_refill_passed(record, now=now)
    assert record.clicks_exhausted is False
    assert should_skip_ohu8_until_refill(record, now=now) is False
    assert should_query_ohu8_on_refill(record, now=now) is False


def test_should_skip_ohu8_when_exhausted_without_refill_at():
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="",
        last_clicked=40,
        last_click_max=40,
    )
    assert should_skip_ohu8_until_refill(record) is True
    assert should_query_ohu8_on_refill(record) is False


def test_should_query_ohu8_on_refill_when_exhausted_flag_but_clicks_remain():
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2099-01-01T00:00:00+00:00",
        last_clicked=3,
        last_click_max=40,
    )
    assert should_skip_ohu8_until_refill(record) is False
    assert should_query_ohu8_on_refill(record) is True


def test_startup_queries_even_with_same_day_cache():
    """Macro start always live-queries unless clicks are exhausted until refill."""
    now = dt.datetime(2026, 7, 8, 15, 23, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=False,
        updated_at="2026-07-08T10:00:00+00:00",
        last_clicked=10,
        last_click_max=40,
    )
    assert should_skip_ohu8_until_refill(record, now=now) is False
    assert should_query_ohu8_on_refill(record, now=now) is False


def test_fresh_record_not_skipped_at_startup():
    record = Perk8DailyRecord()
    assert should_skip_ohu8_until_refill(record) is False
    assert should_query_ohu8_on_refill(record) is False


def test_refresh_exhausted_if_refill_passed_clears_flag():
    now = dt.datetime(2026, 6, 23, 21, 0, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2026-06-23T20:00:00+00:00",
        last_clicked=40,
        last_click_max=40,
    )
    refresh_exhausted_if_refill_passed(record, now=now)
    assert record.clicks_exhausted is False


def test_apply_cached_perk8_stale_exhausted_below_cap():
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        last_clicked=3,
        last_click_max=40,
    )
    assert apply_cached_perk8(record) is Perk8PriorityMode.ACTIVE


def test_update_record_from_ohu8_active_keeps_refill_deadline():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record, mode = update_record_from_ohu8(
        Perk8DailyRecord(),
        {
            "perk8_clicked_today": 3,
            "perk8_click_max": 40,
            "perk8_roll_pool": 20,
            "perk8_refill_minutes": 508,
        },
        now=now,
    )
    assert mode is Perk8PriorityMode.ACTIVE
    assert record.clicks_exhausted is False
    assert record.refill_at == "2026-06-23T20:28:00+00:00"


def test_update_record_from_ohu8_done_without_refill_sets_fallback():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record, mode = update_record_from_ohu8(
        Perk8DailyRecord(),
        {
            "perk8_clicked_today": 40,
            "perk8_click_max": 40,
            "perk8_roll_pool": 20,
        },
        now=now,
    )
    assert mode is Perk8PriorityMode.DONE
    assert record.clicks_exhausted is True
    assert record.refill_at == "2026-06-24T00:00:00+00:00"


def test_update_record_from_ohu8_marks_done_with_refill():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record, mode = update_record_from_ohu8(
        Perk8DailyRecord(),
        {
            "perk8_clicked_today": 40,
            "perk8_click_max": 40,
            "perk8_roll_pool": 20,
            "perk8_refill_minutes": 480,
        },
        now=now,
    )
    assert mode is Perk8PriorityMode.DONE
    assert record.clicks_exhausted is True
    assert record.refill_at == "2026-06-23T20:00:00+00:00"


def test_mark_perk8_exhausted_uses_last_refill_minutes():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record = mark_perk8_exhausted(
        Perk8DailyRecord(last_refill_minutes=120, last_click_max=40, last_clicked=39),
        now=now,
        clicked_today=40,
    )
    assert record.clicks_exhausted is True
    assert record.last_clicked == 40
    assert record.refill_at == "2026-06-23T14:00:00+00:00"


def test_mark_perk8_exhausted_sets_fallback_without_refill_minutes():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record = mark_perk8_exhausted(Perk8DailyRecord(last_click_max=40), now=now)
    assert record.clicks_exhausted is True
    assert record.refill_at == "2026-06-24T00:00:00+00:00"


def test_next_daily_reset_is_always_utc_midnight():
    """Dailies reset at 00:00 UTC; a server's shifted hourly reset must not move it."""
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    assert next_daily_reset(now) == dt.datetime(
        2026, 6, 24, 0, 0, tzinfo=dt.timezone.utc
    )
    late = dt.datetime(2026, 6, 23, 23, 59, tzinfo=dt.timezone.utc)
    assert next_daily_reset(late) == dt.datetime(
        2026, 6, 24, 0, 0, tzinfo=dt.timezone.utc
    )


def test_mudae_daily_date_is_the_utc_date():
    # 00:30 UTC already belongs to the new daily cycle.
    now = dt.datetime(2026, 7, 9, 0, 30, tzinfo=dt.timezone.utc)
    assert mudae_daily_date(now) == dt.date(2026, 7, 9)
    assert mudae_daily_date(
        dt.datetime(2026, 7, 8, 23, 59, tzinfo=dt.timezone.utc)
    ) == dt.date(2026, 7, 8)


def test_mark_perk8_exhausted_falls_back_to_utc_midnight():
    now = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
    record = mark_perk8_exhausted(Perk8DailyRecord(last_click_max=40), now=now)
    assert record.refill_at == "2026-06-24T00:00:00+00:00"


def test_refresh_exhausted_clears_once_utc_day_rolls():
    """Past 00:00 UTC the daily cycle advanced, so the exhausted flag is stale."""
    now = dt.datetime(2026, 7, 9, 0, 14, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2026-07-09T14:00:00+00:00",
        updated_at="2026-07-08T22:10:31+00:00",
    )
    refresh_exhausted_if_refill_passed(record, now=now)
    assert record.clicks_exhausted is False
    assert should_skip_ohu8_until_refill(record, now=now) is False


def test_refresh_exhausted_holds_within_the_same_utc_day():
    now = dt.datetime(2026, 7, 8, 23, 30, tzinfo=dt.timezone.utc)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at="2026-07-09T00:00:00+00:00",
        updated_at="2026-07-08T22:10:31+00:00",
    )
    refresh_exhausted_if_refill_passed(record, now=now)
    assert record.clicks_exhausted is True
    assert should_skip_ohu8_until_refill(record, now=now) is True


def test_parse_refill_minutes_alternate_formats():
    assert parse_refill_minutes("11h 09 min before the refill") == 669
    assert parse_refill_minutes("8h 28 min before the refill") == 508
    assert parse_refill_minutes("3 hours before the refill") == 180
    assert parse_refill_minutes("45 minutes before the refill") == 45


def test_daily_resets_round_trip():
    daily = save_perk8_record({}, Perk8DailyRecord(last_clicked=10, last_click_max=40))
    loaded = load_perk8_record(daily)
    assert loaded.last_clicked == 10
    assert loaded.last_click_max == 40


def test_apply_cached_perk8_done():
    record = Perk8DailyRecord(clicks_exhausted=True, refill_at="2099-01-01T00:00:00+00:00")
    assert apply_cached_perk8(record) is Perk8PriorityMode.DONE


def test_apply_cached_perk8_insufficient_pool():
    record = Perk8DailyRecord(last_roll_pool=5)
    assert apply_cached_perk8(record) is Perk8PriorityMode.INSUFFICIENT_POOL


def _kakera_fields(buttons, *, perk_8=None):
    fields = {
        "buttons": buttons,
        "keys": [],
        "character_name": "Test",
    }
    if perk_8 is not None:
        fields["perk_8"] = perk_8
    return fields


def _kakera_buttons(*emojis):
    return [
        {
            "is_kakera": True,
            "disabled": False,
            "custom_id": f"k-{emoji}",
            "emoji": emoji,
            "kind": "kakera",
        }
        for emoji in emojis
    ]


def test_kakera_active_skips_non_perk_8_while_budget_remains():
    rules = KakeraReactionRules(
        enabled=True, perk_8_budget_mode=True
    )
    state = AccountState(perk8_priority_mode="active", perk8_click_max=40)
    state.kakera_clicks_today = 5
    fields = _kakera_fields(_kakera_buttons("kakeraR"), perk_8=False)
    decision = passes_kakera_reaction(fields, rules, state)
    assert decision.buttons == []
    assert "saving" in decision.reason.lower()


def test_kakera_active_clicks_purple_while_budget_remains():
    rules = KakeraReactionRules(
        enabled=True,
        types_allowed=["kakeraP", "kakeraR"],
        perk_8_budget_mode=True,
    )
    state = AccountState(perk8_priority_mode="active", perk8_click_max=40)
    state.kakera_clicks_today = 5
    fields = _kakera_fields(_kakera_buttons("kakeraP", "kakeraR"), perk_8=False)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "kakeraP"
    assert "budget bypass" in decision.reason


def test_kakera_active_custom_budget_bypass_types():
    rules = KakeraReactionRules(
        enabled=True,
        types_allowed=["kakeraP", "kakeraT", "kakeraR"],
        perk_8_budget_mode=True,
        perk_8_budget_bypass_types=["kakeraT"],
    )
    state = AccountState(perk8_priority_mode="active", perk8_click_max=40)
    fields = _kakera_fields(_kakera_buttons("kakeraP", "kakeraT", "kakeraR"), perk_8=False)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "kakeraT"


def test_kakera_done_clicks_equally():
    rules = KakeraReactionRules(
        enabled=True, perk_8_budget_mode=True
    )
    state = AccountState(perk8_priority_mode="done", perk8_click_max=40)
    state.kakera_clicks_today = 5
    fields = _kakera_fields(_kakera_buttons("kakeraR"), perk_8=False)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1


def test_kakera_insufficient_pool_bypasses_require_perk_8():
    rules = KakeraReactionRules(
        enabled=True,
        require_perk_8=True,
        require_chaos_key=True,
        perk_8_budget_mode=True,
    )
    state = AccountState(perk8_priority_mode="insufficient_pool", perk8_click_max=40)
    fields = _kakera_fields(_kakera_buttons("kakeraO"), perk_8=False)
    fields["keys"] = [{"type": "chaos", "level": 10}]
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "kakeraO"


def test_kakera_active_still_requires_perk_8_when_enabled():
    rules = KakeraReactionRules(
        enabled=True,
        require_perk_8=True,
        require_chaos_key=True,
        perk_8_budget_mode=True,
    )
    state = AccountState(perk8_priority_mode="active")
    fields = _kakera_fields(_kakera_buttons("kakeraO"), perk_8=False)
    fields["keys"] = [{"type": "chaos", "level": 10}]
    decision = passes_kakera_reaction(fields, rules, state)
    assert decision.buttons == []
    assert "perk 8" in decision.reason.lower()
