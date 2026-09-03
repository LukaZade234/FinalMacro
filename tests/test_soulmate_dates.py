"""Dating soulmates from the Discord id they already stored.

Soulmate rows kept ``time`` alone — a clock time with no date — so every one of
them fell into the same empty date bucket and no per-day view was possible. A
Discord snowflake embeds the millisecond it was minted, so the date was already
on disk; these tests pin that recovery and, just as importantly, pin that a row
without a usable id stays undated rather than being guessed at.
"""

from __future__ import annotations

import datetime as dt

from mudae import event_log
from mudae.clock import snowflake_datetime


def _set_events(rows: list[dict]) -> None:
    import mudae.soulmate_log as soulmate_log

    event_log.replace("soulmate", rows)
    soulmate_log._bind_events()


# --- the helper ---------------------------------------------------------------


def test_snowflake_decodes_to_the_time_the_row_recorded_separately():
    """A real logged pair: the id decodes to the ``time`` stored beside it."""
    stamp = snowflake_datetime(1534578258094461121)
    assert stamp is not None
    assert stamp.tzinfo is dt.UTC
    assert stamp.strftime("%Y-%m-%d %H:%M:%S") == "2026-08-05 15:06:07"


def test_snowflake_refuses_junk_rather_than_returning_an_epoch():
    for bad in (None, "", "nope", 0, -5, [1]):
        assert snowflake_datetime(bad) is None


def test_snowflake_accepts_the_string_form_ids_are_often_stored_as():
    assert snowflake_datetime("1534578258094461121") == snowflake_datetime(1534578258094461121)


# --- the backfill -------------------------------------------------------------


def test_backfill_dates_undated_rows():
    import mudae.soulmate_log as soulmate_log

    _set_events([{"character_name": "Klee", "time": "15:04:00",
                  "message_id": 1534578258094461121}])
    assert soulmate_log._backfill_dates_from_message_id() is True
    row = event_log.events("soulmate")[0]
    assert row["date_key"] == "2026-08-05"
    assert row["recorded_at"].startswith("2026-08-05T15:06:07")


def test_backfill_leaves_a_row_undated_when_the_id_is_unusable():
    """Better an unknown date than every such row landing on today."""
    import mudae.soulmate_log as soulmate_log

    _set_events([{"character_name": "Mystery", "time": "01:00:00"}])
    assert soulmate_log._backfill_dates_from_message_id() is False
    assert "date_key" not in event_log.events("soulmate")[0]


def test_backfill_does_not_touch_a_row_that_already_has_a_date():
    import mudae.soulmate_log as soulmate_log

    _set_events([{"character_name": "Klee", "date_key": "2020-01-01",
                  "message_id": 1534578258094461121}])
    assert soulmate_log._backfill_dates_from_message_id() is False
    assert event_log.events("soulmate")[0]["date_key"] == "2020-01-01"


def test_backfill_reports_no_change_on_a_second_pass():
    """It runs on every load, so it must settle rather than rewrite forever."""
    import mudae.soulmate_log as soulmate_log

    _set_events([{"character_name": "Klee", "message_id": 1534578258094461121}])
    assert soulmate_log._backfill_dates_from_message_id() is True
    assert soulmate_log._backfill_dates_from_message_id() is False


def test_dated_rows_reach_the_stats_cube_under_their_own_day():
    """The point of the backfill: soulmates become a per-day figure."""
    from mudae import stats_index

    _set_events([
        {"character_name": "Klee", "message_id": 1534578258094461121,
         "date_key": "2026-08-05", "account_id": "a", "guild_name": "S"},
        {"character_name": "Elegg", "message_id": 1534578258094461121 + (1 << 22),
         "date_key": "2026-08-05", "account_id": "a", "guild_name": "S"},
    ])
    stats_index.rebuild_kind("soulmate")
    days = {key[0] for key in stats_index._cells["soulmate"]}
    assert days == {"2026-08-05"}
