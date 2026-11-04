"""Automatic ``$kl`` from the hourly roll loop (preset › Expert › Kakera loots).

``daily`` runs once per UTC day at the start of the day — after the day's
minigames, before any rolling — and is remembered in the daily record;
``hourly`` runs at the end of every roll session. Neither runs in ``$us``
mode, and neither runs close enough to the next reset to cost rolls.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

from macro.config import KakeraLootRules, MacroConfig
from macro.kakera_loot import KakeraLootRunner
from macro.perk8_daily import mudae_daily_date
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState


def _engine(*, mode="daily", auto=True, minutes_to_reset=40, result=None, daily=None):
    calls: list[float | None] = []
    store = {"value": dict(daily or {})}

    async def run_kl(time_left):
        calls.append(time_left())
        return result if result is not None else {"reason": "insufficient", "batches": 2}

    config = MacroConfig(roll_command="wa", roll_delay_sec=0)
    config.kakera_loot = KakeraLootRules(auto=auto, auto_mode=mode)
    state = AccountState()
    state.rolls_reset_minutes = minutes_to_reset
    engine = RollCycleEngine(
        SimpleNamespace(drain_queue=lambda: None),
        config,
        state,
        SimpleNamespace(macro_active=False),
        daily_resets_get=lambda: store["value"],
        daily_resets_save=lambda value: store.__setitem__("value", value),
        run_kakera_loot=run_kl,
    )
    return engine, calls, store


def _today() -> str:
    return str(mudae_daily_date(dt.datetime.now(dt.timezone.utc)))


def _run(engine, at):
    asyncio.run(engine._maybe_auto_kakera_loot(at=at))


def test_off_does_nothing():
    engine, calls, _ = _engine(auto=False)
    _run(engine, "day_start")
    _run(engine, "hour_end")
    assert calls == []


def test_each_mode_runs_only_at_its_own_moment():
    daily, daily_calls, _ = _engine(mode="daily")
    _run(daily, "hour_end")
    assert daily_calls == []
    hourly, hourly_calls, _ = _engine(mode="hourly")
    _run(hourly, "day_start")
    assert hourly_calls == []


def test_daily_runs_once_and_remembers_the_day():
    engine, calls, store = _engine(mode="daily")
    _run(engine, "day_start")
    _run(engine, "day_start")
    assert len(calls) == 1
    assert store["value"]["kakera_loot"] == {"done_for": _today()}
    # A restart the same day reads the record and does not spend again.
    again, calls_again, _ = _engine(mode="daily", daily=store["value"])
    _run(again, "day_start")
    assert calls_again == []


def test_daily_cut_off_by_the_reset_carries_on_next_hour():
    engine, calls, store = _engine(mode="daily", result={"reason": "deadline", "batches": 30})
    _run(engine, "day_start")
    _run(engine, "day_start")
    assert len(calls) == 2
    assert "kakera_loot" not in store["value"]


def test_hourly_runs_every_hour():
    engine, calls, store = _engine(mode="hourly")
    for _ in range(3):
        _run(engine, "hour_end")
    assert len(calls) == 3
    assert "kakera_loot" not in store["value"]


def test_hour_end_run_stops_90s_before_the_next_rolls_reset():
    engine, calls, _ = _engine(mode="hourly", minutes_to_reset=40)
    _run(engine, "hour_end")
    # 40 minutes to the reset (plus the scheduler's few-second buffer), minus
    # the 90 s margin.
    assert 40 * 60 - 100 < calls[0] <= 40 * 60 - 90 + 30


def test_start_of_day_run_leaves_this_hours_rolls_ten_minutes():
    engine, calls, _ = _engine(mode="daily", minutes_to_reset=40)
    _run(engine, "day_start")
    assert 40 * 60 - 610 < calls[0] <= 40 * 60 - 600 + 30


def test_start_of_day_run_in_the_reset_wake_only_keeps_the_reset_margin():
    """Waiting for rolls: rolling resumes only after the reset, so no reserve."""
    engine, calls, _ = _engine(mode="daily", minutes_to_reset=40)
    engine._waiting_for_hourly_refill = True
    _run(engine, "day_start")
    assert 40 * 60 - 100 < calls[0] <= 40 * 60 - 90 + 30


def test_too_close_to_the_reset_waits_for_next_hour():
    engine, calls, _ = _engine(mode="hourly", minutes_to_reset=2)
    _run(engine, "hour_end")
    assert calls == []
    # With this hour's rolls still to come, 10 minutes is too close as well.
    daily, daily_calls, _ = _engine(mode="daily", minutes_to_reset=10)
    _run(daily, "day_start")
    assert daily_calls == []


def test_a_wrong_loot_value_switches_it_off_for_the_run():
    engine, calls, _ = _engine(mode="hourly", result={"reason": "wrong cost"})
    _run(engine, "hour_end")
    _run(engine, "hour_end")
    assert len(calls) == 1


def test_where_it_is_called():
    """Daily: top of the hourly cycle (after minigames, before the farm step and
    rolling) and the reset wake. Hourly: the three hour-end waits. $us: never."""
    import inspect

    from macro import roll_cycle

    cycle = inspect.getsource(roll_cycle.RollCycleEngine._run_cycle)
    assert cycle.count('_maybe_auto_kakera_loot(at="hour_end")') == 3
    assert cycle.count('_maybe_auto_kakera_loot(at="day_start")') == 1
    assert cycle.index('_maybe_play_daily_minigames()') < cycle.index('at="day_start"') < cycle.index("_run_force_divorce_step()")
    wake = inspect.getsource(roll_cycle.RollCycleEngine._on_scheduled_wake)
    assert wake.index('_maybe_play_daily_minigames()') < wake.index('at="day_start"')
    assert "_maybe_auto_kakera_loot" not in inspect.getsource(roll_cycle.RollCycleEngine._run_us_cycle)


def test_us_mode_is_skipped_even_from_the_shared_wake():
    engine, calls, _ = _engine(mode="daily")
    type(engine).running_mode  # the property exists
    engine.__class__ = type("UsEngine", (type(engine),), {"running_mode": property(lambda self: "us")})
    _run(engine, "day_start")
    assert calls == []


def test_rules_round_trip():
    rules = KakeraLootRules.from_dict({"auto": True, "auto_mode": "hourly", "batch": 100})
    assert (rules.auto, rules.auto_mode, rules.batch) == (True, "hourly", 100)
    assert KakeraLootRules.from_dict({"auto_mode": "nonsense"}).auto_mode == "daily"
    assert KakeraLootRules.from_dict(rules.to_dict()) == rules


def test_runner_stops_before_a_batch_that_would_overrun():
    """`time_left` too short for one more 20 s batch + reply: stop, reason deadline."""

    class Actions:
        def __init__(self):
            self.sent: list[str] = []

        def drain_queue(self):
            pass

        async def send_command(self, command, prefix="$"):
            self.sent.append(command)
            return 1

        async def wait_for(self, predicate, *, timeout=0.0):
            parsed = SimpleNamespace(fields={"kakera_stock": 5_000_000_000, "kl_outcome": "result", "kl_kakera_gained": 0})
            return (SimpleNamespace(), parsed) if predicate(None, parsed) else None

        async def wait_for_mudae_cross(self, message_id, *, timeout=0.0):
            await asyncio.sleep(0)
            return False

    left = {"value": 300.0}

    async def fake_sleep(seconds):
        left["value"] -= seconds

    actions = Actions()
    runner = KakeraLootRunner(
        actions,
        SimpleNamespace(macro_active=False),
        rules=KakeraLootRules(loot_value=500, batch=12000),
        log=lambda _t: None,
        sleep=fake_sleep,
        clock=lambda: 300.0 - left["value"],
        time_left=lambda: left["value"],
    )
    summary = asyncio.run(runner.run())
    assert summary["reason"] == "deadline"
    assert summary["batches"] >= 1
    # Every batch started with room for its cooldown and reply.
    assert left["value"] >= 0
