"""Tests for persisted macro session logs."""

from __future__ import annotations

import json
from pathlib import Path

from macro.activity_log import ActivityLog, ActivityLogEntry
from macro.session_log import SessionLogRecorder, format_session_text, session_log_dir
from macro.state import AccountState


def test_session_log_writes_json_and_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("macro.session_log._SESSION_DIR", tmp_path)
    recorder = SessionLogRecorder()
    recorder.start(mode="hourly", account="Main", preset="default", channel="#mudae")
    recorder.write(
        ActivityLogEntry(text="Sent $tu", severity="info"),
        ts="2026-07-07T01:00:00+00:00",
    )
    recorder.write(
        ActivityLogEntry(text="kakera: wait outcome", severity="debug"),
        ts="2026-07-07T01:00:04+00:00",
    )
    path = recorder.finish("finished")
    assert path is not None
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["mode"] == "hourly"
    assert payload["meta"]["reason"] == "finished"
    assert len(payload["lines"]) == 2
    text_path = path.with_suffix(".log")
    assert text_path.is_file()
    text = text_path.read_text(encoding="utf-8")
    assert "Sent $tu" in text
    assert "[debug] kakera: wait outcome" in text


def test_activity_log_debug_is_session_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("macro.session_log._SESSION_DIR", tmp_path)
    state = AccountState()
    recorder = SessionLogRecorder()
    recorder.start(mode="us", account="A", preset="p", channel="c")
    log = ActivityLog(state, session=recorder)
    log.write("visible line")
    log.debug("hidden debug line")
    assert [entry.text for entry in state.activity_log] == ["visible line"]
    path = recorder.finish("stopped")
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    texts = [row["text"] for row in payload["lines"]]
    assert texts == ["visible line", "hidden debug line"]


def test_format_session_text_header() -> None:
    text = format_session_text(
        {
            "meta": {
                "mode": "hourly",
                "account": "Main",
                "preset": "default",
                "channel": "#x",
                "started_at": "2026-07-07T01:00:00+00:00",
                "ended_at": "2026-07-07T01:30:00+00:00",
                "reason": "finished",
                "line_count": 1,
            },
            "lines": [{"ts": "2026-07-07T01:00:01+00:00", "severity": "info", "text": "Roll 1"}],
        }
    )
    assert "# mode=hourly" in text
    assert "Roll 1" in text


def test_session_log_embeds_minigame_board(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("macro.session_log._SESSION_DIR", tmp_path)
    recorder = SessionLogRecorder()
    recorder.start(mode="oh", account="Main", preset="default", channel="#mudae")
    recorder.attach_minigame(
        {
            "game": "oh",
            "clicks": [{"cell": 7, "emoji": "spD", "resolved": ["spP"], "paid": True}],
            "board": ["spU"] * 25,
            "clicks_paid": 1,
            "clicks_budget": 5,
            "base_value": 5,
        }
    )
    path = recorder.finish("finished")
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["minigames"][0]["game"] == "oh"
    assert payload["minigames"][0]["clicks"][0]["resolved"] == ["spP"]
    text = path.with_suffix(".log").read_text(encoding="utf-8")
    assert "$oh" in text
    assert "1/5 paid" in text


def test_session_log_dir_points_under_data() -> None:
    assert session_log_dir().name == "session_logs"
    assert session_log_dir().parent.name == "data"
