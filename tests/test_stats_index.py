"""Daily cube + paged Statistics payloads."""

from __future__ import annotations

import datetime as dt

from gui.accounts import AccountProfile
from mudae import event_log, stats_index
from mudae.kakera_log import client_payload as kakera_payload
from mudae.key_log import client_payload as key_payload


def _store(*accounts: AccountProfile):
    return type("S", (), {"accounts": list(accounts), "active_account_id": accounts[0].id if accounts else ""})()


def test_cube_all_time_matches_summing_events():
    event_log.append(
        "kakera",
        {
            "amount": 100,
            "earn_method": "kakera_click",
            "date_key": "2026-08-01",
            "account_id": "a1",
            "account_name": "Main",
            "guild_name": "Guild",
        },
    )
    event_log.append(
        "kakera",
        {
            "amount": 250,
            "earn_method": "bku_reset",
            "date_key": "2026-08-02",
            "account_id": "a1",
            "account_name": "Main",
            "guild_name": "Guild",
        },
    )
    store = _store(AccountProfile(id="a1", name="Main", type="Main"))
    payload = kakera_payload(store)
    assert payload["totals"]["all_time"] == 350
    assert payload["event_count"] == 2
    methods = {row["id"]: row["amount"] for row in payload["by_method"]}
    assert methods == {"kakera_click": 100, "bku_reset": 250}


def test_append_updates_today_cell():
    today = dt.date(2026, 8, 24)
    event_log.append(
        "kakera",
        {
            "amount": 40,
            "earn_method": "kakera_click",
            "date_key": today.isoformat(),
            "account_id": "a1",
            "guild_name": "Guild",
        },
    )
    store = _store(AccountProfile(id="a1", name="Main", type="Main"))
    now = dt.datetime(2026, 8, 24, 15, 0, tzinfo=dt.timezone.utc)
    payload = stats_index.payload("kakera", store, now=now)
    assert payload["totals"]["today"] == 40
    event_log.append(
        "kakera",
        {
            "amount": 10,
            "earn_method": "kakera_click",
            "date_key": today.isoformat(),
            "account_id": "a1",
            "guild_name": "Guild",
        },
    )
    payload = stats_index.payload("kakera", store, now=now)
    assert payload["totals"]["today"] == 50
    assert payload["totals"]["all_time"] == 50


def test_account_and_server_filters_roll_up():
    event_log.append(
        "kakera",
        {
            "amount": 100,
            "earn_method": "kakera_click",
            "date_key": "2026-08-10",
            "account_id": "a1",
            "account_name": "Main",
            "guild_name": "Alpha",
        },
    )
    event_log.append(
        "kakera",
        {
            "amount": 70,
            "earn_method": "kakera_click",
            "date_key": "2026-08-10",
            "account_id": "a2",
            "account_name": "Alt",
            "guild_name": "Alpha",
        },
    )
    event_log.append(
        "kakera",
        {
            "amount": 30,
            "earn_method": "kakera_click",
            "date_key": "2026-08-10",
            "account_id": "a1",
            "account_name": "Main",
            "guild_name": "Beta",
        },
    )
    store = _store(
        AccountProfile(id="a1", name="Main", type="Main"),
        AccountProfile(id="a2", name="Alt", type="Alt"),
    )
    by_account = kakera_payload(store, account="a1")
    assert by_account["totals"]["all_time"] == 130
    assert by_account["event_count"] == 2
    by_server = kakera_payload(store, server="Alpha")
    assert by_server["totals"]["all_time"] == 170
    both = kakera_payload(store, account="a1", server="Beta")
    assert both["totals"]["all_time"] == 30


def test_payload_omits_full_entries_and_caps_recent():
    store = _store(AccountProfile(id="a1", name="Main", type="Main"))
    for i in range(85):
        event_log.append(
            "key",
            {
                "amount": 1,
                "key_type": "chaos",
                "source": "roll",
                "date_key": "2026-08-01",
                "account_id": "a1",
                "guild_name": "Guild",
                "character_name": f"Char{i}",
            },
        )
    payload = key_payload(store)
    assert "entries" not in payload
    assert payload["event_count"] == 85
    assert len(payload["recent"]) == stats_index.PAGE_SIZE
    assert payload["has_more"] is True
    assert payload["recent"][0]["character_name"] == "Char84"
    page = key_payload(store, offset=80, limit=80)
    assert len(page["recent"]) == 5
    assert page["recent"][0]["character_name"] == "Char4"
    assert page["has_more"] is False


def test_month_total_equals_summing_matching_events():
    now = dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc)
    rows = [
        {"amount": 10, "earn_method": "kakera_click", "date_key": "2026-08-01", "account_id": "a1", "guild_name": "G"},
        {"amount": 20, "earn_method": "kakera_click", "date_key": "2026-08-20", "account_id": "a1", "guild_name": "G"},
        {"amount": 99, "earn_method": "kakera_click", "date_key": "2026-07-31", "account_id": "a1", "guild_name": "G"},
    ]
    for row in rows:
        event_log.append("kakera", row)
    store = _store(AccountProfile(id="a1", name="Main", type="Main"))
    payload = stats_index.payload("kakera", store, now=now)
    month_sum = sum(row["amount"] for row in rows if row["date_key"].startswith("2026-08"))
    assert payload["totals"]["month"] == month_sum
    assert payload["totals"]["all_time"] == 129
