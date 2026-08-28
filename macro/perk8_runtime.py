"""Perk-8 daily budget runtime: when to re-query ``$ohu8``, and applying the answer.

Orchestration only — the daily-state arithmetic lives in ``macro/perk8_daily.py``.
One instance per running account. Persistence is injected, so this module never
imports the GUI bridge and several accounts can keep independent daily state.

The decision functions at the top are pure so the "should we spend an ``$ohu8``
call right now?" question can be tested as a table instead of through the loop.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from macro.perk8_daily import (
    PERK8_MIN_ROLL_POOL,
    Perk8DailyRecord,
    Perk8PriorityMode,
    apply_cached_perk8,
    load_perk8_record,
    mark_perk8_exhausted,
    refresh_exhausted_if_refill_passed,
    save_perk8_record,
    should_query_ohu8_on_refill,
    should_skip_ohu8_until_refill,
    sync_refill_deadline,
    update_record_from_ohu8,
)
from macro.roll_context import RollContext
from macro.roll_scheduler import seconds_until_perk8_refill

# Pause after sending ``$ohu8`` before polling for the reply.
OHU8_SETTLE_SEC = 2.0
OHU8_RESPONSE_TIMEOUT_SEC = 12.0


class Perk8Action(str, Enum):
    """What a perk-8 status check should do."""

    DISABLED = "disabled"  # budget mode off — clear runtime state
    DEFER = "defer"  # gateway down; remember to re-query once reconnected
    SKIP_UNTIL_REFILL = "skip_until_refill"  # clicks spent, refill not due yet
    USE_CACHED = "use_cached"  # persisted state is good enough
    QUERY = "query"  # send $ohu8


def gate_before_load(
    *,
    budget_mode: bool,
    commands_blocked: bool,
) -> Perk8Action | None:
    """Decide without touching the daily store; ``None`` means carry on and load.

    Kept separate so a disabled or disconnected check performs no store read and
    no settings write.
    """
    if not budget_mode:
        return Perk8Action.DISABLED
    if commands_blocked:
        return Perk8Action.DEFER
    return None


def query_decision(record: Perk8DailyRecord, *, force: bool) -> Perk8Action:
    """Whether an explicit refresh should spend an ``$ohu8`` call.

    ``force`` covers the cases where the caller already knows a query is wanted —
    startup, and a refresh deferred while the gateway was down — so the saved
    record does not get to veto it. A live refill deadline still wins, since we
    already know the clicks are gone and the answer would tell us nothing.
    """
    if should_skip_ohu8_until_refill(record):
        return Perk8Action.SKIP_UNTIL_REFILL
    if force or should_query_ohu8_on_refill(record):
        return Perk8Action.QUERY
    return Perk8Action.USE_CACHED


def opportunistic_decision(
    record: Perk8DailyRecord,
    *,
    pending: bool,
    commands_blocked: bool,
) -> Perk8Action:
    """Whether a mid-session check should re-query, use the cache, or defer.

    ``pending`` carries a refresh that an earlier check could not perform because
    the gateway was down.
    """
    if not (pending or should_query_ohu8_on_refill(record)):
        return Perk8Action.USE_CACHED
    if commands_blocked:
        return Perk8Action.DEFER
    return Perk8Action.QUERY


class Perk8Runtime:
    def __init__(
        self,
        ctx: RollContext,
        *,
        daily_get: Callable[[], dict[str, Any]] | None = None,
        daily_save: Callable[[dict[str, Any]], None] | None = None,
        on_busy: Callable[[], None] | None = None,
        on_idle: Callable[[], None] | None = None,
        response_timeout_sec: float = OHU8_RESPONSE_TIMEOUT_SEC,
    ) -> None:
        self._ctx = ctx
        self._daily_get = daily_get
        self._daily_save = daily_save
        # Phase display stays with the engine; this only signals busy/idle.
        self._on_busy = on_busy
        self._on_idle = on_idle
        self._response_timeout = response_timeout_sec
        self._pending = False

    # --- persisted daily state ---

    def load_daily(self) -> dict[str, Any]:
        if self._daily_get:
            return dict(self._daily_get())
        return {}

    def save_daily(self, daily: dict[str, Any]) -> None:
        if self._daily_save:
            self._daily_save(daily)

    def update_daily_store(
        self,
        *,
        daily_get: Callable[[], dict[str, Any]] | None = None,
        daily_save: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if daily_get is not None:
            self._daily_get = daily_get
        if daily_save is not None:
            self._daily_save = daily_save
        self.clear_pending()

    def _load_refreshed(self) -> tuple[dict[str, Any], Perk8DailyRecord]:
        """Load the record, clear a stale exhausted flag, and persist the result."""
        daily = self.load_daily()
        record = refresh_exhausted_if_refill_passed(load_perk8_record(daily))
        self.save_daily(save_perk8_record(daily, record))
        return daily, record

    # --- pending refresh (set while the gateway is down) ---

    @property
    def pending(self) -> bool:
        return self._pending

    def mark_pending(self) -> None:
        self._pending = True

    def clear_pending(self) -> None:
        self._pending = False

    # --- runtime state ---

    @property
    def budget_mode(self) -> bool:
        return bool(self._ctx.config.kakera_reaction.perk_8_budget_mode)

    def apply_mode(self, mode: Perk8PriorityMode, record: Perk8DailyRecord) -> None:
        state = self._ctx.state
        if record.last_click_max is not None:
            state.perk8_click_max = record.last_click_max
        if record.last_clicked is not None:
            state.rollover_kakera_budget_if_needed()
            # Never rewind a live count if ``$ohu8`` is behind; catch up when it
            # is ahead (local 38, Mudae 40).
            state.kakera_clicks_today = max(
                int(state.kakera_clicks_today), int(record.last_clicked)
            )
            state.clamp_kakera_clicks_to_perk8_cap()
        cap = state.perk8_click_max
        if (
            cap is not None
            and int(state.kakera_clicks_today) >= int(cap)
            and mode is Perk8PriorityMode.ACTIVE
        ):
            mode = Perk8PriorityMode.DONE
        state.perk8_priority_mode = mode.value

    def _set_inactive(self) -> None:
        self._ctx.state.perk8_priority_mode = Perk8PriorityMode.INACTIVE.value
        self._ctx.state.perk8_click_max = None

    def seconds_until_refill(self) -> float | None:
        """Seconds until daily clicks return; ``None`` when no timed wake is needed."""
        if not self.budget_mode:
            return None
        record = refresh_exhausted_if_refill_passed(
            load_perk8_record(self.load_daily())
        )
        return seconds_until_perk8_refill(record)

    # --- KakeraReactor callbacks ---

    def mark_exhausted(self) -> None:
        """Daily clicks ran out mid-session (observed by the kakera reactor)."""
        try:
            mode = Perk8PriorityMode(self._ctx.state.perk8_priority_mode)
        except ValueError:
            return
        if mode is not Perk8PriorityMode.ACTIVE:
            return
        daily = self.load_daily()
        record = mark_perk8_exhausted(
            load_perk8_record(daily),
            clicked_today=self._ctx.state.kakera_clicks_today,
        )
        self.save_daily(save_perk8_record(daily, record))
        self.apply_mode(Perk8PriorityMode.DONE, record)
        self._ctx.log(
            "$ohu8: daily perk 8 clicks used — equal kakera clicking until refill"
        )
        self._ctx.notify()

    def persist_click_progress(self) -> None:
        """Write this account's kakera click count back to persisted daily state."""
        if not self.budget_mode:
            return
        self._ctx.state.clamp_kakera_clicks_to_perk8_cap()
        daily = self.load_daily()
        record = load_perk8_record(daily)
        record.last_clicked = self._ctx.state.kakera_clicks_today
        from mudae.clock import utc_now

        record.updated_at = utc_now().isoformat()
        self.save_daily(save_perk8_record(daily, record))

    async def resync_after_uncertain_click(self) -> None:
        """Live ``$ohu8`` after a kakera timeout — Mudae may have counted the click."""
        if not self.budget_mode:
            return
        try:
            mode = Perk8PriorityMode(self._ctx.state.perk8_priority_mode)
        except ValueError:
            return
        if mode is not Perk8PriorityMode.ACTIVE:
            return
        self._ctx.log("kakera timeout — checking $ohu8 to sync perk-8 clicks")
        await self.refresh(force=True)

    # --- $tu integration ---

    def sync_refill_from_tu(self, fields: dict[str, Any]) -> None:
        """Keep the persisted refill ETA in sync with ``$tu`` / ``$ohu8`` text."""
        if not self.budget_mode:
            return
        refill = fields.get("perk8_refill_minutes")
        if refill is None:
            return
        daily = self.load_daily()
        record = load_perk8_record(daily)
        sync_refill_deadline(record, int(refill))
        record = refresh_exhausted_if_refill_passed(record)
        self.save_daily(save_perk8_record(daily, record))

    # --- status refresh ---

    async def refresh(
        self,
        *,
        at_startup: bool = False,
        force: bool = False,
    ) -> Perk8Action:
        """Bring perk-8 mode up to date, sending ``$ohu8`` when warranted."""
        gate = gate_before_load(
            budget_mode=self.budget_mode,
            commands_blocked=self._ctx.commands_blocked,
        )
        if gate is Perk8Action.DISABLED:
            self._set_inactive()
            return gate
        if gate is Perk8Action.DEFER:
            self.mark_pending()
            return gate

        daily, record = self._load_refreshed()
        action = query_decision(record, force=at_startup or force)

        if action is Perk8Action.SKIP_UNTIL_REFILL:
            mode = apply_cached_perk8(record)
            self.apply_mode(mode, record)
            eta = record.refill_at or "unknown"
            self._ctx.log(
                f"$ohu8: skipped until refill ({eta}) — cached mode {mode.value}"
            )
            self._ctx.notify()
            return action

        if action is Perk8Action.USE_CACHED:
            self.apply_mode(apply_cached_perk8(record), record)
            return action

        await self._query_ohu8(daily, record)
        return Perk8Action.QUERY

    async def _query_ohu8(
        self,
        daily: dict[str, Any],
        record: Perk8DailyRecord,
    ) -> None:
        ctx = self._ctx
        ctx.actions.drain_queue()
        if self._on_busy:
            self._on_busy()
        ctx.log("Sent $ohu8")
        ctx.notify()
        await ctx.actions.send_command("ohu8", prefix=ctx.config.prefix)
        # Discharge the deferred refresh on send, not on reply: the poll loops call
        # in every 30s, so keeping it set through a timeout would resend $ohu8 on
        # every poll for as long as Mudae stays quiet.
        self.clear_pending()
        await ctx.sleep(OHU8_SETTLE_SEC)
        parsed = await ctx.actions.wait_for_ohu8(timeout=self._response_timeout)
        if parsed is None:
            ctx.log("$ohu8 timeout — using preset budget rules")
            ctx.state.perk8_priority_mode = Perk8PriorityMode.ACTIVE.value
            if self._on_idle:
                self._on_idle()
            ctx.notify()
            return

        record, mode = update_record_from_ohu8(record, parsed.fields)
        refresh_exhausted_if_refill_passed(record)
        daily = save_perk8_record(daily, record)
        from macro.minigame_daily import (
            save_minigame_record,
            update_record_from_ohu as update_minigames_from_ohu,
            load_minigame_record,
        )
        from macro.perk9_daily import (
            apply_record_to_state as apply_perk9_record_to_state,
            load_perk9_record,
            save_perk9_record,
            update_record_from_ohu as update_perk9_from_ohu,
        )

        daily = save_minigame_record(
            daily,
            update_minigames_from_ohu(load_minigame_record(daily), parsed.fields),
        )
        perk9 = update_perk9_from_ohu(load_perk9_record(daily), parsed.fields)
        daily = save_perk9_record(daily, perk9)
        apply_perk9_record_to_state(self._ctx.state, perk9)
        self.save_daily(daily)
        self.apply_mode(mode, record)
        ctx.log(_mode_summary(mode, record))
        if self._on_idle:
            self._on_idle()
        ctx.notify()

    async def maybe_refresh(self) -> Perk8Action:
        """Re-query ``$ohu8`` on refill or a deferred refresh."""
        if not self.budget_mode:
            return Perk8Action.DISABLED

        _daily, record = self._load_refreshed()
        action = opportunistic_decision(
            record,
            pending=self._pending,
            commands_blocked=self._ctx.commands_blocked,
        )

        if action is Perk8Action.USE_CACHED:
            self.apply_mode(apply_cached_perk8(record), record)
            return action
        if action is Perk8Action.DEFER:
            self.mark_pending()
            return action

        # ``force`` matters when the only reason to query is a deferred refresh:
        # the record on its own would say "not due" and refresh would use the cache.
        await self.refresh(force=True)
        return action


def _mode_summary(mode: Perk8PriorityMode, record: Perk8DailyRecord) -> str:
    if mode is Perk8PriorityMode.DONE:
        return "$ohu8: perk 8 clicks done for today — equal kakera clicking"
    if mode is Perk8PriorityMode.INSUFFICIENT_POOL:
        return f"$ohu8: roll pool < {PERK8_MIN_ROLL_POOL} — equal kakera clicking"
    clicked = record.last_clicked if record.last_clicked is not None else "?"
    cap = record.last_click_max if record.last_click_max is not None else "?"
    return f"$ohu8: prioritizing perk 8 · clicked {clicked}/{cap}"
