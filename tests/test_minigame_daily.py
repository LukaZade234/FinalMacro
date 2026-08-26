"""Tests for minigame daily_resets persist and skip-until-refill."""

from __future__ import annotations

import datetime as dt

from macro.minigame_daily import (
    MINIGAME_DAILY_KEY,
    MinigameDailyEntry,
    MinigameDailyRecord,
    load_minigame_record,
    mark_game_exhausted,
    refresh_minigames_if_refill_passed,
    save_minigame_record,
    seconds_until_minigame_refill,
    should_skip_game,
    should_skip_playable_minigames,
    update_record_from_ohu,
)


def test_save_roundtrip_under_minigames_key():
    record = MinigameDailyRecord(
        games={"oh": MinigameDailyEntry(exhausted=True, total=0)},
        refill_at="2026-08-26T00:00:00+00:00",
    )
    daily = save_minigame_record({}, record)
    assert MINIGAME_DAILY_KEY in daily
    loaded = load_minigame_record(daily)
    assert loaded.entry("oh").exhausted is True
    assert loaded.entry("oh").total == 0


def test_ohu_zeros_mark_playable_exhausted():
    now = dt.datetime(2026, 8, 25, 12, 0, tzinfo=dt.timezone.utc)
    record = update_record_from_ohu(
        MinigameDailyRecord(),
        {
            "oh_total": 0,
            "oc_total": 0,
            "oq_total": 0,
            "ot_total": 2,
            "oh_left": 0,
            "oc_left": 0,
            "oq_left": 0,
            "ot_left": 2,
            "perk8_refill_minutes": 180,
        },
        now=now,
    )
    assert should_skip_playable_minigames(record, now=now) is True
    assert should_skip_game(record, "ot", now=now) is False
    assert record.entry("ot").total == 2


def test_skip_clears_after_utc_midnight():
    now = dt.datetime(2026, 8, 25, 23, 0, tzinfo=dt.timezone.utc)
    record = MinigameDailyRecord(
        games={
            "oh": MinigameDailyEntry(exhausted=True, total=0),
            "oc": MinigameDailyEntry(exhausted=True, total=0),
            "oq": MinigameDailyEntry(exhausted=True, total=0),
        },
        refill_at="2026-08-26T12:00:00+00:00",
        updated_at=now.isoformat(),
    )
    later = dt.datetime(2026, 8, 26, 0, 5, tzinfo=dt.timezone.utc)
    refresh_minigames_if_refill_passed(record, now=later)
    assert should_skip_playable_minigames(record, now=later) is False


def test_mark_game_exhausted_sets_refill():
    now = dt.datetime(2026, 8, 25, 12, 0, tzinfo=dt.timezone.utc)
    record = mark_game_exhausted(
        MinigameDailyRecord(),
        "oh",
        now=now,
        refill_minutes=90,
    )
    assert record.entry("oh").exhausted is True
    assert should_skip_game(record, "oh", now=now) is True
    assert should_skip_playable_minigames(record, now=now) is False


def test_seconds_until_minigame_refill_none_when_not_exhausted():
    now = dt.datetime(2026, 8, 25, 12, 0, tzinfo=dt.timezone.utc)
    record = MinigameDailyRecord(refill_at="2026-08-25T18:00:00+00:00")
    assert seconds_until_minigame_refill(record, now=now) is None


def test_seconds_until_minigame_refill_counts_down():
    now = dt.datetime(2026, 8, 25, 12, 0, tzinfo=dt.timezone.utc)
    record = mark_game_exhausted(
        MinigameDailyRecord(),
        "oh",
        now=now,
        refill_minutes=90,
    )
    mark_game_exhausted(record, "oc", now=now, refill_minutes=90)
    mark_game_exhausted(record, "oq", now=now, refill_minutes=90)
    remaining = seconds_until_minigame_refill(record, now=now)
    assert remaining is not None
    assert 89 * 60 <= remaining <= 90 * 60
