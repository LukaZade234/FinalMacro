"""Tests for the debounced JSON log writer."""

from __future__ import annotations

import json

from mudae.log_store import DebouncedJsonLog


def test_mark_dirty_batches_writes_until_flush(tmp_path):
    path = tmp_path / "log.json"
    events: list[dict] = []
    writer = DebouncedJsonLog(lambda: path, lambda: events, delay_sec=60.0)

    events.append({"amount": 1})
    writer.mark_dirty()
    events.append({"amount": 2})
    writer.mark_dirty()

    # Debounced: nothing on disk yet.
    assert not path.exists()

    writer.flush()
    assert json.loads(path.read_text()) == [{"amount": 1}, {"amount": 2}]

    # Flush without new changes is a no-op (file untouched, no error).
    path.unlink()
    writer.flush()
    assert not path.exists()


def test_timer_writes_after_delay(tmp_path):
    import time

    path = tmp_path / "log.json"
    events = [{"amount": 5}]
    writer = DebouncedJsonLog(lambda: path, lambda: events, delay_sec=0.05)

    writer.mark_dirty()
    deadline = time.monotonic() + 2.0
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert json.loads(path.read_text()) == [{"amount": 5}]


def test_cancel_pending_drops_scheduled_write(tmp_path):
    path = tmp_path / "log.json"
    events = [{"amount": 1}]
    writer = DebouncedJsonLog(lambda: path, lambda: events, delay_sec=60.0)

    writer.mark_dirty()
    writer.cancel_pending()
    writer.flush()

    assert not path.exists()


def test_kakera_log_flush_writes_pending_events(tmp_path):
    import mudae.kakera_log as kakera_log
    from mudae import event_log

    event_log.append("kakera", {"amount": 7})
    kakera_log._bind_events()
    kakera_log.flush_disk_log()

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["amount"] == 7
    assert json.loads(lines[0])["kind"] == "kakera"
