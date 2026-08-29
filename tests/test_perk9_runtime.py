"""Perk-9 ``$ohu9`` runtime: when to query, and applying the answer."""

from __future__ import annotations

import asyncio
import datetime as dt

from macro.config import MacroConfig, SphereReactionRules
from macro.perk9_daily import (
    Perk9DailyRecord,
    should_query_ohu9_on_refill,
    should_skip_ohu9_until_refill,
)
from macro.perk9_runtime import (
    Perk9Action,
    Perk9Runtime,
    gate_before_load,
    merge_click_count,
    merge_spawn_count,
    query_decision,
)
from macro.perk9_threshold import adaptive_status
from macro.state import AccountState
from mudae.parsers.ohu import is_ohu9_response, parse_ohu
from mudae.parsers.ohu8 import is_ohu8_response

# Verbatim $ohu9 reply (character list trimmed to three names).
OHU9_SAMPLE = (
    "0 $oh left for today, 0 $oc, 0 $oq and 0 $ot (+30 stored).\n"
    "8h 40 min before the refill. 10/20 buttons clicked.\n"
    "No :spM: left today.\n"
    "Stock: 24,248 :sp:\n"
    "\n"
    "(Perk 9) Rolled today: 60/154\n"
    "2B, A2, Agnes Tachyon"
)
OHU8_SAMPLE = (
    "0 $oh left for today, 0 $oc, 0 $oq and 0 $ot (+1 stored).\n"
    "8h 28 min before the refill. 3/15 buttons clicked.\n"
    "(Perk 8) Clicked today: 12/40\n"
    "(Perk 8) Rolled today: 30/99"
)
# Anchored to the real clock: the decision helpers call ``utc_now()`` themselves,
# so a frozen date would drift past the refill deadlines below.
_NOW = dt.datetime.now(dt.timezone.utc)


class _Actions:
    def __init__(self, reply=None):
        self.sent: list[str] = []
        self._reply = reply

    def drain_queue(self) -> None:
        pass

    async def send_command(self, command, *, prefix=None):
        self.sent.append(command)
        return 1

    async def wait_for_ohu9(self, *, timeout=12.0):
        return self._reply


class _Ctx:
    def __init__(self, config, state, actions):
        self.config = config
        self.state = state
        self.actions = actions
        self.commands_blocked = False
        self.logs: list[str] = []

    def log(self, text: str) -> None:
        self.logs.append(text)

    def notify(self) -> None:
        pass

    async def sleep(self, seconds: float) -> None:
        pass


def _runtime(*, reply=None, budget_aware=True, state=None):
    config = MacroConfig()
    config.sphere_reaction = SphereReactionRules(enabled=True, budget_aware=budget_aware)
    state = state or AccountState()
    store: dict = {}
    ctx = _Ctx(config, state, _Actions(reply))
    runtime = Perk9Runtime(
        ctx,
        daily_get=lambda: store,
        daily_save=lambda d: store.update(d),
    )
    return runtime, ctx, store


# --- parsing / detection ---


def test_real_ohu9_sample_parses_every_field():
    fields = parse_ohu(OHU9_SAMPLE).fields
    assert fields["perk9_clicked_today"] == 10
    assert fields["perk9_click_max"] == 20
    assert fields["perk9_rolled_today"] == 60
    assert fields["perk9_roll_pool"] == 154
    assert fields["perk8_refill_minutes"] == 8 * 60 + 40
    assert fields["megasphere_left"] is False
    assert fields["sphere_stock"] == 24248


def test_ohu9_detector_requires_the_perk9_line():
    assert is_ohu9_response(OHU9_SAMPLE)
    assert not is_ohu9_response(OHU8_SAMPLE)


def test_ohu8_reply_would_otherwise_satisfy_a_generic_ohu_wait():
    """Both share the availability header, so the wait must key on ``(Perk 9)``."""
    assert is_ohu8_response(OHU9_SAMPLE)
    assert not is_ohu9_response(OHU8_SAMPLE)


# --- decisions ---


def test_gate_blocks_when_disabled_or_disconnected():
    assert gate_before_load(budget_mode=False, commands_blocked=False) is Perk9Action.DISABLED
    assert gate_before_load(budget_mode=True, commands_blocked=True) is Perk9Action.DEFER
    assert gate_before_load(budget_mode=True, commands_blocked=False) is None


def test_startup_queries_once():
    record = Perk9DailyRecord()
    assert query_decision(record, force=True, clicks_used=0, click_max=20) is Perk9Action.QUERY


def test_mid_session_uses_local_tracking_instead_of_requerying():
    record = Perk9DailyRecord(last_clicked=3, last_click_max=20, updated_at=_iso(_NOW))
    action = query_decision(record, force=False, clicks_used=5, click_max=20)
    assert action is Perk9Action.USE_CACHED


def test_reaching_the_cap_queries_once_to_confirm():
    record = Perk9DailyRecord(last_clicked=18, last_click_max=20, updated_at=_iso(_NOW))
    action = query_decision(record, force=False, clicks_used=20, click_max=20)
    assert action is Perk9Action.QUERY


def test_confirmed_exhausted_then_skips_until_refill():
    record = Perk9DailyRecord(
        clicks_exhausted=True,
        last_clicked=20,
        last_click_max=20,
        refill_at=_iso(_NOW + dt.timedelta(hours=3)),
        updated_at=_iso(_NOW),
    )
    action = query_decision(record, force=False, clicks_used=20, click_max=20)
    assert action is Perk9Action.SKIP_UNTIL_REFILL
    assert should_skip_ohu9_until_refill(record, now=_NOW)


def test_refill_passed_reopens_the_query():
    record = Perk9DailyRecord(
        clicks_exhausted=True,
        last_clicked=20,
        last_click_max=20,
        refill_at=_iso(_NOW - dt.timedelta(minutes=1)),
        updated_at=_iso(_NOW - dt.timedelta(hours=9)),
    )
    assert should_query_ohu9_on_refill(record, now=_NOW)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


# --- merging ---


def test_click_merge_catches_up_and_tolerates_small_lag():
    assert merge_click_count(live=3, reported=7) == 7
    assert merge_click_count(live=8, reported=7) == 8
    assert merge_click_count(live=20, reported=2) == 2


def test_spawn_merge_never_drops_below_what_was_seen():
    assert merge_spawn_count(live=12, reported=60) == 60
    assert merge_spawn_count(live=60, reported=12) == 60


# --- runtime ---


def test_refresh_sends_ohu9_and_syncs_state():
    parsed = parse_ohu(OHU9_SAMPLE)
    runtime, ctx, store = _runtime(reply=parsed)
    action = asyncio.run(runtime.refresh(at_startup=True))
    assert action is Perk9Action.QUERY
    assert ctx.actions.sent == ["ohu9"]
    assert ctx.state.perk9_clicks_today == 10
    assert ctx.state.perk9_click_max == 20
    assert ctx.state.perk9_rolled_today == 60
    assert ctx.state.perk9_roll_pool == 154
    assert store["perk9"]["roll_pool"] == 154


def test_refresh_is_a_noop_when_budget_mode_is_off():
    runtime, ctx, _ = _runtime(reply=None, budget_aware=False)
    assert asyncio.run(runtime.refresh(at_startup=True)) is Perk9Action.DISABLED
    assert ctx.actions.sent == []


def test_timeout_keeps_local_counts():
    state = AccountState()
    state.perk9_clicks_today = 4
    runtime, ctx, _ = _runtime(reply=None, state=state)
    asyncio.run(runtime.refresh(at_startup=True))
    assert ctx.state.perk9_clicks_today == 4
    assert any("timeout" in line for line in ctx.logs)


def test_second_refresh_does_not_resend():
    parsed = parse_ohu(OHU9_SAMPLE)
    runtime, ctx, _ = _runtime(reply=parsed)
    asyncio.run(runtime.refresh(at_startup=True))
    asyncio.run(runtime.refresh())
    assert ctx.actions.sent == ["ohu9"]


def test_deferred_while_disconnected_then_queries_on_reconnect():
    parsed = parse_ohu(OHU9_SAMPLE)
    runtime, ctx, _ = _runtime(reply=parsed)
    ctx.commands_blocked = True
    assert asyncio.run(runtime.refresh(at_startup=True)) is Perk9Action.DEFER
    assert runtime.pending
    ctx.commands_blocked = False
    assert asyncio.run(runtime.maybe_refresh()) is Perk9Action.QUERY
    assert ctx.actions.sent == ["ohu9"]


def test_local_click_and_spawn_tracking_between_syncs():
    state = AccountState()
    state.record_perk9_spawn()
    state.record_perk9_spawn()
    state.record_perk9_click()
    state.record_perk9_click_emoji("spT")
    assert state.perk9_spawns_today == 2
    assert state.perk9_clicks_today == 1
    assert state.perk9_click_emojis == ["spT"]


def test_untracked_clicks_become_face_down():
    state = AccountState()
    state.perk9_clicks_today = 7
    state.record_perk9_click_emoji("spR")
    state.sync_perk9_unknown_clicks()
    assert state.perk9_unknown_clicks == 6


# --- Run panel payload ---


def test_adaptive_status_is_off_without_the_toggle():
    rules = SphereReactionRules(enabled=True, budget_aware=False)
    assert adaptive_status(AccountState(), rules) == {"enabled": False}


def test_adaptive_status_reports_counts_history_and_bar():
    state = AccountState()
    state.perk9_click_max = 20
    state.perk9_clicks_today = 3
    state.perk9_spawns_today = 40
    state.perk9_spawns_at_sync = 40
    state.perk9_roll_pool = 154
    state.perk9_rolled_today = 44
    state.record_perk9_click_emoji("spT")
    state.record_perk9_click_emoji("spR")
    state.sync_perk9_unknown_clicks()

    rules = SphereReactionRules(enabled=True, budget_aware=True)
    status = adaptive_status(state, rules)
    assert status["enabled"]
    assert status["clicks_used"] == 3
    assert status["clicks_left"] == 17
    assert status["spawns_seen"] == 40
    assert status["spawns_left"] == 110
    # Newest first, with the one untracked click trailing as face-down.
    assert status["history"] == ["spR", "spT", "spU"]
    assert status["allowed"]
    assert status["threshold"] is not None


def test_adaptive_status_reports_when_the_set_changes_each_way():
    state = AccountState()
    state.perk9_click_max = 20
    state.perk9_roll_pool = 400
    state.perk9_rolled_today = 0
    rules = SphereReactionRules(enabled=True, budget_aware=True)
    status = adaptive_status(state, rules)
    # Running low on spawns opens the bar; running low on clicks tightens it.
    assert status["looser_at"] is not None
    assert status["looser_at"] < status["spawns_left"]
    assert not set(status["looser_adds"]) & set(status["allowed"])
    if status["stricter_at"] is not None:
        assert status["stricter_at"] < status["clicks_left"]
        assert set(status["stricter_drops"]) <= set(status["allowed"])


# --- SphereReactor integration (the path that actually spends the budget) ---


class _ReactorActions:
    def __init__(self, *, confirm=True):
        self.clicked: list[str] = []
        self._confirm = confirm

    async def click_button(self, message_id, custom_id):
        self.clicked.append(custom_id)
        return True

    async def wait_for_sphere_click(self, *, timeout=10.0):
        return object() if self._confirm else None


def _roll_fields(*emojis):
    return {
        "character_name": "Rem",
        "buttons": [
            {
                "custom_id": f"cmd s{i}",
                "is_sphere": True,
                "disabled": False,
                "emoji": {"name": emoji},
            }
            for i, emoji in enumerate(emojis)
        ],
    }


def _reactor(*, confirm=True, state=None, **callbacks):
    from macro.sphere_reactor import SphereReactor

    config = MacroConfig()
    config.sphere_reaction = SphereReactionRules(enabled=True, budget_aware=True)
    state = state or AccountState()
    state.perk9_click_max = 20
    state.perk9_roll_pool = 154
    state.perk9_rolled_today = 20
    return SphereReactor(
        actions=_ReactorActions(confirm=confirm),
        config=config,
        state=state,
        log=lambda _t: None,
        **callbacks,
    )


def test_reactor_counts_every_sphere_spawn_even_when_it_skips():
    seen: list[int] = []
    state = AccountState()
    reactor = _reactor(state=state, on_spawn=seen.append)
    # Blue is far below the bar with 130 spawns still to come.
    asyncio.run(reactor.react(message_id=1, fields=_roll_fields("spB")))
    assert seen == [1]
    assert reactor.actions.clicked == []


def test_reactor_does_not_count_megasphere_as_a_perk9_spawn():
    seen: list[int] = []
    reactor = _reactor(on_spawn=seen.append)
    asyncio.run(reactor.react(message_id=1, fields=_roll_fields("spM")))
    assert seen == []


def test_reactor_resyncs_when_a_click_confirmation_times_out():
    calls: list[int] = []

    async def on_timeout() -> None:
        calls.append(1)

    reactor = _reactor(confirm=False, on_click_timeout=on_timeout)
    asyncio.run(reactor.react(message_id=1, fields=_roll_fields("spW")))
    assert reactor.actions.clicked == ["cmd s0"]
    assert calls == [1]


def test_reactor_does_not_resync_when_the_click_is_confirmed():
    calls: list[int] = []

    async def on_timeout() -> None:
        calls.append(1)

    reactor = _reactor(confirm=True, on_click_timeout=on_timeout)
    asyncio.run(reactor.react(message_id=1, fields=_roll_fields("spW")))
    assert calls == []


def test_reactor_confirms_exhaustion_at_the_cap():
    calls: list[int] = []

    async def on_exhausted() -> None:
        calls.append(1)

    state = AccountState()
    state.perk9_clicks_day = state._today_key()
    state.perk9_clicks_today = 20
    reactor = _reactor(state=state, on_exhausted=on_exhausted)
    asyncio.run(reactor.react(message_id=1, fields=_roll_fields("spW")))
    assert calls == [1]


# --- click history backfilled from the earning log ---


def _click_event(sphere_type, *, date_key, account_id="acct"):
    return {
        "source": "sphere_click",
        "sphere_type": sphere_type,
        "date_key": date_key,
        "account_id": account_id,
    }


def _today_key():
    from mudae.clock import utc_date_key

    return utc_date_key()


def test_recent_click_colours_are_newest_first():
    from macro.perk9_daily import recent_perk9_click_colours

    today = _today_key()
    events = [
        _click_event("spB", date_key=today),
        _click_event("spT", date_key=today),
        _click_event("spR", date_key=today),
    ]
    got = recent_perk9_click_colours(3, events=events, date_key=today, account_id="acct")
    assert got == ["spR", "spT", "spB"]


def test_recent_click_colours_ignore_other_days_sources_and_accounts():
    from macro.perk9_daily import recent_perk9_click_colours

    today = _today_key()
    events = [
        _click_event("spW", date_key="1999-01-01"),
        _click_event("spO", date_key=today, account_id="someone-else"),
        {"source": "perk10", "sphere_type": "spR", "date_key": today, "account_id": "acct"},
        _click_event("spM", date_key=today),  # megasphere is not a perk-9 click
        _click_event("spG", date_key=today),
    ]
    got = recent_perk9_click_colours(9, events=events, date_key=today, account_id="acct")
    assert got == ["spG"]


def test_history_prefers_the_log_over_face_down_placeholders(monkeypatch):
    today = _today_key()
    logged = [_click_event(e, date_key=today) for e in ("spB", "spT", "spG", "spY", "spR")]
    monkeypatch.setattr("macro.perk9_daily.get_sphere_events", lambda: logged)
    monkeypatch.setattr("mudae.sphere_log.recording_account_id", lambda: "acct")

    state = AccountState()
    state.perk9_click_max = 20
    state.perk9_clicks_day = state._today_key()
    state.perk9_clicks_today = 5
    state.perk9_roll_pool = 154
    state.perk9_rolled_today = 40
    # This session only saw the last one; the log knows the other four.
    state.record_perk9_click_emoji("spR")

    status = adaptive_status(state, SphereReactionRules(enabled=True, budget_aware=True))
    assert status["history"] == ["spR", "spY", "spG", "spT", "spB"]
    assert status["unknown_clicks"] == 0


def test_history_falls_back_to_face_down_when_the_log_is_short(monkeypatch):
    today = _today_key()
    monkeypatch.setattr(
        "macro.perk9_daily.get_sphere_events",
        lambda: [_click_event("spR", date_key=today)],
    )
    monkeypatch.setattr("mudae.sphere_log.recording_account_id", lambda: "acct")

    state = AccountState()
    state.perk9_click_max = 20
    state.perk9_clicks_day = state._today_key()
    state.perk9_clicks_today = 4
    state.perk9_roll_pool = 154
    state.perk9_rolled_today = 40

    status = adaptive_status(state, SphereReactionRules(enabled=True, budget_aware=True))
    assert status["history"] == ["spR", "spU", "spU", "spU"]
    assert status["unknown_clicks"] == 3


# --- remaining-spawn estimate decays between $ohu9 syncs ---


def test_spawns_left_counts_down_as_spawns_are_seen():
    state = AccountState()
    state.perk9_click_max = 20
    state.perk9_roll_pool = 154
    state.perk9_rolled_today = 60
    state.perk9_spawns_today = 60
    state.perk9_spawns_at_sync = 60
    rules = SphereReactionRules(enabled=True, budget_aware=True)

    at_sync = adaptive_status(state, rules)
    assert at_sync["spawns_left"] == 94
    assert at_sync["spawns_total"] == 154

    # Ten more perk-9 characters roll before the next $ohu9.
    for _ in range(10):
        state.record_perk9_spawn()
    later = adaptive_status(state, rules)
    assert later["spawns_seen"] == 70
    assert later["spawns_left"] == 84
    assert later["spawns_total"] == 154


def test_sync_rebaselines_the_spawn_countdown():
    parsed = parse_ohu(OHU9_SAMPLE)  # Rolled today: 60/154
    state = AccountState()
    state.perk9_spawns_today = 5
    runtime, ctx, _ = _runtime(reply=parsed, state=state)
    asyncio.run(runtime.refresh(at_startup=True))
    # Mudae's 60 wins over the 5 seen locally, and becomes the new baseline.
    assert ctx.state.perk9_spawns_today == 60
    assert ctx.state.perk9_spawns_at_sync == 60
    status = adaptive_status(ctx.state, ctx.config.sphere_reaction)
    assert status["spawns_left"] == 94
