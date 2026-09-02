"""Perk-9 daily budget runtime: when to re-query ``$ohu9``, and applying the answer.

Same shape as ``macro/perk8_runtime.py`` — orchestration only, arithmetic lives in
``macro/perk9_daily.py``, persistence is injected so this never imports the GUI.

``$ohu9`` is expensive to spam, so it is sent once per refill window and the
counters are tracked locally in between: every sphere button seen is a spawn,
every confirmed click bumps the used count. A query re-syncs both to Mudae. It
is also sent after a click whose confirmation timed out (the click may have
landed) and once the local count reaches the cap, to confirm before standing
down until the refill.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from macro.perk9_daily import (
    Perk9DailyRecord,
    apply_record_to_state,
    learned_hazard,
    load_perk9_record,
    persist_click_progress,
    record_hazard_interval,
    refresh_exhausted_if_refill_passed,
    rolled_today_estimate,
    save_perk9_record,
    should_query_ohu9_on_refill,
    should_skip_ohu9_until_refill,
    update_record_from_ohu,
)
from macro.roll_context import RollContext

OHU9_SETTLE_SEC = 2.0
OHU9_RESPONSE_TIMEOUT_SEC = 12.0
# Confirmed clicks ``$ohu9`` may not have counted yet. A bigger gap is stale
# local state, not lag, so it rewinds to Mudae's number.
OHU9_CLICK_LAG_MAX = 2


class Perk9Action(str, Enum):
    """What a perk-9 status check should do."""

    DISABLED = "disabled"  # budget mode off
    DEFER = "defer"  # gateway down; re-query once reconnected
    SKIP_UNTIL_REFILL = "skip_until_refill"  # clicks spent and confirmed
    USE_CACHED = "use_cached"  # local tracking is good enough
    QUERY = "query"  # send $ohu9


def gate_before_load(
    *,
    budget_mode: bool,
    commands_blocked: bool,
) -> Perk9Action | None:
    """Decide without touching the daily store; ``None`` means carry on and load."""
    if not budget_mode:
        return Perk9Action.DISABLED
    if commands_blocked:
        return Perk9Action.DEFER
    return None


def query_decision(
    record: Perk9DailyRecord,
    *,
    force: bool,
    clicks_used: int,
    click_max: int,
) -> Perk9Action:
    """Whether this check should spend an ``$ohu9`` call.

    ``force`` covers startup and a refresh deferred while the gateway was down.
    Reaching the cap locally also queries once — that is the confirmation that
    lets later checks stand down until the refill.
    """
    if should_skip_ohu9_until_refill(record):
        return Perk9Action.SKIP_UNTIL_REFILL
    if force or should_query_ohu9_on_refill(record):
        return Perk9Action.QUERY
    if click_max > 0 and clicks_used >= click_max and not record.clicks_exhausted:
        return Perk9Action.QUERY
    return Perk9Action.USE_CACHED


def merge_click_count(*, live: int, reported: int) -> int:
    """Combine the local click tracker with Mudae's ``N/M buttons clicked``.

    Catch up when Mudae is ahead; keep the local count when it is only a click
    or two ahead (not yet reflected); rewind when it is far ahead (stale).
    """
    live_n = max(0, int(live))
    reported_n = max(0, int(reported))
    if reported_n >= live_n:
        return reported_n
    if live_n - reported_n <= OHU9_CLICK_LAG_MAX:
        return live_n
    return reported_n


def merge_spawn_count(*, live: int, reported: int) -> int:
    """``(Perk 9) Rolled today`` counts pool characters rolled — never fewer than seen.

    After the click budget is spent Mudae keeps rolling perk-9 characters without
    spawning buttons, so its number runs ahead of what the reactor observed. Take
    the larger; the local count can only under-report.
    """
    return max(0, int(live), 0 if reported is None else int(reported))


class Perk9Runtime:
    def __init__(
        self,
        ctx: RollContext,
        *,
        daily_get: Callable[[], dict[str, Any]] | None = None,
        daily_save: Callable[[dict[str, Any]], None] | None = None,
        on_busy: Callable[[], None] | None = None,
        on_idle: Callable[[], None] | None = None,
        response_timeout_sec: float = OHU9_RESPONSE_TIMEOUT_SEC,
    ) -> None:
        self._ctx = ctx
        self._daily_get = daily_get
        self._daily_save = daily_save
        self._on_busy = on_busy
        self._on_idle = on_idle
        self._response_timeout = response_timeout_sec
        self._pending = False
        # Open stretch of ordinary rolling being measured: ``(rolled, rolls)``
        # when it started. ``None`` between stretches — during a ``$us`` drain,
        # or once the click budget is spent and Mudae stops spawning buttons, so
        # the local ``rolled`` estimate would no longer track reality.
        self._hazard_mark: tuple[int, int] | None = None

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

    def _load_refreshed(self) -> tuple[dict[str, Any], Perk9DailyRecord]:
        daily = self.load_daily()
        record = refresh_exhausted_if_refill_passed(load_perk9_record(daily))
        self.save_daily(save_perk9_record(daily, record))
        return daily, record

    # --- pending refresh (set while the gateway is down) ---

    @property
    def pending(self) -> bool:
        return self._pending

    def mark_pending(self) -> None:
        self._pending = True

    def clear_pending(self) -> None:
        self._pending = False

    @property
    def budget_mode(self) -> bool:
        return bool(self._ctx.config.sphere_reaction.budget_aware)

    # --- SphereReactor callbacks ---

    def note_spawn(self, count: int = 1) -> None:
        """A perk-9 sphere button appeared, whether or not it was clicked."""
        if count <= 0:
            return
        self._ctx.state.record_perk9_spawn(count)

    def note_roll(self, us_roll: bool = False) -> None:
        """One roll went out; keep the learned-rate accounting straight.

        Ordinary rolls are the denominator of the rate. ``$us`` rolls are not:
        they spawn perk-9 buttons like any other roll, but a drain can tear
        through a large slice of the pool in half an hour, and counting that as
        this account's normal pace would inflate the estimate for every later
        day. A ``$us`` roll therefore closes the stretch being measured and the
        next stretch starts from the post-drain ``rolled`` — the depletion the
        drain caused is respected, its rolls are not counted.
        """
        state = self._ctx.state
        if us_roll:
            self._close_hazard_interval()
            return
        if self._hazard_mark is None:
            self._open_hazard_interval()
        state.record_perk9_regular_roll()

    def _at_click_cap(self) -> bool:
        cap = int(getattr(self._ctx.state, "perk9_click_max", 0) or 0)
        return cap > 0 and int(self._ctx.state.perk9_clicks_today) >= cap

    def _open_hazard_interval(self, rolled: int | None = None) -> None:
        """Start measuring a stretch of ordinary rolling from a known ``rolled``."""
        state = self._ctx.state
        if rolled is None:
            # Only Mudae's own number survives the click budget running out.
            if self._at_click_cap():
                return
            rolled = rolled_today_estimate(state)
        if rolled is None or state.perk9_roll_pool is None:
            return
        self._hazard_mark = (int(rolled), int(state.perk9_regular_rolls_today))

    def _close_hazard_interval(self, rolled: int | None = None) -> None:
        """Fold the open stretch into the learned rate and stop measuring."""
        mark = self._hazard_mark
        self._hazard_mark = None
        if mark is None:
            return
        state = self._ctx.state
        if rolled is None:
            if self._at_click_cap():
                # Buttons stopped spawning, so the local count froze while the
                # real one kept climbing — the stretch is unmeasurable.
                return
            rolled = rolled_today_estimate(state)
        if rolled is None:
            return
        rolled_from, rolls_from = mark
        rolls = int(state.perk9_regular_rolls_today) - rolls_from
        if rolls <= 0:
            return
        daily = self.load_daily()
        record = record_hazard_interval(
            load_perk9_record(daily),
            pool=state.perk9_roll_pool,
            rolled_from=rolled_from,
            rolled_to=int(rolled),
            rolls=rolls,
        )
        self.save_daily(save_perk9_record(daily, record))
        state.perk9_hazard = learned_hazard(record.hazard_history)

    def persist_click_progress(self) -> None:
        """Write the live click counter into the persisted daily record."""
        if not self.budget_mode:
            return
        state = self._ctx.state
        daily = self.load_daily()
        record = persist_click_progress(
            load_perk9_record(daily),
            clicked_today=int(state.perk9_clicks_today),
            click_max=int(state.perk9_click_max),
        )
        self.save_daily(save_perk9_record(daily, record))

    async def resync_after_uncertain_click(self) -> None:
        """A sphere click's confirmation never arrived — it may still have landed."""
        if not self.budget_mode:
            return
        self._ctx.log("sphere click timeout — checking $ohu9 to sync perk-9 clicks")
        await self.refresh(force=True)

    async def confirm_exhausted(self) -> None:
        """Local count hit the cap; confirm with Mudae before standing down."""
        if not self.budget_mode:
            return
        await self.refresh()

    # --- status refresh ---

    async def refresh(
        self,
        *,
        at_startup: bool = False,
        force: bool = False,
    ) -> Perk9Action:
        """Bring perk-9 tracking up to date, sending ``$ohu9`` when warranted."""
        gate = gate_before_load(
            budget_mode=self.budget_mode,
            commands_blocked=self._ctx.commands_blocked,
        )
        if gate is Perk9Action.DEFER:
            self.mark_pending()
            return gate
        if gate is Perk9Action.DISABLED:
            return gate

        state = self._ctx.state
        daily, record = self._load_refreshed()
        action = query_decision(
            record,
            force=at_startup or force or self._pending,
            clicks_used=int(state.perk9_clicks_today),
            click_max=int(state.perk9_click_max),
        )

        if action is Perk9Action.SKIP_UNTIL_REFILL:
            apply_record_to_state(state, record)
            state.sync_perk9_unknown_clicks()
            self._ctx.notify()
            return action

        if action is Perk9Action.USE_CACHED:
            return action

        await self._query_ohu9(daily, record)
        return Perk9Action.QUERY

    async def maybe_refresh(self) -> Perk9Action:
        """Mid-session check: only queries when the refill has passed or a defer is due."""
        gate = gate_before_load(
            budget_mode=self.budget_mode,
            commands_blocked=self._ctx.commands_blocked,
        )
        if gate is not None:
            if gate is Perk9Action.DEFER:
                self.mark_pending()
            return gate
        _daily, record = self._load_refreshed()
        if not (self._pending or should_query_ohu9_on_refill(record)):
            self.checkpoint_hazard()
            return Perk9Action.USE_CACHED
        return await self.refresh(force=True)

    def checkpoint_hazard(self) -> None:
        """Bank the stretch measured so far and start the next one.

        ``$ohu9`` goes out about once a day, so without this a stretch opened at
        session start would only ever close at the *next* day's query — which
        spans the reset and is discarded — and the rate would never be learned
        at all. The local ``rolled`` estimate is exact until the click budget
        runs out, which ``_close_hazard_interval`` already checks, so an hourly
        checkpoint costs nothing and needs no extra command.
        """
        if self._hazard_mark is None:
            return
        self._close_hazard_interval()
        self._open_hazard_interval()

    async def _query_ohu9(
        self,
        daily: dict[str, Any],
        record: Perk9DailyRecord,
    ) -> None:
        ctx = self._ctx
        state = ctx.state
        ctx.actions.drain_queue()
        if self._on_busy:
            self._on_busy()
        ctx.log("Sent $ohu9")
        ctx.notify()
        await ctx.actions.send_command("ohu9", prefix=ctx.config.prefix)
        # Cleared on send, not on reply: the poll loops call in every 30s, so a
        # pending flag held through a timeout would resend on every poll.
        self.clear_pending()
        await ctx.sleep(OHU9_SETTLE_SEC)
        parsed = await ctx.actions.wait_for_ohu9(timeout=self._response_timeout)
        if parsed is None:
            ctx.log("$ohu9 timeout — keeping locally tracked perk-9 counts")
            if self._on_idle:
                self._on_idle()
            ctx.notify()
            return

        self.apply_parsed(parsed.fields, daily=daily, record=record)
        if self._on_idle:
            self._on_idle()
        ctx.notify()

    def apply_parsed(
        self,
        fields: dict[str, Any],
        *,
        daily: dict[str, Any] | None = None,
        record: Perk9DailyRecord | None = None,
    ) -> None:
        """Merge a parsed ``$ohu9`` reply into runtime state and the daily record."""
        ctx = self._ctx
        state = ctx.state
        daily = self.load_daily() if daily is None else daily
        record = load_perk9_record(daily) if record is None else record

        record = update_record_from_ohu(record, fields)
        record = refresh_exhausted_if_refill_passed(record)
        self.save_daily(save_perk9_record(daily, record))

        day_before = state.perk9_clicks_day
        state.rollover_perk9_if_needed()
        if state.perk9_clicks_day != day_before:
            # Yesterday's open stretch cannot be closed against today's counts.
            self._hazard_mark = None
        if record.last_click_max is not None:
            state.perk9_click_max = int(record.last_click_max)
        if record.last_clicked is not None:
            state.perk9_clicks_today = merge_click_count(
                live=int(state.perk9_clicks_today),
                reported=int(record.last_clicked),
            )
        if record.roll_pool is not None:
            state.perk9_roll_pool = int(record.roll_pool)
        if record.rolled_today is not None:
            state.perk9_rolled_today = int(record.rolled_today)
            state.perk9_spawns_today = merge_spawn_count(
                live=int(state.perk9_spawns_today),
                reported=int(record.rolled_today),
            )
            # Baseline for "spawns seen since this sync" — the remaining-spawn
            # estimate counts down from here until the next $ohu9.
            state.perk9_spawns_at_sync = int(state.perk9_spawns_today)
        state.sync_perk9_unknown_clicks()

        # Mudae's own ``rolled`` is the one number the click budget running out
        # cannot stale — buttons stop spawning at the cap, but the pool keeps
        # emptying — so it both closes the stretch being measured and opens the
        # next one.
        if record.rolled_today is not None:
            self._close_hazard_interval(rolled=int(record.rolled_today))
            self._open_hazard_interval(rolled=int(record.rolled_today))
        state.perk9_hazard = learned_hazard(
            load_perk9_record(self.load_daily()).hazard_history
        )

        used = int(state.perk9_clicks_today)
        cap = int(state.perk9_click_max)
        ctx.log(
            f"$ohu9: {used}/{cap} clicks used"
            + (
                f", {record.rolled_today}/{record.roll_pool} perk-9 rolled"
                if record.roll_pool is not None
                else ""
            )
        )
