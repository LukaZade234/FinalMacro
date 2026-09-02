"""Tests for perk 9 daily sphere-button click tracking."""

from __future__ import annotations

from macro.perk9_daily import (
    PERK9_CLICK_MAX_DEFAULT,
    Perk9DailyRecord,
    apply_perk9_click_from_parse,
    count_perk9_clicks,
    is_perk9_sphere_click,
    sync_perk9_clicks_from_log,
)
from macro.state import AccountState


def test_is_perk9_sphere_click_excludes_megasphere():
    assert is_perk9_sphere_click("spB") is True
    assert is_perk9_sphere_click("spM") is False
    assert is_perk9_sphere_click("SpM") is False


def test_count_perk9_clicks_ignores_minigames_and_megasphere():
    events = [
        {
            "date_key": "2026-08-24",
            "source": "sphere_click",
            "sphere_type": "spB",
        },
        {
            "date_key": "2026-08-24",
            "source": "sphere_click",
            "sphere_type": "spM",
        },
        {
            "date_key": "2026-08-24",
            "source": "minigame_oh",
            "sphere_type": "spY",
        },
        {
            "date_key": "2026-08-23",
            "source": "sphere_click",
            "sphere_type": "spR",
        },
    ]
    assert count_perk9_clicks(events, date_key="2026-08-24") == 1


def test_record_and_rollover_perk9_clicks(monkeypatch):
    monkeypatch.setattr("mudae.clock.utc_date_key", lambda: "2026-08-24")
    state = AccountState()
    state.perk9_clicks_day = "2026-08-23"
    state.perk9_clicks_today = 4
    state.record_perk9_click()
    assert state.perk9_clicks_today == 1
    state.record_perk9_click(2)
    assert state.perk9_clicks_today == 3


def test_apply_perk9_click_uses_mudae_daily_counter():
    state = AccountState()
    state.perk9_clicks_today = 19
    state.perk9_click_max = 20
    assert apply_perk9_click_from_parse(
        state,
        {"sphere_type": "spD", "daily_used": 20, "daily_max": 20},
    )
    assert state.perk9_clicks_today == 20
    assert apply_perk9_click_from_parse(
        state,
        {"sphere_type": "spB", "daily_used": 18, "daily_max": 20},
    )
    assert state.perk9_clicks_today == 18
    before = state.perk9_clicks_today
    assert apply_perk9_click_from_parse(
        state,
        {"sphere_type": "spM", "daily_used": 20, "daily_max": 20},
    ) is False
    assert state.perk9_clicks_today == before


def test_sync_perk9_clicks_from_log(monkeypatch):
    state = AccountState()
    state.perk9_clicks_today = 1
    monkeypatch.setattr("mudae.clock.utc_date_key", lambda: "2026-08-24")
    monkeypatch.setattr("macro.state.utc_date_key", lambda: "2026-08-24")
    monkeypatch.setattr(
        "macro.perk9_daily.get_sphere_events",
        lambda: [
            {"date_key": "2026-08-24", "source": "sphere_click", "sphere_type": "spG"},
            {"date_key": "2026-08-24", "source": "sphere_click", "sphere_type": "spY"},
            {"date_key": "2026-08-24", "source": "sphere_click", "sphere_type": "spM"},
        ],
    )

    sync_perk9_clicks_from_log(state)
    assert state.perk9_clicks_today == 2


def test_perk9_history_shows_the_dark_sphere_not_its_payout(monkeypatch):
    """End to end: a real dark click reaches the Run panel as dark.

    The panel is how the adaptive threshold is checked by eye, so a dark click
    listed as the rainbow it paid out as would misreport both what was clicked
    and how often the rare colours actually turn up.
    """
    from mudae.parsers.sphere import parse_sphere_click
    from macro.perk9_daily import recent_perk9_click_colours

    fields = parse_sphere_click(
        "<:spD:1> turns into <a:spW:2>\n<a:spW:2> **lukazade234 +2,072** (7/20)"
    ).fields

    state = AccountState()
    monkeypatch.setattr("macro.state.utc_date_key", lambda: "2026-08-30")
    assert apply_perk9_click_from_parse(state, fields) is True
    assert state.perk9_click_emojis == ["spD"]

    monkeypatch.setattr(
        "macro.perk9_daily.get_sphere_events",
        lambda: [
            {
                "date_key": "2026-08-30",
                "source": "sphere_click",
                "sphere_type": fields["sphere_type"],
                "sphere_resolved": fields["sphere_resolved"],
            }
        ],
    )
    assert recent_perk9_click_colours(
        4, date_key="2026-08-30", account_id=""
    ) == ["spD"]


def test_run_summary_reports_perk9_from_state():
    from gui.run_summary import build_run_summary

    state = AccountState()
    state.perk9_clicks_today = 6
    state.perk9_click_max = PERK9_CLICK_MAX_DEFAULT
    summary = build_run_summary(state, session_started_at=None)
    assert summary["today"]["perk9_used"] == 6
    assert summary["today"]["perk9_max"] == 20
    assert summary["today"]["perk9_spheres"] == 6


def test_ohu_buttons_clicked_persist():
    import datetime as dt

    from macro.perk9_daily import apply_record_to_state, update_record_from_ohu

    now = dt.datetime(2026, 8, 25, 12, 0, tzinfo=dt.timezone.utc)
    record = update_record_from_ohu(
        Perk9DailyRecord(),
        {
            "perk9_clicked_today": 15,
            "perk9_click_max": 15,
            "megasphere_left": False,
            "sphere_stock": 3924,
            "perk8_refill_minutes": 180,
        },
        now=now,
    )
    assert record.clicks_exhausted is True
    assert record.megasphere_exhausted is True
    assert record.stock == 3924

    state = AccountState()
    apply_record_to_state(state, record, now=now)
    assert state.perk9_clicks_today == 15
    assert state.perk9_click_max == 15


def test_perk9_record_clears_after_midnight():
    import datetime as dt

    from macro.perk9_daily import refresh_exhausted_if_refill_passed

    now = dt.datetime(2026, 8, 25, 23, 0, tzinfo=dt.timezone.utc)
    record = Perk9DailyRecord(
        clicks_exhausted=True,
        last_clicked=15,
        last_click_max=15,
        megasphere_exhausted=True,
        refill_at="2026-08-26T12:00:00+00:00",
        updated_at=now.isoformat(),
    )
    later = dt.datetime(2026, 8, 26, 0, 5, tzinfo=dt.timezone.utc)
    refresh_exhausted_if_refill_passed(record, now=later)
    assert record.clicks_exhausted is False
    assert record.megasphere_exhausted is False
    assert record.last_clicked == 0


# --- the learned perk-9 arrival rate ---


def test_hazard_history_round_trips_through_the_daily_record():
    record = Perk9DailyRecord(
        hazard_history=[{"date": "2026-08-30", "h0": 0.31, "rolls": 800}]
    )
    restored = Perk9DailyRecord.from_dict(record.to_dict())
    assert restored.hazard_history == [{"date": "2026-08-30", "h0": 0.31, "rolls": 800}]


def test_a_second_stretch_the_same_day_accumulates_instead_of_appending():
    """A day is one entry, however many times ``$us`` interrupted the rolling."""
    import datetime as dt

    from macro.perk9_daily import record_hazard_interval

    now = dt.datetime(2026, 8, 30, 12, 0, tzinfo=dt.timezone.utc)
    record = Perk9DailyRecord()
    record_hazard_interval(
        record, pool=154, rolled_from=0, rolled_to=20, rolls=400, now=now
    )
    record_hazard_interval(
        record, pool=154, rolled_from=60, rolled_to=70, rolls=400, now=now
    )
    assert len(record.hazard_history) == 1
    entry = record.hazard_history[0]
    assert entry["date"] == "2026-08-30"
    assert entry["rolls"] == 800


def test_only_the_trailing_window_of_days_is_kept():
    """Accounts get upgraded, so an old day drops out rather than fading."""
    import datetime as dt

    from macro.perk9_daily import PERK9_HAZARD_WINDOW_DAYS, record_hazard_interval

    record = Perk9DailyRecord()
    start = dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.timezone.utc)
    for day in range(PERK9_HAZARD_WINDOW_DAYS + 5):
        record_hazard_interval(
            record,
            pool=154,
            rolled_from=0,
            rolled_to=20,
            rolls=400,
            now=start + dt.timedelta(days=day),
        )
    assert len(record.hazard_history) == PERK9_HAZARD_WINDOW_DAYS
    assert record.hazard_history[0]["date"] == "2026-08-06"
    assert record.hazard_history[-1]["date"] == "2026-08-19"


def test_learned_hazard_weights_days_by_how_much_rolling_backs_them():
    """A 40-roll evening must not outvote a full day of rolling."""
    from macro.perk9_daily import learned_hazard

    history = [
        {"date": "2026-08-29", "h0": 0.30, "rolls": 2000},
        {"date": "2026-08-30", "h0": 0.90, "rolls": 40},
    ]
    assert abs(learned_hazard(history) - 0.312) < 0.001


def test_learned_hazard_is_none_until_enough_rolling_backs_it():
    """Cold start hands the caller ``None``, not a number built from noise."""
    from macro.perk9_daily import PERK9_HAZARD_MIN_ROLLS, learned_hazard

    assert learned_hazard([]) is None
    assert learned_hazard([{"date": "2026-08-30", "h0": 0.9, "rolls": 10}]) is None
    assert (
        learned_hazard(
            [{"date": "2026-08-30", "h0": 0.3, "rolls": PERK9_HAZARD_MIN_ROLLS}]
        )
        is not None
    )


# --- the daily reset (2026-09-02: blue clicked at 00:01) ---


def test_the_reset_clears_rolled_today_so_the_bar_does_not_collapse():
    """``rolled_today`` is day-scoped like every other counter here.

    Leaving yesterday's 148/154 in place after the reset says only 6 characters
    are still rollable, so the adaptive threshold thinks the day is nearly over
    and drops its bar to zero on the very first roll.
    """
    state = AccountState()
    state.perk9_clicks_day = "2026-09-01"
    state.perk9_rolled_today = 148
    state.perk9_roll_pool = 154
    state.perk9_spawns_today = 148
    state.rollover_perk9_if_needed()
    assert state.perk9_rolled_today == 0
    assert state.perk9_roll_pool == 154

    unknown = AccountState()
    unknown.perk9_clicks_day = "2026-09-01"
    unknown.rollover_perk9_if_needed()
    assert unknown.perk9_rolled_today is None, "never measured is not the same as none rolled"


def test_ohu8_does_not_pass_yesterdays_roll_count_off_as_todays():
    """``$ohu`` / ``$ohu8`` share this record but carry no perk-9 roll line.

    Observed 2026-09-02: the first ``$ohu8`` after the reset stamped the record
    fresh for the new day, so ``$ohu9`` was never sent, ``rolled_today`` stayed
    at yesterday's 148, and the macro clicked blue spheres on the first rolls of
    the day.
    """
    import datetime as dt

    from macro.perk9_daily import (
        apply_record_to_state,
        rolled_data_is_stale,
        should_query_ohu9_on_refill,
        update_record_from_ohu,
    )

    record = Perk9DailyRecord(
        last_clicked=20,
        last_click_max=20,
        clicks_exhausted=True,
        refill_at="2026-09-02T00:00:00+00:00",
        updated_at="2026-09-01T23:02:39+00:00",
        rolled_today=148,
        roll_pool=154,
        rolled_synced_at="2026-09-01T23:00:27+00:00",
    )
    after_reset = dt.datetime(2026, 9, 2, 0, 0, 13, tzinfo=dt.timezone.utc)
    record = update_record_from_ohu(
        record,
        {"perk9_clicked_today": 0, "perk9_click_max": 20, "perk8_refill_minutes": 1439},
        now=after_reset,
    )
    assert record.updated_at.startswith("2026-09-02"), "$ohu8 does refresh the record"
    assert record.rolled_synced_at.startswith("2026-09-01"), "but not the roll count"
    assert rolled_data_is_stale(record, now=after_reset)
    assert should_query_ohu9_on_refill(record, now=after_reset)

    state = AccountState()
    apply_record_to_state(state, record, now=after_reset)
    assert state.perk9_rolled_today == 0
    assert state.perk9_roll_pool == 154


def test_a_fresh_ohu9_is_not_re_queried_for_the_rest_of_the_day():
    """The freshness check must not turn into an ``$ohu9`` every hourly cycle."""
    import datetime as dt

    from macro.perk9_daily import should_query_ohu9_on_refill, update_record_from_ohu

    morning = dt.datetime(2026, 9, 2, 6, 0, tzinfo=dt.timezone.utc)
    record = update_record_from_ohu(
        Perk9DailyRecord(),
        {
            "perk9_clicked_today": 3,
            "perk9_click_max": 20,
            "perk9_rolled_today": 40,
            "perk9_roll_pool": 154,
            "perk8_refill_minutes": 1080,
        },
        now=morning,
    )
    assert not should_query_ohu9_on_refill(
        record, now=morning + dt.timedelta(hours=4)
    )
