"""Sequential ``$p`` / ``$daily`` sends with channel switch-back."""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

from macro.account_dailies import AccountDailyPlan
from macro.account_daily_runtime import COMMAND_GAP_SEC, AccountDailyRuntime
from mudae.types import MessageKind, ParseResult


def _at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 8, 25, hour, minute, tzinfo=dt.timezone.utc)


def test_run_plans_sends_one_account_then_restores_home():
    switches: list[tuple[str, int]] = []
    sent: list[str] = []
    persisted: list[tuple[str, dict]] = []

    async def switch_to(token: str, channel_id: int) -> bool:
        switches.append((token, channel_id))
        return True

    async def send_command(command: str) -> int:
        sent.append(command)
        return 11 if command == "daily" else 10

    async def wait_tick(message_id: int, timeout: float) -> bool:
        return message_id == 11

    async def wait_for(predicate, *, timeout: float = 15.0):
        parsed = ParseResult(
            kind=MessageKind.P,
            summary="$p",
            fields={"p_success": True},
        )
        if predicate(SimpleNamespace(), parsed):
            return SimpleNamespace(), parsed
        return None

    async def sleep(_seconds: float) -> None:
        return None

    runtime = AccountDailyRuntime(
        switch_to=switch_to,
        send_command=send_command,
        wait_for_tick=wait_tick,
        wait_for=wait_for,
        sleep=sleep,
        log=lambda _t: None,
        persist_account=lambda acc_id, fields: persisted.append((acc_id, dict(fields))),
        now=lambda: _at(1, 19),
    )
    plan = AccountDailyPlan(
        account_id="acc-1",
        account_name="Main",
        token="tok-alt",
        channel_profile_id="ch-daily",
        commands=("p", "daily"),
    )

    attempted = asyncio.run(
        runtime.run_plans(
            [plan],
            home_token="tok-home",
            home_channel_id=111,
            discord_channel_id_for=lambda _plan: 222,
        )
    )

    assert attempted is True
    assert sent == ["p", "daily"]
    assert switches[0] == ("tok-alt", 222)
    assert switches[-1] == ("tok-home", 111)
    assert persisted[0][0] == "acc-1"
    assert "p_next_ready_at" in persisted[0][1]
    assert persisted[1][1]["daily_next_ready_at"]


def test_run_plans_pauses_after_switch_and_between_commands():
    events: list[str] = []
    drains = 0

    async def sleep(seconds: float) -> None:
        events.append(f"sleep:{seconds:g}")

    async def wait_for(predicate, *, timeout: float = 15.0):
        parsed = ParseResult(
            kind=MessageKind.P,
            summary="$p",
            fields={"p_success": True},
        )
        if predicate(SimpleNamespace(), parsed):
            return SimpleNamespace(), parsed
        return None

    async def send_command(command: str) -> int:
        events.append(f"send:{command}")
        return 11 if command == "daily" else 10

    def drain() -> None:
        nonlocal drains
        drains += 1
        events.append("drain")

    runtime = AccountDailyRuntime(
        switch_to=AsyncMock(return_value=True),
        send_command=send_command,
        wait_for_tick=AsyncMock(return_value=True),
        wait_for=wait_for,
        sleep=sleep,
        log=lambda _t: None,
        persist_account=lambda *_a, **_k: None,
        drain=drain,
        now=lambda: _at(1, 19),
    )
    plan = AccountDailyPlan(
        account_id="acc-1",
        account_name="Main",
        token="tok",
        channel_profile_id="ch",
        commands=("p", "daily"),
    )
    asyncio.run(
        runtime.run_plans(
            [plan],
            home_token="tok",
            home_channel_id=1,
            discord_channel_id_for=lambda _plan: 2,
        )
    )
    gap = f"sleep:{COMMAND_GAP_SEC:g}"
    assert events[:2] == [gap, "drain"]
    assert events.index("send:p") < events.index(gap, events.index("send:p"))
    p_idx = events.index("send:p")
    daily_idx = events.index("send:daily")
    assert events[p_idx:daily_idx].count(gap) >= 1
    assert drains == 2
    assert events.count(gap) >= 3


def test_run_plans_records_p_cooldown_without_marking_success():
    persisted: list[dict] = []

    async def wait_for(predicate, *, timeout: float = 15.0):
        parsed = ParseResult(
            kind=MessageKind.P,
            summary="$p cooldown",
            fields={"p_success": False, "p_cooldown_minutes": 101},
        )
        if predicate(SimpleNamespace(), parsed):
            return SimpleNamespace(), parsed
        return None

    runtime = AccountDailyRuntime(
        switch_to=AsyncMock(return_value=True),
        send_command=AsyncMock(return_value=10),
        wait_for_tick=AsyncMock(return_value=False),
        wait_for=wait_for,
        sleep=AsyncMock(),
        log=lambda _t: None,
        persist_account=lambda _id, fields: persisted.append(dict(fields)),
        now=lambda: _at(1, 19),
    )
    plan = AccountDailyPlan(
        account_id="acc-1",
        account_name="Main",
        token="tok",
        channel_profile_id="ch",
        commands=("p",),
    )
    asyncio.run(
        runtime.run_plans(
            [plan],
            home_token="tok",
            home_channel_id=1,
            discord_channel_id_for=lambda _plan: 2,
        )
    )
    ready = dt.datetime.fromisoformat(persisted[0]["p_next_ready_at"])
    assert ready == _at(1, 19) + dt.timedelta(minutes=101)


def test_run_plans_skips_when_nothing_to_send():
    switch = AsyncMock(return_value=True)
    runtime = AccountDailyRuntime(
        switch_to=switch,
        send_command=AsyncMock(),
        wait_for_tick=AsyncMock(),
        wait_for=AsyncMock(),
        sleep=AsyncMock(),
        log=lambda _t: None,
        persist_account=lambda *_a, **_k: None,
    )
    attempted = asyncio.run(
        runtime.run_plans(
            [],
            home_token="tok",
            home_channel_id=1,
            discord_channel_id_for=lambda _plan: 2,
        )
    )
    assert attempted is False
    switch.assert_not_awaited()


def test_accounts_round_trip_daily_channel():
    from gui.accounts import AccountProfile

    raw = {
        "id": "abc",
        "name": "Main",
        "token": "t",
        "type": "Main",
        "daily_channel_id": "ch-9",
        "p_next_ready_at": "2026-08-25T02:00:00+00:00",
        "daily_next_ready_at": "2026-08-26T01:19:00+00:00",
    }
    account = AccountProfile.from_dict(raw)
    dumped = account.to_dict()
    assert dumped["daily_channel_id"] == "ch-9"
    assert dumped["p_next_ready_at"].startswith("2026-08-25")
