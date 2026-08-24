"""UTC daily clock vs local display time."""

from __future__ import annotations

import datetime as dt

from macro.activity_log import ActivityLogEntry, activity_log_text
from mudae.clock import local_hhmmss, utc_date_key


def test_utc_date_key_follows_utc_not_local_offset():
    stamp = dt.datetime(2026, 8, 24, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert utc_date_key(stamp) == "2026-08-23"


def test_utc_date_key_naive_is_utc():
    stamp = dt.datetime(2026, 8, 24, 23, 15, 0)
    assert utc_date_key(stamp) == "2026-08-24"


def test_local_hhmmss_matches_astimezone():
    utc = dt.datetime(2026, 8, 24, 14, 27, 32, tzinfo=dt.UTC)
    iso = utc.isoformat(timespec="seconds")
    assert local_hhmmss(iso) == utc.astimezone().strftime("%H:%M:%S")


def test_activity_log_text_shows_local_clock():
    ts = "2026-08-24T14:27:32+00:00"
    text = activity_log_text([ActivityLogEntry(text="Sent $tu", ts=ts)])
    assert text == f"[{local_hhmmss(ts)}] Sent $tu"
