"""Roll-cycle macro engine: $tu, roll until stop, then claim best character."""

from __future__ import annotations

import asyncio
import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions
from macro.activity_log import ActivityLog
from macro.claim_window import is_final_roll_session_before_claim_reset
from macro.config import MacroConfig
from macro.perk8_daily import (
    PERK8_MIN_ROLL_POOL,
    Perk8DailyRecord,
    Perk8PriorityMode,
    apply_cached_perk8,
    load_perk8_record,
    mark_perk8_exhausted,
    refresh_exhausted_if_refill_passed,
    save_perk8_record,
    should_query_ohu8,
    sync_refill_deadline,
    update_record_from_ohu8,
)
from macro.kakera_reactor import KakeraReactor
from macro.post_roll import PostRollHandler, RollRecord
from macro.roll_interrupts import RollInterruptContext, evaluate_claim_trigger
from macro.roll_stop import RollStopTracker
from macro.reaction_power import sync_reaction_power_fields
from macro.dk_manager import sync_dk_fields_from_tu
from macro.sphere_reactor import SphereReactor
from macro.state import AccountState, MacroPhase, RuleTraceEntry
from mudae.parsers.us import is_us_stack_response, parse_us_stacked

# Stop $us mode after this many consecutive "$us N" sends fail to register
# (Mudae ignores rapid follow-ups, so the usable roll count never rises).
_MAX_FAILED_US_ADDS = 3
# Stop $us mode after this many consecutive roll timeouts (no embed arrived).
_MAX_ROLL_TIMEOUT_RETRIES = 5

# Timing knobs shared by the roll loops (seconds).
_COMMAND_SETTLE_SEC = 2.5  # pause after $tu before polling for the reply
_OHU8_SETTLE_SEC = 2.0  # pause after $ohu8 before polling for the reply
_RESPONSE_TIMEOUT_SEC = 12.0  # max wait for a $tu / $ohu8 / $us text reply
_ROLL_EMBED_TIMEOUT_SEC = 25.0  # max wait for a character embed after rolling
_RESET_POLL_SEC = 30.0  # $tu poll interval while paused for the rolls reset ($us mode)
_ROLLS_RESET_BUFFER_SEC = 5.0  # pad after parsed reset time before re-checking $tu
_STOP_CHECK_SEC = 1.0  # wake interval so Stop remains responsive during long waits
_PERK6_SPAWN_WAIT_SEC = 0.8  # brief poll for perk-6 follow-up embed (only when proc'd)
_PERK6_POST_SETTLE_SEC = 0.5  # pause after spawn reactions before next roll


@dataclass
class _RollOutcome:
    """Result of a single roll performed by :meth:`RollCycleEngine._perform_roll`."""

    ok: bool  # roll embed received and processed
    rolls_left: int | None = None
    claimed: bool = False  # a claim was made on this roll via the interrupt path
    stop: bool = False  # caller should stop the *normal* roll loop (interrupt claim)


class RollCycleEngine:
    def __init__(
        self,
        actions: DiscordActions,
        config: MacroConfig,
        state: AccountState,
        monitor: Any,
        *,
        on_state: Callable[[], None] | None = None,
        on_persist: Callable[[], None] | None = None,
        daily_resets_get: Callable[[], dict[str, Any]] | None = None,
        daily_resets_save: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._actions = actions
        self._config = config
        self._state = state
        self._monitor = monitor
        self._on_state = on_state
        self._on_persist = on_persist
        self._daily_resets_get = daily_resets_get
        self._daily_resets_save = daily_resets_save
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._roll_stop = RollStopTracker()
        self._activity = ActivityLog(self._state, on_update=self._notify)
        self._final_roll_session = False

    def _notify(self) -> None:
        if self._on_state:
            self._on_state()

    def _persist(self) -> None:
        if self._on_persist:
            self._on_persist()

    def _log(self, text: str) -> None:
        self._activity.write(text)

    def _sync_roll_stop_config(self) -> None:
        n = max(1, self._config.rolls_left_stop)
        self._roll_stop.threshold = n
        self._roll_stop.tail_count = n

    def _make_post_roll_handler(self) -> PostRollHandler:
        return PostRollHandler(
            self._actions,
            self._config,
            self._state,
            log=self._log,
        )

    def _make_kakera_reactor(self) -> KakeraReactor:
        on_exhausted = None
        on_progress = None
        if self._config.kakera_reaction.perk_8_budget_mode:
            on_exhausted = self._mark_perk8_exhausted
            on_progress = self._persist_perk8_click_progress
        return KakeraReactor(
            actions=self._actions,
            config=self._config,
            state=self._state,
            log=self._log,
            on_perk8_exhausted=on_exhausted,
            on_click_progress=on_progress,
            on_state=self._notify,
        )

    def _get_daily_resets(self) -> dict[str, Any]:
        if self._daily_resets_get:
            return dict(self._daily_resets_get())
        return {}

    def _save_daily_resets(self, daily: dict[str, Any]) -> None:
        if self._daily_resets_save:
            self._daily_resets_save(daily)

    def _apply_perk8_mode(self, mode: Perk8PriorityMode, record: Perk8DailyRecord) -> None:
        self._state.perk8_priority_mode = mode.value
        if record.last_click_max is not None:
            self._state.perk8_click_max = record.last_click_max
        if record.last_clicked is not None:
            self._state.rollover_kakera_budget_if_needed()
            self._state.kakera_clicks_today = record.last_clicked

    def _mark_perk8_exhausted(self) -> None:
        try:
            mode = Perk8PriorityMode(self._state.perk8_priority_mode)
        except ValueError:
            return
        if mode is not Perk8PriorityMode.ACTIVE:
            return
        daily = self._get_daily_resets()
        record = mark_perk8_exhausted(
            load_perk8_record(daily),
            clicked_today=self._state.kakera_clicks_today,
        )
        self._save_daily_resets(save_perk8_record(daily, record))
        self._apply_perk8_mode(Perk8PriorityMode.DONE, record)
        self._log("$ohu8: daily perk 8 clicks used — equal kakera clicking until refill")
        self._notify()

    def _persist_perk8_click_progress(self) -> None:
        """Write this account's kakera click count back to persisted daily state."""
        if not self._config.kakera_reaction.perk_8_budget_mode:
            return
        daily = self._get_daily_resets()
        record = load_perk8_record(daily)
        record.last_clicked = self._state.kakera_clicks_today
        self._save_daily_resets(save_perk8_record(daily, record))

    def _sync_perk8_refill_from_tu(self, fields: dict[str, Any]) -> None:
        """Keep the persisted refill ETA in sync with ``$tu`` / ``$ohu8`` text."""
        if not self._config.kakera_reaction.perk_8_budget_mode:
            return
        refill = fields.get("perk8_refill_minutes")
        if refill is None:
            return
        daily = self._get_daily_resets()
        record = load_perk8_record(daily)
        sync_refill_deadline(record, int(refill))
        refresh_exhausted_if_refill_passed(record)
        self._save_daily_resets(save_perk8_record(daily, record))

    async def _refresh_perk8_status(self) -> None:
        rules = self._config.kakera_reaction
        if not rules.perk_8_budget_mode:
            self._state.perk8_priority_mode = Perk8PriorityMode.INACTIVE.value
            self._state.perk8_click_max = None
            return

        daily = self._get_daily_resets()
        record = load_perk8_record(daily)
        refresh_exhausted_if_refill_passed(record)

        if not should_query_ohu8(record):
            mode = apply_cached_perk8(record)
            self._apply_perk8_mode(mode, record)
            eta = record.refill_at or "unknown"
            self._log(
                f"$ohu8: skipped until refill ({eta}) — "
                f"cached mode {mode.value}"
            )
            self._notify()
            return

        self._actions.drain_queue()
        self._state.phase = MacroPhase.CHECKING_TU
        self._log("Sent $ohu8")
        self._notify()
        await self._actions.send_command("ohu8", prefix=self._config.prefix)
        await asyncio.sleep(_OHU8_SETTLE_SEC)
        parsed = await self._actions.wait_for_ohu8(timeout=_RESPONSE_TIMEOUT_SEC)
        if parsed is None:
            self._log("$ohu8 timeout — using preset budget rules")
            self._state.perk8_priority_mode = Perk8PriorityMode.ACTIVE.value
            self._state.phase = MacroPhase.IDLE
            self._notify()
            return

        record, mode = update_record_from_ohu8(record, parsed.fields)
        refresh_exhausted_if_refill_passed(record)
        self._save_daily_resets(save_perk8_record(daily, record))
        self._apply_perk8_mode(mode, record)

        if mode is Perk8PriorityMode.DONE:
            self._log("$ohu8: perk 8 clicks done for today — equal kakera clicking")
        elif mode is Perk8PriorityMode.INSUFFICIENT_POOL:
            self._log(
                f"$ohu8: roll pool < {PERK8_MIN_ROLL_POOL} — equal kakera clicking"
            )
        else:
            clicked = record.last_clicked if record.last_clicked is not None else "?"
            cap = record.last_click_max if record.last_click_max is not None else "?"
            self._log(f"$ohu8: prioritizing perk 8 · clicked {clicked}/{cap}")

        self._state.phase = MacroPhase.IDLE
        self._notify()

    async def _maybe_refresh_perk8_status(self) -> None:
        """Re-query ``$ohu8`` when the daily perk-8 refill window has passed."""
        if not self._config.kakera_reaction.perk_8_budget_mode:
            return
        daily = self._get_daily_resets()
        record = load_perk8_record(daily)
        refresh_exhausted_if_refill_passed(record)
        self._save_daily_resets(save_perk8_record(daily, record))
        if should_query_ohu8(record):
            await self._refresh_perk8_status()
        else:
            mode = apply_cached_perk8(record)
            self._apply_perk8_mode(mode, record)

    async def _roll_hourly_normal_segment(
        self,
        cmd: str,
        session_records: list[RollRecord],
        roll_index: int,
        *,
        normal_rolls: int,
    ) -> tuple[int, bool, int]:
        """Roll the full hourly pool with standard stop/claim rules."""
        self._reset_roll_stop_tracker()
        self._log(f"{normal_rolls} hourly roll(s) — standard macro rules")
        segment_start = len(session_records)
        done, claimed = await self._run_normal_roll_segment(
            cmd,
            session_records,
            roll_index,
        )
        roll_index += done
        await self._claim_best_at_session_end(
            session_records[segment_start:],
            claimed,
        )
        return done, claimed, roll_index

    def _make_sphere_reactor(self) -> SphereReactor:
        return SphereReactor(
            actions=self._actions,
            config=self._config,
            state=self._state,
            log=self._log,
        )

    def _sync_claim_window_from_tu(self) -> None:
        self._final_roll_session = is_final_roll_session_before_claim_reset(
            self._state.next_claim_reset_minutes,
            self._state.rolls_reset_minutes,
            margin_minutes=self._config.claim_reset_margin_minutes,
        )

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def update_config(self, config: MacroConfig) -> None:
        self._config = config

    def stop(self) -> None:
        self._stop.set()
        self._state.phase = MacroPhase.STOPPING
        self._notify()
        if self._task and not self._task.done():
            self._task.cancel()

    async def run_tu(self) -> bool:
        """Send $tu and update account state. Returns False on timeout."""
        self._actions.drain_queue()
        self._state.phase = MacroPhase.CHECKING_TU
        self._log("Sent $tu")
        self._notify()
        await self._actions.send_command("tu", prefix=self._config.prefix)
        await asyncio.sleep(_COMMAND_SETTLE_SEC)
        parsed = await self._actions.wait_for_tu(timeout=_RESPONSE_TIMEOUT_SEC)
        if parsed is None:
            self._log("$tu timeout")
            self._state.phase = MacroPhase.IDLE
            self._notify()
            return False
        self._apply_tu_fields(parsed.fields)
        self._sync_perk8_refill_from_tu(parsed.fields)
        self._sync_claim_window_from_tu()
        claim_reset = self._state.next_claim_reset_minutes
        rolls_reset = self._state.rolls_reset_minutes
        expire = self._state.claim_expire_sec or self._config.claim_expire_sec
        window_note = ""
        if claim_reset is not None and rolls_reset is not None:
            window_note = (
                f" · claim reset {claim_reset}m · rolls reset {rolls_reset}m"
            )
            if self._final_roll_session:
                window_note += f" · final roll hour (claim ≤{expire}s)"
            else:
                window_note += " · roll only (save claim for final hour)"
        rolls_txt = "?" if self._state.rolls_left is None else str(self._state.rolls_left)
        if self._state.rolls_us_bonus:
            rolls_txt += f" (+{self._state.rolls_us_bonus} $us)"
        self._log(
            f"$tu OK · {rolls_txt} rolls · "
            f"{self._state.claim_label()}{window_note}"
        )
        self._state.phase = MacroPhase.IDLE
        self._notify()
        return True

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_cycle(), name="roll-cycle")

    def start_us_mode(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_us_cycle(), name="us-roll-cycle")

    async def _run_cycle(self) -> None:
        try:
            self._monitor.macro_active = True
            self._actions.drain_queue()
            self._reset_roll_stop_tracker()

            await self._refresh_perk8_status()

            cmd = self._config.normalized_roll_command()
            roll_index = 0
            tu_fresh = False

            self._log("Macro starting (continuous hourly mode)")

            while not self._stop.is_set():
                if not tu_fresh:
                    if not await self.run_tu():
                        self._log("$tu failed — stopping")
                        break
                tu_fresh = False

                await self._maybe_refresh_perk8_status()

                normal_rolls = self._state.rolls_left or 0
                if normal_rolls <= 0:
                    if not await self._wait_for_hourly_refill():
                        break
                    tu_fresh = True
                    continue

                # Fresh record list per hourly batch: claim-best runs inside the
                # segment, and keeping every hour's records would grow forever
                # on multi-day runs.
                session_records: list[RollRecord] = []
                done, claimed, roll_index = await self._roll_hourly_normal_segment(
                    cmd,
                    session_records,
                    roll_index,
                    normal_rolls=normal_rolls,
                )
                if claimed:
                    break
                if done == 0:
                    self._log("Roll failed — stopping")
                    break

                if not await self._wait_for_hourly_refill():
                    break
                tu_fresh = True

            self._log("Macro finished")
        except asyncio.CancelledError:
            self._log("Macro stopped")
        except Exception as exc:  # noqa: BLE001 - surface to the activity log
            self._log(f"Macro error: {exc}")
        finally:
            self._monitor.macro_active = False
            self._state.phase = MacroPhase.IDLE
            self._notify()
            self._task = None

    async def _perform_roll(
        self,
        cmd: str,
        roll_index: int,
        session_records: list[RollRecord],
        *,
        us_roll: bool = False,
        stop_on_interrupt: bool = True,
    ) -> _RollOutcome:
        """Send one roll, log it, react, and optionally claim on an interrupt trigger."""
        self._state.phase = MacroPhase.ROLLING
        self._notify()

        self._log(f"Roll {roll_index}: ${cmd}")
        await self._actions.send_command(cmd, prefix=self._config.prefix)
        result = await self._actions.wait_for_roll(
            roll_command=cmd,
            timeout=_ROLL_EMBED_TIMEOUT_SEC,
        )
        if result is None:
            self._log("Roll embed timeout")
            return _RollOutcome(ok=False)

        outcome = await self._process_roll_embed(
            result[0],
            result[1],
            roll_index,
            session_records,
            us_roll=us_roll,
            stop_on_interrupt=stop_on_interrupt,
        )
        if not outcome.ok:
            return outcome

        spawn_outcome = await self._handle_perk6_spawn_followup(
            parent_name=result[1].fields.get("character_name"),
            roll_index=roll_index,
            session_records=session_records,
            us_roll=us_roll,
            stop_on_interrupt=stop_on_interrupt,
            rolls_left=outcome.rolls_left,
        )
        if spawn_outcome is None:
            return outcome
        if spawn_outcome.stop:
            return spawn_outcome
        if spawn_outcome.claimed:
            outcome = _RollOutcome(
                ok=True,
                rolls_left=outcome.rolls_left,
                claimed=True,
                stop=False,
            )
        return outcome

    async def _process_roll_embed(
        self,
        snapshot: Any,
        parsed: Any,
        roll_index: int,
        session_records: list[RollRecord],
        *,
        us_roll: bool,
        stop_on_interrupt: bool,
        log_prefix: str = "",
    ) -> _RollOutcome:
        """Run claim / kakera / sphere checks for one character embed."""
        fields = dict(parsed.fields)
        name = fields.get("character_name") or "?"
        ka = fields.get("total_kakera")
        ka_text = f" · {ka} ka" if ka is not None else ""
        wished = fields.get("wished_by")
        if wished:
            ka_text += f" · wish×{len(wished)}"
        spawn_note = ""
        if fields.get("perk_6"):
            spawner = fields.get("spawned_by") or "?"
            spawn_note = f" · perk 6 spawn by {spawner}"
        self._log(f"{log_prefix}→ {name}{ka_text}{spawn_note}")

        rl = fields.get("rolls_left")
        if rl is not None and not fields.get("perk_6"):
            self._state.rolls_left = int(rl)

        record = RollRecord(
            message_id=snapshot.message_id,
            character_name=fields.get("character_name"),
            fields=fields,
            rolled_at=time.monotonic(),
        )
        session_records.append(record)

        interrupt = evaluate_claim_trigger(
            RollInterruptContext(
                fields=fields,
                own_user_ids=self._state.own_user_ids,
            ),
            self._config.character_claim,
            self._state,
            final_hour=self._final_roll_session,
        )
        if interrupt is not None:
            if stop_on_interrupt:
                self._log(f"{interrupt.reason} — stop rolling, claim now")
            else:
                self._log(f"{interrupt.reason} — claim now (continuing $us rolls)")
            self._state.append_rule_trace(
                RuleTraceEntry(
                    block="character",
                    roll_index=roll_index,
                    character=name,
                    decision="claim",
                    reason=interrupt.reason,
                )
            )
            self._state.phase = MacroPhase.POST_ROLL
            self._notify()
            claimed = await self._make_post_roll_handler().claim_record(
                record,
                reason=interrupt.reason,
            )
            return _RollOutcome(
                ok=True,
                rolls_left=rl,
                claimed=claimed,
                stop=stop_on_interrupt,
            )

        kakera_rules = self._config.kakera_rules_for_roll(us_roll=us_roll)
        await self._make_kakera_reactor().react(
            message_id=snapshot.message_id,
            fields=fields,
            roll_index=roll_index,
            rules=kakera_rules,
        )
        await self._make_sphere_reactor().react(
            message_id=snapshot.message_id,
            fields=fields,
            roll_index=roll_index,
        )
        return _RollOutcome(ok=True, rolls_left=rl)

    async def _handle_perk6_spawn_followup(
        self,
        *,
        parent_name: str | None,
        roll_index: int,
        session_records: list[RollRecord],
        us_roll: bool,
        stop_on_interrupt: bool,
        rolls_left: int | None,
    ) -> _RollOutcome | None:
        """Wait for and process a perk-6 spawn triggered by the roll just handled."""
        if not parent_name:
            return None

        result = await self._actions.wait_for_perk6_spawn(
            parent_character=parent_name,
            timeout=_PERK6_SPAWN_WAIT_SEC,
        )
        if result is None:
            return None

        snapshot, parsed = result
        spawn_name = parsed.fields.get("character_name") or "?"
        spawner = parsed.fields.get("spawned_by") or parent_name
        self._log(
            f"perk 6: {spawn_name} spawned by {spawner} "
            f"(roll {roll_index}) — reacting before next roll"
        )
        self._state.append_rule_trace(
            RuleTraceEntry(
                block="perk_6",
                roll_index=roll_index,
                character=spawn_name,
                decision="spawn",
                reason=f"spawned by {spawner}",
            )
        )
        self._notify()

        spawn_outcome = await self._process_roll_embed(
            snapshot,
            parsed,
            roll_index,
            session_records,
            us_roll=us_roll,
            stop_on_interrupt=stop_on_interrupt,
            log_prefix="perk 6 · ",
        )
        if spawn_outcome.rolls_left is None:
            spawn_outcome = _RollOutcome(
                ok=spawn_outcome.ok,
                rolls_left=rolls_left,
                claimed=spawn_outcome.claimed,
                stop=spawn_outcome.stop,
            )
        self._log(
            f"perk 6: settled — waiting {_PERK6_POST_SETTLE_SEC:g}s "
            "before next roll"
        )
        await asyncio.sleep(_PERK6_POST_SETTLE_SEC)
        return spawn_outcome

    async def _claim_best_at_session_end(
        self,
        session_records: list[RollRecord],
        claimed_via_interrupt: bool,
    ) -> None:
        if (
            session_records
            and not self._stop.is_set()
            and not claimed_via_interrupt
            and self._final_roll_session
        ):
            self._state.phase = MacroPhase.POST_ROLL
            self._notify()
            await self._make_post_roll_handler().claim_best(
                session_records,
                context="final roll hour before claim reset",
                final_hour=True,
            )
        elif session_records and not claimed_via_interrupt and not self._final_roll_session:
            rules = self._config.character_claim
            if rules.enabled and not rules.only_final_hour:
                self._state.phase = MacroPhase.POST_ROLL
                self._notify()
                await self._make_post_roll_handler().claim_best(
                    session_records,
                    context="batch end (any hour)",
                    final_hour=False,
                )
            else:
                self._log(
                    f"Rolled {len(session_records)} this hour — "
                    "claim best skipped (not final hour; buttons expire)"
                )

    def _reset_roll_stop_tracker(self) -> None:
        self._sync_roll_stop_config()
        self._roll_stop = RollStopTracker(
            threshold=self._roll_stop.threshold,
            tail_count=self._roll_stop.tail_count,
        )

    def _should_roll_normal_in_us_mode(self) -> bool:
        """True while normal hourly rolls still need the standard macro pass."""
        rl = self._state.rolls_left
        if rl is None or int(rl) <= 0:
            return False
        self._sync_roll_stop_config()
        if self._roll_stop.tail_remaining is not None and self._roll_stop.tail_remaining > 0:
            return True
        if self._roll_stop.saw_warning:
            return False
        return int(rl) > self._roll_stop.threshold

    async def _run_normal_roll_segment(
        self,
        cmd: str,
        session_records: list[RollRecord],
        start_index: int,
        *,
        respect_roll_stop: bool = True,
        max_rolls: int | None = None,
    ) -> tuple[int, bool]:
        """Roll normal hourly rolls with standard stop/interrupt rules.

        Returns ``(rolls_done, claimed_via_interrupt)``.
        """
        if respect_roll_stop:
            self._sync_roll_stop_config()

        claimed_via_interrupt = False
        done = 0
        stop_rolling = False

        while not self._stop.is_set() and not stop_rolling:
            if max_rolls is not None and done >= max_rolls:
                break
            if respect_roll_stop and self._roll_stop.should_stop_before_roll(
                self._state.rolls_left
            ):
                break

            outcome = await self._perform_roll(
                cmd,
                start_index + done + 1,
                session_records,
                us_roll=False,
                stop_on_interrupt=True,
            )
            if not outcome.ok:
                break
            done += 1
            if outcome.stop:
                claimed_via_interrupt = outcome.claimed
                break

            if respect_roll_stop:
                rl = outcome.rolls_left
                if (
                    rl is not None
                    and int(rl) == self._roll_stop.threshold
                    and not self._roll_stop.saw_warning
                ):
                    self._log(
                        f"Parsed {rl} rolls left — "
                        f"{self._roll_stop.tail_count} more roll(s) then stop"
                    )
                if self._roll_stop.on_roll_parsed(
                    int(rl) if rl is not None else None
                ):
                    self._log("Finished rolls after warning")
                    stop_rolling = True

            await asyncio.sleep(self._config.roll_delay())

        return done, claimed_via_interrupt

    async def _run_us_cycle(self) -> None:
        """Roll out the usable pool, top it up from the ``$us`` stack, repeat.

        Mudae's ``$us`` stack holds a pool of rolls; ``$us <1-20>`` moves that
        many into the usable count until the next rolls reset, where they (and
        any unused ``$us`` rolls) are wiped. So this loop:

        * always rolls out the *usable* rolls first (normal + already-added
          ``$us`` rolls) so nothing is skipped;
        * tops up with ``$us <n>`` only when the usable pool hits zero;
        * reads the authoritative stacked total via a bare ``$us`` to decide how
          many to request and to know when the stack is exhausted (< 1 left);
        * refuses to add when the hourly rolls reset is within
          ``us_reset_margin_minutes`` — fresh ``$us`` rolls would be wiped;
          pauses until the reset passes, then resumes (rolls normal rolls first).
        """
        try:
            self._monitor.macro_active = True
            self._actions.drain_queue()
            self._reset_roll_stop_tracker()
            cmd = self._config.normalized_roll_command()
            max_request = self._config.us_batch()
            margin = max(0, self._config.us_reset_margin_minutes)
            add_delay = self._config.us_add_delay()
            read_before_add_delay = self._config.us_read_before_add_delay()
            session_records: list[RollRecord] = []
            claimed_any = False
            roll_index = 0

            # Track the stack locally so the steady state is just
            # "$tu -> $us N -> roll", with no extra bare "$us" between adds — two
            # commands back to back is what Mudae was ignoring.
            us_stack: float | None = None
            last_request = 0
            failed_adds = 0
            roll_timeouts = 0

            self._log("$us mode: starting")

            await self._refresh_perk8_status()

            while not self._stop.is_set():
                if not await self.run_tu():
                    self._log("$us mode: $tu failed — stopping")
                    break

                await self._maybe_refresh_perk8_status()

                normal_rolls = self._state.rolls_left or 0
                us_bonus = self._state.rolls_us_bonus or 0
                reset_m = self._state.rolls_reset_minutes

                if reset_m is not None and reset_m <= margin:
                    if normal_rolls > 0 or us_bonus > 0:
                        self._log(
                            f"$us mode: rolls reset in {reset_m}m — rolling out "
                            f"{normal_rolls + us_bonus} usable roll(s) before they reset"
                        )
                        if normal_rolls > 0:
                            self._reset_roll_stop_tracker()
                            segment_start = len(session_records)
                            done, claimed = await self._run_normal_roll_segment(
                                cmd,
                                session_records,
                                roll_index,
                                respect_roll_stop=False,
                                max_rolls=normal_rolls,
                            )
                            roll_index += done
                            claimed_any = claimed_any or claimed
                            await self._claim_best_at_session_end(
                                session_records[segment_start:],
                                claimed,
                            )
                            keep, roll_timeouts = await self._handle_us_roll_timeout(
                                done, normal_rolls, roll_timeouts
                            )
                            if not keep:
                                break
                            if done < normal_rolls:
                                continue
                        if us_bonus > 0:
                            done, claimed = await self._roll_us_batch(
                                cmd,
                                us_bonus,
                                session_records,
                                roll_index,
                                us_roll=True,
                            )
                            roll_index += done
                            claimed_any = claimed_any or claimed
                            keep, roll_timeouts = await self._handle_us_roll_timeout(
                                done, us_bonus, roll_timeouts
                            )
                            if not keep:
                                break
                            if done < us_bonus:
                                continue
                    if not await self._wait_for_rolls_reset(margin):
                        break
                    us_stack = None
                    last_request = 0
                    failed_adds = 0
                    self._reset_roll_stop_tracker()
                    continue

                if self._should_roll_normal_in_us_mode():
                    self._log(
                        f"$us mode: {normal_rolls} normal roll(s) — "
                        "standard macro rules"
                    )
                    segment_start = len(session_records)
                    done, claimed = await self._run_normal_roll_segment(
                        cmd,
                        session_records,
                        roll_index,
                    )
                    roll_index += done
                    claimed_any = claimed_any or claimed
                    if done == 0 and not claimed:
                        self._log("$us mode: normal roll failed — stopping")
                        break
                    await self._claim_best_at_session_end(
                        session_records[segment_start:],
                        claimed,
                    )
                    continue

                if us_bonus > 0:
                    if last_request > 0 and us_stack is not None:
                        us_stack -= last_request
                    last_request = 0
                    failed_adds = 0

                    done, claimed = await self._roll_us_batch(
                        cmd,
                        us_bonus,
                        session_records,
                        roll_index,
                        us_roll=True,
                    )
                    roll_index += done
                    claimed_any = claimed_any or claimed
                    keep, roll_timeouts = await self._handle_us_roll_timeout(
                        done, us_bonus, roll_timeouts
                    )
                    if not keep:
                        break
                    if done < us_bonus:
                        continue
                    continue

                # Usable pool is empty. A previous "$us N" that left us at zero
                # means Mudae ignored it — re-read the authoritative stack and
                # count the miss so we don't loop forever.
                just_read_stack = False
                if us_stack is None or failed_adds > 0:
                    fresh = await self._read_us_stack()
                    if fresh is None:
                        self._log("$us mode: could not read $us stack — stopping")
                        break
                    us_stack = fresh
                    just_read_stack = True

                if us_stack < 1:
                    self._log("$us mode: no $us rolls left in the stack — stopping")
                    break

                request = min(max_request, int(us_stack))
                if just_read_stack:
                    self._log(
                        f"$us mode: waiting {read_before_add_delay:g}s after "
                        f"$us read before adding rolls"
                    )
                    await asyncio.sleep(read_before_add_delay)
                self._log(
                    f"$us mode: {us_stack:g} stacked — adding "
                    f"{self._config.prefix}us {request}"
                )
                await self._actions.send_command(f"us {request}", prefix=self._config.prefix)
                last_request = request
                failed_adds += 1
                if failed_adds >= _MAX_FAILED_US_ADDS:
                    self._log(
                        f"$us mode: ${self._config.prefix}us {request} not registering "
                        f"after {failed_adds} attempts — stopping (Mudae ignored it)"
                    )
                    break
                await asyncio.sleep(add_delay)

            await self._claim_best_at_session_end(session_records, claimed_any)
            self._log(f"$us mode: finished ({roll_index} roll(s))")
        except asyncio.CancelledError:
            self._log("$us mode stopped")
        except Exception as exc:  # noqa: BLE001 - surface to the activity log
            self._log(f"$us mode error: {exc}")
        finally:
            self._monitor.macro_active = False
            self._state.phase = MacroPhase.IDLE
            self._notify()
            self._task = None

    async def _handle_us_roll_timeout(
        self,
        done: int,
        planned: int,
        roll_timeouts: int,
    ) -> tuple[bool, int]:
        """On a partial batch (roll embed timeout), wait and resume $us mode.

        Returns ``(keep_running, roll_timeouts)``. Resets the counter when the
        full planned batch completes.
        """
        if done >= planned:
            return True, 0
        roll_timeouts += 1
        if roll_timeouts >= _MAX_ROLL_TIMEOUT_RETRIES:
            self._log(
                f"$us mode: roll timeout after {done}/{planned} roll(s) — "
                f"no Mudae character embed within {_ROLL_EMBED_TIMEOUT_SEC:g}s; "
                f"stopped after {roll_timeouts} retries"
            )
            return False, roll_timeouts
        delay = self._config.us_roll_timeout_retry_delay()
        self._log(
            f"$us mode: roll timeout after {done}/{planned} roll(s) — "
            f"no character embed within {_ROLL_EMBED_TIMEOUT_SEC:g}s; "
            f"waiting {delay:g}s then resuming "
            f"({roll_timeouts}/{_MAX_ROLL_TIMEOUT_RETRIES})"
        )
        await asyncio.sleep(delay)
        return True, roll_timeouts

    def _seconds_until_rolls_reset(self) -> float:
        """Wall-clock seconds until the next hourly rolls reset from the last ``$tu``."""
        reset_m = self._state.rolls_reset_minutes
        if reset_m is None:
            return 0.0
        return max(0.0, reset_m * 60.0 + _ROLLS_RESET_BUFFER_SEC)

    def _seconds_until_perk8_refresh(self) -> float | None:
        """Seconds until the stored perk-8 daily refill, or ``0`` if it just passed.

        Returns ``None`` when no timed perk-8 wake is needed during a long sleep
        (normal active mode — do not spam ``$ohu8`` every second).
        """
        if not self._config.kakera_reaction.perk_8_budget_mode:
            return None
        daily = self._get_daily_resets()
        record = refresh_exhausted_if_refill_passed(load_perk8_record(daily))
        if not record.clicks_exhausted or not record.refill_at:
            return None
        try:
            refill_at = dt.datetime.fromisoformat(
                record.refill_at.replace("Z", "+00:00")
            )
        except ValueError:
            return None
        now = dt.datetime.now(dt.timezone.utc)
        if now >= refill_at:
            return 0.0
        return (refill_at - now).total_seconds()

    async def _sleep_interruptible(self, seconds: float) -> bool:
        """Sleep up to ``seconds``. Returns False if the macro was stopped."""
        remaining = max(0.0, seconds)
        while remaining > 0:
            if self._stop.is_set():
                return False
            step = min(remaining, _STOP_CHECK_SEC)
            await asyncio.sleep(step)
            remaining -= step
        return True

    async def _wait_for_scheduled_wake(self, seconds: float) -> bool:
        """Sleep until a deadline, waking early for perk-8 refresh if needed."""
        remaining = max(0.0, seconds)
        while remaining > 0:
            if self._stop.is_set():
                return False
            perk8_sec = self._seconds_until_perk8_refresh()
            if perk8_sec is not None and perk8_sec <= 0:
                await self._maybe_refresh_perk8_status()
            step = min(remaining, _STOP_CHECK_SEC)
            if perk8_sec is not None and 0 < perk8_sec < step:
                step = min(step, perk8_sec)
            await asyncio.sleep(step)
            remaining -= step
            if perk8_sec is not None and 0 < perk8_sec <= step:
                await self._maybe_refresh_perk8_status()
        return True

    async def _wait_for_rolls_reset(self, margin: int) -> bool:
        """Pause until the hourly rolls reset is no longer imminent.

        Returns False if the user stops the macro or ``$tu`` fails repeatedly.
        """
        poll_sec = _RESET_POLL_SEC
        self._log(
            "$us mode: pausing until rolls reset "
            "(won't add $us rolls that would be wiped at reset)"
        )
        while not self._stop.is_set():
            await asyncio.sleep(poll_sec)
            await self._maybe_refresh_perk8_status()
            if not await self.run_tu():
                self._log("$us mode: $tu failed while waiting for rolls reset")
                return False
            reset_m = self._state.rolls_reset_minutes
            if reset_m is None or reset_m > margin:
                note = f"next reset in {reset_m}m" if reset_m is not None else "reset passed"
                self._log(f"$us mode: rolls reset complete ({note}) — resuming")
                return True
        return False

    async def _wait_for_hourly_refill(self) -> bool:
        """Wait until the parsed rolls-reset time, then confirm with ``$tu``."""
        if self._state.rolls_reset_minutes is None:
            self._log("No rolls reset time from $tu — stopping")
            return False

        while not self._stop.is_set():
            reset_m = self._state.rolls_reset_minutes
            if reset_m is None:
                self._log("No rolls reset time from $tu — stopping")
                return False

            self._log(
                f"No rolls remaining — waiting {reset_m}m until hourly refill"
            )
            if not await self._wait_for_scheduled_wake(self._seconds_until_rolls_reset()):
                return False

            await self._maybe_refresh_perk8_status()
            if not await self.run_tu():
                self._log("$tu failed while waiting for hourly rolls")
                return False

            if (self._state.rolls_left or 0) > 0:
                self._log(
                    f"Hourly rolls available "
                    f"({self._state.rolls_left} roll(s))"
                )
                return True

            new_reset = self._state.rolls_reset_minutes
            if new_reset is not None:
                self._log(f"Reset passed but no rolls yet — waiting {new_reset}m")
                continue

            return False

        return False

    async def _read_us_stack(self) -> float | None:
        """Send a bare ``$us`` and return the stacked-roll pool size."""
        self._actions.drain_queue()
        await self._actions.send_command("us", prefix=self._config.prefix)
        result = await self._actions.wait_for(
            lambda snapshot, _parsed: is_us_stack_response(
                getattr(snapshot, "content", "") or ""
            ),
            timeout=_RESPONSE_TIMEOUT_SEC,
        )
        if result is None:
            return None
        return parse_us_stacked(result[0].content or "")

    async def _roll_us_batch(
        self,
        cmd: str,
        count: int,
        session_records: list[RollRecord],
        start_index: int,
        *,
        us_roll: bool = True,
    ) -> tuple[int, bool]:
        """Roll ``count`` times. Returns ``(rolls_done, claimed_any)``.

        Unlike the normal cycle, an interrupt claim does not end the run — the
        claim is consumed but mass rolling continues so the whole ``$us`` pool
        is used.
        """
        claimed_any = False
        done = 0
        for _ in range(count):
            if self._stop.is_set():
                break
            outcome = await self._perform_roll(
                cmd,
                start_index + done + 1,
                session_records,
                us_roll=us_roll,
                stop_on_interrupt=False,
            )
            if not outcome.ok:
                break
            done += 1
            if outcome.claimed:
                claimed_any = True
            await asyncio.sleep(self._config.roll_delay())
        return done, claimed_any

    def apply_settings_fields(self, fields: dict[str, Any]) -> None:
        """Update claim timer from parsed $settings (``settimer``)."""
        timer = fields.get("settimer")
        if timer is not None:
            self._state.claim_expire_sec = int(timer)

    def _apply_tu_fields(self, fields: dict[str, Any]) -> None:
        if "rolls_left" in fields and fields["rolls_left"] is not None:
            self._state.rolls_left = int(fields["rolls_left"])
        # Always refresh the $us bonus (None when $tu no longer reports one).
        us_bonus = fields.get("rolls_us_bonus")
        self._state.rolls_us_bonus = int(us_bonus) if us_bonus is not None else None
        if "claim_available" in fields:
            self._state.claim_available = fields["claim_available"]
        if "claim_cooldown_minutes" in fields:
            self._state.claim_cooldown_minutes = fields["claim_cooldown_minutes"]
        sync_reaction_power_fields(self._state, fields)
        sync_dk_fields_from_tu(self._state, fields)
        if "rolls_reset_minutes" in fields:
            self._state.rolls_reset_minutes = int(fields["rolls_reset_minutes"])
        if "next_claim_reset_minutes" in fields and fields["next_claim_reset_minutes"] is not None:
            self._state.next_claim_reset_minutes = int(fields["next_claim_reset_minutes"])
