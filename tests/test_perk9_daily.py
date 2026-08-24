"""Tests for perk 9 daily sphere-button click tracking."""

from __future__ import annotations

from macro.perk9_daily import (
    PERK9_CLICK_MAX_DEFAULT,
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


def test_sync_perk9_clicks_from_log(monkeypatch):
    import mudae.sphere_log as sphere_log

    state = AccountState()
    state.perk9_clicks_today = 1
    monkeypatch.setattr(
        sphere_log,
        "get_sphere_events",
        lambda: [
            {"date_key": "2026-08-24", "source": "sphere_click", "sphere_type": "spG"},
            {"date_key": "2026-08-24", "source": "sphere_click", "sphere_type": "spY"},
            {"date_key": "2026-08-24", "source": "sphere_click", "sphere_type": "spM"},
        ],
    )
    monkeypatch.setattr("mudae.clock.utc_date_key", lambda: "2026-08-24")

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
