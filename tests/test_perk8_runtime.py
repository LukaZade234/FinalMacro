"""Tests for the perk-8 query decisions and runtime (no engine)."""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

import pytest

from macro.config import KakeraReactionRules, MacroConfig
from macro.perk8_daily import (
    PERK8_DAILY_KEY,
    Perk8DailyRecord,
    Perk8PriorityMode,
)
from macro.perk8_runtime import (
    Perk8Action,
    Perk8Runtime,
    gate_before_load,
    opportunistic_decision,
    query_decision,
)
from macro.roll_context import RollContext
from macro.state import AccountState
from mudae.types import MessageKind, ParseResult


# --- pure decisions -----------------------------------------------------------


def test_gate_reports_disabled_before_touching_the_store():
    assert gate_before_load(budget_mode=False, commands_blocked=False) is (
        Perk8Action.DISABLED
    )


def test_gate_defers_while_gateway_is_down():
    assert gate_before_load(budget_mode=True, commands_blocked=True) is (
        Perk8Action.DEFER
    )


def test_gate_passes_through_when_usable():
    assert gate_before_load(budget_mode=True, commands_blocked=False) is None


def test_forced_query_overrides_a_cached_record():
    record = Perk8DailyRecord(last_clicked=3, last_click_max=40)
    assert query_decision(record, force=True) is Perk8Action.QUERY


def test_mid_session_uses_cache_when_nothing_changed():
    record = Perk8DailyRecord(last_clicked=3, last_click_max=40)
    assert query_decision(record, force=False) is Perk8Action.USE_CACHED


def test_refill_deadline_outranks_force():
    """Exhausted with a future deadline: never spend an $ohu8 call, forced or not."""
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)
    record = Perk8DailyRecord(
        clicks_exhausted=True,
        refill_at=future.isoformat(),
        last_clicked=40,
        last_click_max=40,
    )
    assert query_decision(record, force=True) is Perk8Action.SKIP_UNTIL_REFILL
    assert query_decision(record, force=False) is Perk8Action.SKIP_UNTIL_REFILL


def test_opportunistic_uses_cache_when_no_refresh_is_due():
    record = Perk8DailyRecord(last_clicked=3, last_click_max=40)
    action = opportunistic_decision(record, pending=False, commands_blocked=False)
    assert action is Perk8Action.USE_CACHED


def test_opportunistic_queries_when_a_refresh_is_pending():
    record = Perk8DailyRecord(last_clicked=3, last_click_max=40)
    action = opportunistic_decision(record, pending=True, commands_blocked=False)
    assert action is Perk8Action.QUERY


def test_opportunistic_defers_a_pending_refresh_while_disconnected():
    """A pending refresh must survive, not be spent, when the gateway is down."""
    record = Perk8DailyRecord(last_clicked=3, last_click_max=40)
    action = opportunistic_decision(record, pending=True, commands_blocked=True)
    assert action is Perk8Action.DEFER


# --- runtime ------------------------------------------------------------------


class _FakeActions:
    def __init__(self, reply: ParseResult | None = None) -> None:
        self.sent: list[str] = []
        self.drained = 0
        self._reply = reply

    def drain_queue(self) -> None:
        self.drained += 1

    async def send_command(self, command: str, *, prefix: str | None = None) -> int:
        self.sent.append(command)
        return 1

    async def wait_for_ohu8(self, *, timeout: float = 12.0) -> ParseResult | None:
        return self._reply


def _ohu8(clicked: int, click_max: int, roll_pool: int = 50) -> ParseResult:
    return ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary="$ohu8",
        fields={
            "perk8_clicked_today": clicked,
            "perk8_click_max": click_max,
            "perk8_roll_pool": roll_pool,
        },
    )


def _make_runtime(
    *,
    reply: ParseResult | None = None,
    budget_mode: bool = True,
    connected: bool = True,
    notification_mode: bool = False,
    daily: dict | None = None,
):
    logs: list[str] = []
    store: dict = {"value": dict(daily or {})}
    actions = _FakeActions(reply)

    async def no_sleep(_seconds: float) -> None:
        return None

    ctx = RollContext(
        actions=actions,
        config=MacroConfig(
            notification_mode=notification_mode,
            kakera_reaction=KakeraReactionRules(
                enabled=True, perk_8_budget_mode=budget_mode
            ),
        ),
        state=AccountState(),
        monitor=SimpleNamespace(is_connected=connected),
        log=logs.append,
        sleep=no_sleep,
    )
    runtime = Perk8Runtime(
        ctx,
        daily_get=lambda: store["value"],
        daily_save=lambda d: store.__setitem__("value", d),
    )
    return runtime, ctx, actions, logs, store


def test_refresh_disabled_clears_mode_and_touches_nothing():
    runtime, ctx, actions, _logs, store = _make_runtime(budget_mode=False)

    action = asyncio.run(runtime.refresh(at_startup=True))

    assert action is Perk8Action.DISABLED
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.INACTIVE.value
    assert actions.sent == []
    assert store["value"] == {}


def test_refresh_defers_and_remembers_while_disconnected():
    runtime, _ctx, actions, _logs, store = _make_runtime(
        connected=False, notification_mode=True
    )

    action = asyncio.run(runtime.refresh(at_startup=True))

    assert action is Perk8Action.DEFER
    assert runtime.pending is True
    assert actions.sent == []
    # Nothing was read or written while the gateway was down.
    assert store["value"] == {}


def test_refresh_sends_ohu8_and_applies_the_reply():
    runtime, ctx, actions, logs, store = _make_runtime(reply=_ohu8(7, 40))

    action = asyncio.run(runtime.refresh(at_startup=True))

    assert action is Perk8Action.QUERY
    assert actions.sent == ["ohu8"]
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.ACTIVE.value
    assert ctx.state.perk8_click_max == 40
    assert ctx.state.kakera_clicks_today == 7
    assert store["value"][PERK8_DAILY_KEY]["last_clicked"] == 7
    assert any("prioritizing perk 8 · clicked 7/40" in line for line in logs)


def test_refresh_marks_done_when_clicks_are_used_up():
    runtime, ctx, _actions, logs, _store = _make_runtime(reply=_ohu8(40, 40))

    asyncio.run(runtime.refresh(at_startup=True))

    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.DONE.value
    assert any("clicks done for today" in line for line in logs)


def test_refresh_timeout_falls_back_to_preset_rules():
    runtime, ctx, actions, logs, _store = _make_runtime(reply=None)

    asyncio.run(runtime.refresh(at_startup=True))

    assert actions.sent == ["ohu8"]
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.ACTIVE.value
    assert any("timeout" in line for line in logs)


def test_refresh_skips_the_call_until_the_refill_lands():
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)
    daily = {
        PERK8_DAILY_KEY: Perk8DailyRecord(
            clicks_exhausted=True,
            refill_at=future.isoformat(),
            updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            last_clicked=40,
            last_click_max=40,
        ).to_dict()
    }
    runtime, ctx, actions, logs, _store = _make_runtime(daily=daily)

    action = asyncio.run(runtime.refresh(at_startup=True))

    assert action is Perk8Action.SKIP_UNTIL_REFILL
    assert actions.sent == []
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.DONE.value
    assert any("skipped until refill" in line for line in logs)


def test_query_clears_a_pending_refresh():
    runtime, _ctx, _actions, _logs, _store = _make_runtime(reply=_ohu8(2, 40))
    runtime.mark_pending()

    asyncio.run(runtime.refresh(at_startup=True))

    assert runtime.pending is False


def test_maybe_refresh_uses_cache_without_sending():
    daily = {
        PERK8_DAILY_KEY: Perk8DailyRecord(last_clicked=3, last_click_max=40).to_dict()
    }
    runtime, ctx, actions, _logs, _store = _make_runtime(daily=daily)

    action = asyncio.run(runtime.maybe_refresh())

    assert action is Perk8Action.USE_CACHED
    assert actions.sent == []
    assert ctx.state.perk8_click_max == 40


def test_maybe_refresh_sends_a_deferred_query_and_clears_the_flag():
    """The whole point of ``pending``: the query it deferred actually goes out.

    The saved record here does not independently warrant a query, so without the
    forced hand-off ``refresh`` would fall back to the cache and leave ``pending``
    stuck on forever.
    """
    runtime, _ctx, actions, _logs, _store = _make_runtime(reply=_ohu8(5, 40))
    runtime.mark_pending()

    action = asyncio.run(runtime.maybe_refresh())

    assert action is Perk8Action.QUERY
    assert actions.sent == ["ohu8"]
    assert runtime.pending is False


def test_deferred_query_is_not_resent_after_a_timeout():
    """The poll loops call in every 30s, so a silent Mudae must not mean $ohu8 spam."""
    runtime, _ctx, actions, _logs, _store = _make_runtime(reply=None)
    runtime.mark_pending()

    asyncio.run(runtime.maybe_refresh())
    assert actions.sent == ["ohu8"]
    assert runtime.pending is False

    asyncio.run(runtime.maybe_refresh())
    assert actions.sent == ["ohu8"]  # still just the one


def test_pending_survives_repeated_checks_while_disconnected():
    runtime, _ctx, actions, _logs, _store = _make_runtime(
        connected=False, notification_mode=True
    )
    runtime.mark_pending()

    for _ in range(3):
        assert asyncio.run(runtime.maybe_refresh()) is Perk8Action.DEFER

    assert runtime.pending is True
    assert actions.sent == []


def test_mark_exhausted_only_applies_while_active():
    runtime, ctx, _actions, logs, store = _make_runtime()
    ctx.state.perk8_priority_mode = Perk8PriorityMode.ACTIVE.value
    ctx.state.kakera_clicks_today = 40

    runtime.mark_exhausted()

    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.DONE.value
    assert store["value"][PERK8_DAILY_KEY]["clicks_exhausted"] is True
    assert any("daily perk 8 clicks used" in line for line in logs)


def test_apply_mode_clamps_clicked_count_to_daily_cap():
    runtime, ctx, _actions, _logs, _store = _make_runtime()
    record = Perk8DailyRecord(last_clicked=67, last_click_max=40)

    runtime.apply_mode(Perk8PriorityMode.DONE, record)

    assert ctx.state.kakera_clicks_today == 40
    assert ctx.state.perk8_click_max == 40
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.DONE.value


def test_apply_mode_does_not_rewind_live_click_count():
    runtime, ctx, _actions, _logs, _store = _make_runtime()
    ctx.state.rollover_kakera_budget_if_needed()
    ctx.state.kakera_clicks_today = 38
    ctx.state.perk8_click_max = 40
    record = Perk8DailyRecord(last_clicked=36, last_click_max=40)

    runtime.apply_mode(Perk8PriorityMode.ACTIVE, record)

    assert ctx.state.kakera_clicks_today == 38
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.ACTIVE.value


def test_apply_mode_catches_up_and_marks_done_when_ohu8_ahead():
    runtime, ctx, _actions, _logs, _store = _make_runtime()
    ctx.state.rollover_kakera_budget_if_needed()
    ctx.state.kakera_clicks_today = 38
    record = Perk8DailyRecord(last_clicked=40, last_click_max=40)

    runtime.apply_mode(Perk8PriorityMode.ACTIVE, record)

    assert ctx.state.kakera_clicks_today == 40
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.DONE.value


def test_mark_exhausted_ignored_when_not_active():
    runtime, ctx, _actions, _logs, store = _make_runtime()
    ctx.state.perk8_priority_mode = Perk8PriorityMode.DONE.value

    runtime.mark_exhausted()

    assert store["value"] == {}


def test_resync_after_timeout_queries_ohu8_when_active():
    runtime, ctx, actions, logs, _store = _make_runtime(reply=_ohu8(40, 40))
    ctx.state.perk8_priority_mode = Perk8PriorityMode.ACTIVE.value
    ctx.state.rollover_kakera_budget_if_needed()
    ctx.state.kakera_clicks_today = 38
    ctx.state.perk8_click_max = 40

    asyncio.run(runtime.resync_after_uncertain_click())

    assert actions.sent == ["ohu8"]
    assert ctx.state.kakera_clicks_today == 40
    assert ctx.state.perk8_priority_mode == Perk8PriorityMode.DONE.value
    assert any("timeout" in line and "$ohu8" in line for line in logs)


def test_resync_after_timeout_skips_when_already_done():
    runtime, ctx, actions, _logs, _store = _make_runtime(reply=_ohu8(40, 40))
    ctx.state.perk8_priority_mode = Perk8PriorityMode.DONE.value

    asyncio.run(runtime.resync_after_uncertain_click())

    assert actions.sent == []


def test_persist_click_progress_writes_current_count():
    runtime, ctx, _actions, _logs, store = _make_runtime()
    ctx.state.kakera_clicks_today = 12

    runtime.persist_click_progress()

    assert store["value"][PERK8_DAILY_KEY]["last_clicked"] == 12
    assert store["value"][PERK8_DAILY_KEY]["updated_at"]


def test_sync_refill_from_tu_records_the_deadline():
    runtime, _ctx, _actions, _logs, store = _make_runtime()

    runtime.sync_refill_from_tu({"perk8_refill_minutes": 90})

    assert store["value"][PERK8_DAILY_KEY]["last_refill_minutes"] == 90


def test_sync_refill_from_tu_ignores_missing_field():
    runtime, _ctx, _actions, _logs, store = _make_runtime()

    runtime.sync_refill_from_tu({"rolls_left": 5})

    assert store["value"] == {}


def test_seconds_until_refill_none_when_budget_mode_off():
    runtime, _ctx, _actions, _logs, _store = _make_runtime(budget_mode=False)
    assert runtime.seconds_until_refill() is None


def test_runtimes_keep_independent_pending_state_per_account():
    """Two accounts must not share a pending refresh."""
    runtime_a, _ca, _aa, _la, _sa = _make_runtime()
    runtime_b, _cb, _ab, _lb, _sb = _make_runtime()

    runtime_a.mark_pending()

    assert runtime_a.pending is True
    assert runtime_b.pending is False


@pytest.mark.parametrize("clicked,expected", [(0, "0/40"), (39, "39/40")])
def test_active_summary_reports_click_progress(clicked, expected):
    runtime, _ctx, _actions, logs, _store = _make_runtime(reply=_ohu8(clicked, 40))

    asyncio.run(runtime.refresh(at_startup=True))

    assert any(expected in line for line in logs)
