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
