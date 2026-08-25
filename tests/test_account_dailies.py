"""Timing math for account-global ``$p`` / ``$daily``."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from macro.account_dailies import (
    due_commands,
    next_p_reset_at,
    plans_due,
    seconds_until_due,
)


def _at(hour: int, minute: int = 0, second: int = 0) -> dt.datetime:
    return dt.datetime(2026, 8, 25, hour, minute, second, tzinfo=dt.timezone.utc)


def test_next_p_reset_even_and_odd_hours():
    assert next_p_reset_at(_at(0, 0)) == _at(2, 0)
    assert next_p_reset_at(_at(0, 19)) == _at(2, 0)
    assert next_p_reset_at(_at(1, 19)) == _at(2, 0)
    assert next_p_reset_at(_at(2, 0)) == _at(4, 0)
    assert next_p_reset_at(_at(23, 30)) == dt.datetime(
        2026, 8, 26, 0, 0, tzinfo=dt.timezone.utc
    )


def test_due_when_never_sent_and_channel_set():
    account = SimpleNamespace(
        id="a1",
        name="Main",
        token="tok",
        daily_channel_id="ch-1",
        p_next_ready_at="",
        daily_next_ready_at="",
    )
    assert due_commands(account, now=_at(1, 19)) == ("p", "daily")


def test_not_due_without_designated_channel():
    account = SimpleNamespace(
        id="a1",
        name="Main",
        token="tok",
        daily_channel_id="",
        p_next_ready_at="",
        daily_next_ready_at="",
    )
    assert due_commands(account, now=_at(1, 19)) == ()


def test_due_after_stored_deadline():
    account = SimpleNamespace(
        id="a1",
        name="Main",
        token="tok",
        daily_channel_id="ch-1",
        p_next_ready_at=_at(2, 0).isoformat(),
        daily_next_ready_at=_at(20, 0).isoformat(),
    )
    assert due_commands(account, now=_at(1, 59)) == ()
    assert due_commands(account, now=_at(2, 0)) == ("p",)
    assert due_commands(account, now=_at(20, 0)) == ("p", "daily")


def test_plans_prefer_current_run_account():
    alt = SimpleNamespace(
        id="alt",
        name="Alt",
        token="t2",
        daily_channel_id="ch-2",
        p_next_ready_at="",
        daily_next_ready_at=_at(4, 0).isoformat(),
    )
    main = SimpleNamespace(
        id="main",
        name="Main",
        token="t1",
        daily_channel_id="ch-1",
        p_next_ready_at="",
        daily_next_ready_at=_at(4, 0).isoformat(),
    )
    plans = plans_due([alt, main], now=_at(1, 0), prefer_account_id="main")
    assert [p.account_id for p in plans] == ["main", "alt"]
    assert plans[0].commands == ("p",)


def test_seconds_until_due_none_without_channels():
    account = SimpleNamespace(
        id="a1",
        daily_channel_id="",
        p_next_ready_at="",
        daily_next_ready_at="",
    )
    assert seconds_until_due([account], now=_at(1, 0)) is None


def test_seconds_until_due_zero_when_ready():
    account = SimpleNamespace(
        id="a1",
        daily_channel_id="ch-1",
        p_next_ready_at=_at(2, 0).isoformat(),
        daily_next_ready_at=_at(20, 0).isoformat(),
    )
    assert seconds_until_due([account], now=_at(2, 0)) == 0.0
    assert seconds_until_due([account], now=_at(1, 0)) == 3600.0
