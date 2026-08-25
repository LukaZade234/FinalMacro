"""Run-tab session haul and perk-8 tracker."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from gui.run_summary import build_run_summary


def _at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 8, 25, hour, minute, tzinfo=dt.timezone.utc)


def test_run_summary_sums_session_sphere_sp(monkeypatch):
    start = _at(1, 34)
    monkeypatch.setattr(
        "mudae.kakera_log.get_kakera_events",
        lambda: [],
    )
    monkeypatch.setattr(
        "mudae.key_log.get_key_events",
        lambda: [],
    )
    monkeypatch.setattr(
        "mudae.sphere_log.get_sphere_events",
        lambda: [
            {"amount": 30, "recorded_at": "2026-08-25T01:35:10+00:00"},
            {"amount": 246, "recorded_at": "2026-08-25T01:40:00+00:00"},
            {"amount": 1840, "recorded_at": "2026-08-25T02:10:00+00:00"},
            {"amount": 50, "recorded_at": "2026-08-25T01:00:00+00:00"},
        ],
    )
    summary = build_run_summary(SimpleNamespace(activity_log=[]), start)
    assert summary["session"]["spheres"] == 30 + 246 + 1840
    assert summary["session"]["sphere_value"] == summary["session"]["spheres"]


def test_run_summary_caps_perk8_used_at_daily_max(monkeypatch):
    monkeypatch.setattr("mudae.kakera_log.get_kakera_events", lambda: [])
    monkeypatch.setattr("mudae.key_log.get_key_events", lambda: [])
    monkeypatch.setattr("mudae.sphere_log.get_sphere_events", lambda: [])
    state = SimpleNamespace(
        activity_log=[],
        kakera_clicks_today=67,
        perk8_click_max=40,
        perk8_priority_mode="done",
        perk9_clicks_today=0,
        perk9_click_max=20,
    )
    summary = build_run_summary(state, session_started_at=None)
    assert summary["today"]["perk8_used"] == 40
    assert summary["today"]["perk8_max"] == 40
