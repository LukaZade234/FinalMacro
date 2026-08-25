"""Account-scoped daily state on channel profiles."""

from __future__ import annotations

from macro.daily_store import (
    get_account_daily_slice,
    is_legacy_flat_daily_store,
    set_account_daily_slice,
)
from macro.minigame_daily import MINIGAME_DAILY_KEY
from macro.perk8_daily import PERK8_DAILY_KEY, Perk8DailyRecord, load_perk8_record, save_perk8_record
from macro.perk9_daily import PERK9_DAILY_KEY
from macro.us_schedule import US_SCHEDULE_KEY


def test_legacy_flat_store_detected():
    legacy = {PERK8_DAILY_KEY: {"clicks_exhausted": True}}
    assert is_legacy_flat_daily_store(legacy) is True


def test_account_slices_are_isolated():
    channel_daily = set_account_daily_slice(
        {},
        "acc_a",
        save_perk8_record({}, Perk8DailyRecord(last_clicked=3, last_click_max=40)),
    )
    channel_daily = set_account_daily_slice(
        channel_daily,
        "acc_b",
        save_perk8_record({}, Perk8DailyRecord(last_clicked=10, last_click_max=40)),
    )

    a = load_perk8_record(get_account_daily_slice(channel_daily, "acc_a"))
    b = load_perk8_record(get_account_daily_slice(channel_daily, "acc_b"))
    assert a.last_clicked == 3
    assert b.last_clicked == 10


def test_legacy_root_keys_not_migrated_to_accounts():
    legacy = {
        PERK8_DAILY_KEY: Perk8DailyRecord(last_clicked=99, last_click_max=40).to_dict()
    }
    assert is_legacy_flat_daily_store(legacy)
    assert get_account_daily_slice(legacy, "acc_a") == {}


def test_save_strips_legacy_root_keys():
    legacy = {
        PERK8_DAILY_KEY: {"clicks_exhausted": True},
        "acc_a": {PERK8_DAILY_KEY: {"last_clicked": 1}},
    }
    updated = set_account_daily_slice(
        legacy,
        "acc_a",
        save_perk8_record({}, Perk8DailyRecord(last_clicked=5, last_click_max=40)),
    )
    assert PERK8_DAILY_KEY not in updated
    record = load_perk8_record(get_account_daily_slice(updated, "acc_a"))
    assert record.last_clicked == 5


def test_legacy_flat_store_detects_minigames_and_perk9():
    assert is_legacy_flat_daily_store({MINIGAME_DAILY_KEY: {"games": {}}}) is True
    assert is_legacy_flat_daily_store({PERK9_DAILY_KEY: {"clicks_exhausted": True}}) is True
    assert is_legacy_flat_daily_store({US_SCHEDULE_KEY: {"consumed_id": "x"}}) is True
