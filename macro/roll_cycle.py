"""Roll-cycle macro engine: $tu, roll until stop, then claim best character."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions, is_perk6_spawn_parse_result
from macro.activity_log import ActivityLog, ActivitySeverity
from macro.connection_recovery import ConnectionRecovery
from macro.roll_context import RollContext
from macro.roll_scheduler import (
    earliest_wake_seconds,
    seconds_until_rolls_reset,
    sleep_interruptible,
    wait_for_scheduled_wake,
)
from macro.session_log import SessionLogRecorder
from macro.claim_window import is_final_roll_session_before_claim_reset
from macro.config import MacroConfig
from macro.runtime_store import (
    RuntimeRestoreResult,
    apply_to_state,
    can_skip_initial_tu,
    load_runtime_record,
    save_runtime_record,
    snapshot_from_state,
)
from macro.us_schedule import (
    in_local_window,
    seconds_until_window_end,
    seconds_until_window_start,
)
from macro.us_stop import (
    UsModeStopOptions,
    us_kakera_power_exhausted,
    us_stop_can_pause,
    us_stop_from_config,
    us_stop_reason,
    _minimum_kakera_cost,
)
from mudae.discord_errors import is_fatal_runtime_error
from macro.perk8_daily import Perk8DailyRecord, Perk8PriorityMode
from macro.kakera_reactor import KakeraReactor
from macro.chaos_followup import chaos_extra_rolls, merge_tu_hourly_rolls
from macro.perk8_runtime import Perk8Runtime
from macro.post_roll import PostRollHandler, RollRecord
from macro.roll_interrupts import RollInterruptContext, evaluate_claim_trigger
from macro.roll_stop import ROLLS_LEFT_STOP, RollStopTracker
from macro.rt_manager import should_stop_after_wish_claim
from macro.reaction_power import sync_reaction_power_fields
from macro.dk_manager import sync_dk_fields_from_tu
from macro.sphere_reactor import SphereReactor
from macro.state import AccountState, MacroPhase
from mudae.parsers.us import is_us_stack_response, parse_us_stacked
from mudae.parsers.pipeline import parse_mudae_message
from mudae.live_feed import format_roll_line
from mudae.types import MessageKind
from mudae.buttons import is_kakera_button, is_sphere_button

# Stop $us mode after this many consecutive "$us N" sends fail to register
# (Mudae ignores rapid follow-ups, so the usable roll count never rises).
_MAX_FAILED_US_ADDS = 3
# Stop $us mode after this many consecutive roll timeouts (no embed arrived).
_MAX_ROLL_TIMEOUT_RETRIES = 5
# After this many consecutive roll timeouts, force a Discord reconnect.
_ROLL_TIMEOUT_RECONNECT_AFTER = 2

# Timing knobs shared by the roll loops (seconds).
_COMMAND_SETTLE_SEC = 2.5  # pause after $tu before polling for the reply
_RESPONSE_TIMEOUT_SEC = 12.0  # max wait for a $tu / $ohu8 / $us text reply
# Progressive waits for a missed roll embed; resend the roll command between stages.
_ROLL_EMBED_TIMEOUTS_SEC = (5.0, 10.0, 25.0)
_ROLL_EMBED_TIMEOUT_SEC = _ROLL_EMBED_TIMEOUTS_SEC[-1]  # used in timeout log text
_RESET_POLL_SEC = 30.0  # $tu poll interval while paused for the rolls reset ($us mode)
_PERK6_SPAWN_WAIT_SEC = 0.5  # brief poll; queue drain catches late spawns
_PERK6_SPAWN_POLL_SEC = 0.25
_PERK6_POST_SETTLE_SEC = 1.2  # pause after spawn reactions before next roll
_US_ADD_SETTLE_SEC = 1.0  # pause after $us N before the first $wa


@dataclass
class _RollOutcome:
    """Result of a single roll performed by :meth:`RollCycleEngine._perform_roll`."""

    ok: bool  # roll embed received and processed
    rolls_left: int | None = None
    claimed: bool = False  # a claim was made on this roll via the interrupt path
    stop: bool = False  # caller should stop the *normal* roll loop (interrupt claim)
    roll_limit: bool = False  # Mudae hourly roll limit (no embed)


class RollCycleEngine:
    def __init__(
        self,
        actions: DiscordActions,
        config: MacroConfig,
        state: AccountState,
        monitor: Any,
        *,
        on_state: Callable[[], None] | None = None,
        on_keys: Callable[[], None] | None = None,
        on_persist: Callable[[], None] | None = None,
        daily_resets_get: Callable[[], dict[str, Any]] | None = None,
        daily_resets_save: Callable[[dict[str, Any]], None] | None = None,
        notification_disconnect: Callable[[], Any] | None = None,
        notification_reconnect: Callable[[], Any] | None = None,
        account_id: str = "",
        on_priority_pause: Callable[[], Any] | None = None,
        priority_wake_hint: Callable[[], float | None] | None = None,
        play_daily_minigames: Callable[[], Awaitable[None]] | None = None,
        notification_connection_held: Callable[[], bool] | None = None,
    ) -> None:
        self._actions = actions
        self._config = config
        self._state = state
        self._monitor = monitor
        self._on_state = on_state
        self._on_keys = on_keys
        self._on_persist = on_persist
        self._on_priority_pause = on_priority_pause
        self._priority_wake_hint = priority_wake_hint
        self._play_daily_minigames = play_daily_minigames
        self._notification_connection_held = notification_connection_held
        self._daily_get = daily_resets_get
        self._daily_save = daily_resets_save
        self._channel_settings: dict[str, Any] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._roll_stop = RollStopTracker()
        self._us_stop = UsModeStopOptions()
        self._us_rolls_done = 0
        self._us_schedule_entered = False
        self._us_schedule_wait_logged = False
        self._us_halt_reason: str | None = None
        self._waiting_for_hourly_refill = False
        self._activity = ActivityLog(self._state, on_update=self._notify)
        self._session: SessionLogRecorder | None = None
        self._final_roll_session = False
        self._ctx = RollContext(
            actions=actions,
            config=config,
            state=state,
            monitor=monitor,
            stop=self._stop,
            account_id=account_id,
            log=self._log,
            log_debug=self._log_debug,
            notify=self._notify,
            sleep=self._sleep,
        )
        self._recovery = ConnectionRecovery(
            self._ctx,
            notification_disconnect=notification_disconnect,
            notification_reconnect=notification_reconnect,
        )
        self._perk8 = Perk8Runtime(
            self._ctx,
            daily_get=daily_resets_get,
            daily_save=daily_resets_save,
            on_busy=lambda: self._set_phase(MacroPhase.CHECKING_TU),
            on_idle=lambda: self._set_phase(MacroPhase.IDLE),
            response_timeout_sec=_RESPONSE_TIMEOUT_SEC,
        )

    def _set_phase(self, phase: MacroPhase) -> None:
        self._state.phase = phase

    @property
    def _pending_perk8_refresh(self) -> bool:
        return self._perk8.pending

    @_pending_perk8_refresh.setter
    def _pending_perk8_refresh(self, value: bool) -> None:
        if value:
            self._perk8.mark_pending()
        else:
            self._perk8.clear_pending()

    async def _sleep(self, seconds: float) -> None:
        # Routed through this module so tests patching ``macro.roll_cycle.asyncio``
        # still intercept waits taken inside extracted subsystems.
        await asyncio.sleep(seconds)

    def _notify(self) -> None:
        if not self._on_state:
            return
        try:
            self._on_state()
        except RuntimeError:
            # GUI may already be torn down while a macro task finishes.
            pass

    def _notify_keys(self) -> None:
        if self._on_keys:
            self._on_keys()

    def _persist(self) -> None:
        if self._on_persist:
            self._on_persist()

    def _persist_tu_state_enabled(self) -> bool:
        return bool(self._config.character_claim.persist_tu_state)

    def _save_runtime_state(self) -> None:
        if not self._daily_get or not self._daily_save:
            return
        daily = self._daily_get()
        record = snapshot_from_state(
            self._state,
            settings=self._channel_settings,
        )
        self._daily_save(save_runtime_record(daily, record))
        self._persist()

    def _restore_runtime_state(self) -> RuntimeRestoreResult:
        if not self._persist_tu_state_enabled() or not self._daily_get:
            return RuntimeRestoreResult(False, True, "persist disabled")
        record = load_runtime_record(self._daily_get())
        result = apply_to_state(
            self._state,
            record,
            settings=self._channel_settings,
        )
        if result.applied:
            self._sync_claim_window_from_tu()
        return result

    async def _release_connection_for_notifications(self) -> bool:
        return await self._recovery.release_for_notifications()

    async def _restore_connection_for_notifications(self) -> bool:
        return await self._recovery.restore_for_notifications()

    def _log(self, text: str) -> None:
        self._activity.write(text)

    def write_activity(
        self,
        text: str,
        *,
        severity: ActivitySeverity | None = None,
    ) -> None:
        self._activity.write(text, severity=severity)

    def _log_debug(self, text: str) -> None:
        self._activity.debug(text)

    async def _force_discord_reconnect(self) -> bool:
        return await self._recovery.force_reconnect()

    async def _recover_transient_connection(
        self,
        exc: BaseException,
        *,
        label: str,
        recoveries: int,
    ) -> int | None:
        return await self._recovery.recover_transient(
            exc,
            label=label,
            recoveries=recoveries,
        )

    async def _send_command_with_reconnect(
        self,
        command: str,
        *,
        label: str,
    ) -> int | None:
        return await self._recovery.send_command_with_reconnect(command, label=label)

    def begin_session(self, mode: str, meta: dict[str, Any]) -> None:
        if self._session and self._session.active:
            self._finish_session("replaced")
        self._session = SessionLogRecorder()
        self._session.start(mode=mode, **meta)
        self._activity.set_session(self._session)
        self._activity.clear()
        channel = meta.get("channel") or "?"
        preset = meta.get("preset") or "?"
        account = meta.get("account") or "?"
        self._log(
            f"Session started · {mode} · {account} · {preset} · {channel}"
        )

    def _finish_session(self, reason: str) -> None:
        from mudae.chaos_capture import close_open_window

        close_open_window("session_end")
        if not self._session or not self._session.active:
            return
        self._activity.write(f"Session ending ({reason})")
        path = self._session.finish(reason)
        self._activity.set_session(None)
        self._session = None
        if path is not None:
            self._log(f"Session log saved: {path.name}")
            self._log_debug(f"session file: {path}")
            self._log_debug(f"session text: {path.with_suffix('.log')}")

    def end_session(self, reason: str) -> None:
        self._finish_session(reason)

    def _sync_roll_stop_config(self) -> None:
        self._roll_stop.threshold = ROLLS_LEFT_STOP
        self._roll_stop.tail_count = ROLLS_LEFT_STOP

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
        on_timeout = None
        if self._config.kakera_reaction.perk_8_budget_mode:
            on_exhausted = self._mark_perk8_exhausted
            on_progress = self._persist_perk8_click_progress
            on_timeout = self._resync_perk8_after_kakera_timeout
        return KakeraReactor(
            actions=self._actions,
            config=self._config,
            state=self._state,
            log=self._log,
            debug_log=self._log_debug,
            on_perk8_exhausted=on_exhausted,
            on_click_progress=on_progress,
            on_click_timeout=on_timeout,
            on_state=self._notify,
            on_keys=self._notify_keys,
        )

    def _get_daily_resets(self) -> dict[str, Any]:
        return self._perk8.load_daily()

    def _save_daily_resets(self, daily: dict[str, Any]) -> None:
        self._perk8.save_daily(daily)

    def _discord_commands_blocked(self) -> bool:
        return self._ctx.commands_blocked

    def _apply_perk8_mode(self, mode: Perk8PriorityMode, record: Perk8DailyRecord) -> None:
        self._perk8.apply_mode(mode, record)

    def _mark_perk8_exhausted(self) -> None:
        self._perk8.mark_exhausted()

    def _persist_perk8_click_progress(self) -> None:
        self._perk8.persist_click_progress()

    async def _resync_perk8_after_kakera_timeout(self) -> None:
        await self._perk8.resync_after_uncertain_click()

    def _sync_perk8_refill_from_tu(self, fields: dict[str, Any]) -> None:
        self._perk8.sync_refill_from_tu(fields)

    async def _refresh_perk8_status(self, *, at_startup: bool = False) -> None:
        await self._perk8.refresh(at_startup=at_startup)

    async def _run_priority_pause(self) -> None:
        """Run account-global ``$p`` / ``$daily`` before rolls when they are due."""
        cb = self._on_priority_pause
        if cb is None:
            return
        result = cb()
        if asyncio.iscoroutine(result):
            await result

    async def _on_scheduled_wake(self) -> None:
        """Run $p/$daily, perk-8, and daily minigames when a wait is interrupted.

        Notification mode drops the gateway during the hourly wait, so reconnect
        first. After the work, disconnect again if we are still waiting for rolls.
        """
        if not await self._restore_connection_for_notifications():
            self._log("Notification mode: reconnect failed — deferring scheduled work")
            return
        try:
            await self._run_priority_pause()
            await self._perk8.maybe_refresh()
            await self._maybe_play_daily_minigames()
        finally:
            held = False
            cb = self._notification_connection_held
            if cb is not None:
                held = bool(cb())
            if self._waiting_for_hourly_refill and not held:
                await self._release_connection_for_notifications()

    async def _maybe_refresh_perk8_status(self) -> None:
        await self._perk8.maybe_refresh()

    async def _maybe_play_daily_minigames(self) -> None:
        """Spend remaining ``$oh`` / ``$oc`` / ``$oq`` once per daily cycle."""
        cb = self._play_daily_minigames
        if cb is None or self._stop.is_set():
            return
        if self._discord_commands_blocked():
            return
        await cb()

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
        done, claimed, _ = await self._run_normal_roll_segment(
            cmd,
            session_records,
            roll_index,
            max_rolls=normal_rolls,
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
            debug_log=self._log_debug,
        )

    def _sync_claim_window_from_tu(self) -> None:
        self._final_roll_session = is_final_roll_session_before_claim_reset(
            self._state.next_claim_reset_minutes,
            self._state.rolls_reset_minutes,
        )

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def running_mode(self) -> str | None:
        """``hourly``, ``us``, or ``None`` when the engine is idle."""
        if not self.is_running or self._task is None:
            return None
        name = self._task.get_name()
        if name == "us-roll-cycle":
            return "us"
        if name == "roll-cycle":
            return "hourly"
        return None

    @property
    def waiting_for_hourly_refill(self) -> bool:
        return bool(self._waiting_for_hourly_refill)

    def update_config(self, config: MacroConfig) -> None:
        # Copy so live preset edits always replace the running snapshot.
        self._config = MacroConfig.from_dict(config.to_dict())
        self._ctx.config = self._config

    def update_run_target(
        self,
        *,
        account_id: str,
        daily_resets_get: Callable[[], dict[str, Any]] | None = None,
        daily_resets_save: Callable[[dict[str, Any]], None] | None = None,
        channel_settings: dict[str, Any] | None = None,
    ) -> None:
        """Rebind per-channel persistence after a live server/channel switch."""
        self._ctx.account_id = account_id
        self._perk8.update_daily_store(
            daily_get=daily_resets_get,
            daily_save=daily_resets_save,
        )
        self._daily_get = daily_resets_get
        self._daily_save = daily_resets_save
        if channel_settings is not None:
            self._channel_settings = dict(channel_settings)
        self._reset_roll_stop_tracker()

    def stop(self) -> None:
        self._stop.set()
        self._state.phase = MacroPhase.STOPPING
        self._notify()
        if self._task and not self._task.done():
            self._task.cancel()

    def save_runtime_state(self) -> None:
        self._save_runtime_state()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

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
        self._save_runtime_state()
        return True

    async def run_us_check(self) -> bool:
        """Send bare ``$us`` and report stacked rolls. Returns False on timeout."""
        if self.is_running:
            return False
        self._actions.drain_queue()
        self._log("Sent $us")
        self._notify()
        stacked = await self._read_us_stack()
        if stacked is None:
            self._log("$us timeout")
            self._notify()
            return False
        self._state.us_stacked = stacked
        self._log(f"$us OK · {stacked:g} stacked")
        self._notify()
        return True

    def start(self, *, session_meta: dict[str, Any] | None = None) -> None:
        if self.is_running:
            return
        if session_meta:
            self.begin_session("hourly", session_meta)
        self._stop.clear()
        self._task = asyncio.create_task(self._run_cycle(), name="roll-cycle")

    def start_us_mode(
        self,
        *,
        session_meta: dict[str, Any] | None = None,
        us_stop: UsModeStopOptions | None = None,
    ) -> None:
        if self.is_running:
            return
        if session_meta:
            self.begin_session("us", session_meta)
        self._us_stop = us_stop or us_stop_from_config(self._config)
        self._us_rolls_done = 0
        self._us_schedule_entered = False
        self._us_schedule_wait_logged = False
        self._us_halt_reason = None
        self._stop.clear()
        self._task = asyncio.create_task(self._run_us_cycle(), name="us-roll-cycle")

    async def _run_cycle(self) -> None:
        session_reason = "finished"
        try:
            self._monitor.macro_active = True
            self._actions.drain_queue()
            self._reset_roll_stop_tracker()

            if not await self._restore_connection_for_notifications():
                self._log("Notification mode: reconnect failed — stopping")
                return

            await self._refresh_perk8_status(at_startup=True)
            await self._run_priority_pause()

            cmd = self._config.normalized_roll_command()
            roll_index = 0
            tu_fresh = False
            if self._persist_tu_state_enabled():
                restore = self._restore_runtime_state()
                if can_skip_initial_tu(restore):
                    tu_fresh = True
                    self._log("Using saved $tu state — skipping initial $tu")
                elif restore.message and restore.message != "persist disabled":
                    self._log(
                        f"Saved $tu state unavailable ({restore.message}) — running $tu"
                    )

            self._log("Macro starting (continuous hourly mode)")

            transient_recoveries = 0
            while not self._stop.is_set():
                try:
                    if not await self._restore_connection_for_notifications():
                        self._log("Notification mode: reconnect failed — stopping")
                        break

                    await self._run_priority_pause()

                    if not tu_fresh:
                        if not await self.run_tu():
                            self._log("$tu failed — stopping")
                            break
                    tu_fresh = False

                    await self._maybe_refresh_perk8_status()
                    await self._maybe_play_daily_minigames()

                    pool = int(self._state.rolls_left or 0)
                    if pool <= 0:
                        if not await self._wait_for_hourly_refill():
                            break
                        tu_fresh = True
                        continue

                    # Fresh record list per hourly batch: claim-best runs inside the
                    # segment, and keeping every hour's records would grow forever
                    # on multi-day runs.
                    session_records: list[RollRecord] = []
                    done, claimed, roll_index = (
                        await self._roll_hourly_normal_segment(
                            cmd,
                            session_records,
                            roll_index,
                            normal_rolls=pool,
                        )
                    )
                    remaining = int(self._state.rolls_left or 0)
                    if done == 0 and not claimed and remaining <= 0:
                        if not await self._wait_for_hourly_refill():
                            break
                        tu_fresh = True
                        continue
                    if done == 0 and not claimed:
                        self._log("Roll failed — stopping")
                        break
                    if claimed:
                        if self._stop.is_set():
                            break
                        if remaining:
                            self._log(
                                f"{remaining} roll(s) left this hour — "
                                "continuing after claim"
                            )
                        tu_fresh = True
                        continue
                    if remaining > 0:
                        # Chaos +N (or a missed footer) grew the pool after this
                        # pass. Keep rolling — do not $tu, which can omit extras.
                        tu_fresh = False
                        continue

                    if not await self._wait_for_hourly_refill():
                        break
                    tu_fresh = True
                except Exception as exc:
                    recovered = await self._recover_transient_connection(
                        exc,
                        label="Macro",
                        recoveries=transient_recoveries,
                    )
                    if recovered is None:
                        raise
                    transient_recoveries = recovered
                    tu_fresh = False

            self._log("Macro finished")
        except asyncio.CancelledError:
            session_reason = "stopped"
            self._log("Macro stopped")
        except Exception as exc:  # noqa: BLE001 - surface to the activity log
            session_reason = "stopped" if is_fatal_runtime_error(exc) else "error"
            self._log(f"Macro error: {exc}")
        finally:
            if self._stop.is_set() and session_reason == "finished":
                session_reason = "stopped"
            self._save_runtime_state()
            self._finish_session(session_reason)
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
        await self._drain_pending_perk6_spawns(
            roll_index,
            session_records,
            us_roll=us_roll,
            stop_on_interrupt=stop_on_interrupt,
        )

        self._state.phase = MacroPhase.ROLLING
        self._notify()

        qsize = getattr(self._actions, "queue_size", lambda: 0)()
        self._log(f"Roll {roll_index}: ${cmd}")
        self._log_debug(f"roll {roll_index}: sending ${cmd} · queue={qsize}")
        await self._send_command_with_reconnect(cmd, label=f"Roll {roll_index}")
        result = None
        waited = 0.0
        for stage, timeout in enumerate(_ROLL_EMBED_TIMEOUTS_SEC, start=1):
            result = await self._actions.wait_for_roll(
                roll_command=cmd,
                timeout=timeout,
            )
            if result is not None:
                break
            waited += timeout
            if stage < len(_ROLL_EMBED_TIMEOUTS_SEC):
                self._log(
                    f"Roll {roll_index}: no embed after {timeout:g}s — "
                    f"resending ${cmd}"
                )
                self._log_debug(
                    f"roll {roll_index}: no embed after {waited:g}s — "
                    f"resending ${cmd} before {_ROLL_EMBED_TIMEOUTS_SEC[stage]:g}s wait"
                )
                await self._send_command_with_reconnect(
                    cmd,
                    label=f"Roll {roll_index} retry",
                )
        if result is None:
            self._log("Roll embed timeout")
            self._log_debug(
                f"roll {roll_index}: embed timeout after {waited:g}s · "
                f"queue={getattr(self._actions, 'queue_size', lambda: 0)()}"
            )
            return _RollOutcome(ok=False)

        snapshot, parsed = result
        if parsed.kind == MessageKind.ROLL_LIMIT:
            fields = parsed.fields
            self._state.rolls_left = 0
            self._state.chaos_rolls_left = 0
            if fields.get("rolls_reset_minutes") is not None:
                self._state.set_rolls_reset(int(fields["rolls_reset_minutes"]))
            self._notify()
            self._log(parsed.summary or "Hourly roll limit reached")
            return _RollOutcome(ok=False, rolls_left=0, roll_limit=True)

        outcome = await self._process_roll_embed(
            snapshot,
            parsed,
            roll_index,
            session_records,
            us_roll=us_roll,
            stop_on_interrupt=stop_on_interrupt,
        )
        if not outcome.ok:
            return outcome

        spawn_outcome = await self._handle_perk6_spawn_followup(
            parent_name=parsed.fields.get("character_name"),
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
        snapshot, parsed = await self._refresh_roll_snapshot(snapshot, parsed)
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
        self._log_debug(f"{log_prefix}→ {name}{ka_text}{spawn_note}")
        self._log(format_roll_line(fields))

        rl = fields.get("rolls_left")
        if not fields.get("perk_6"):
            # Perk-6 spawns are free, so they never come off a pool.
            if rl is not None:
                self._apply_roll_footer_pool_count(int(rl), us_roll=us_roll)
            else:
                self._consume_roll(us_roll=us_roll)
        self._notify()

        record = RollRecord(
            message_id=snapshot.message_id,
            character_name=fields.get("character_name"),
            fields=fields,
            rolled_at=time.monotonic(),
        )
        session_records.append(record)

        if fields.get("keys") or fields.get("omega_keys"):
            from mudae.key_log import record_roll_key_events

            if record_roll_key_events(snapshot, fields, from_macro=True):
                self._notify_keys()

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
            self._state.phase = MacroPhase.POST_ROLL
            self._notify()
            claimed = await self._make_post_roll_handler().claim_record(
                record,
                reason=interrupt.reason,
                allow_rt=interrupt.code == "wish_ping",
            )
            if (
                not us_roll
                and interrupt.code == "wish_ping"
                and claimed
                and should_stop_after_wish_claim(self._state)
            ):
                self._log("Wish claimed — no claim or $rt left, stopping macro")
                self._stop.set()
            return _RollOutcome(
                ok=True,
                rolls_left=rl,
                claimed=claimed,
                stop=stop_on_interrupt,
            )

        kakera_rules = self._config.kakera_rules_for_roll(us_roll=us_roll)
        extras_before = chaos_extra_rolls(self._state)
        await self._make_kakera_reactor().react(
            message_id=snapshot.message_id,
            fields=fields,
            roll_index=roll_index,
            rules=kakera_rules,
        )
        if chaos_extra_rolls(self._state) > extras_before:
            # Pool just grew — abandon a stop-at-2 tail so the new rolls are spent.
            self._reset_roll_stop_tracker()
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

        result = await self._wait_for_matching_perk6_spawn(parent_name)
        if result is None:
            return None

        snapshot, parsed = result
        spawn_outcome = await self._process_perk6_spawn(
            snapshot,
            parsed,
            roll_index=roll_index,
            session_records=session_records,
            us_roll=us_roll,
            stop_on_interrupt=stop_on_interrupt,
            rolls_left=rolls_left,
        )
        self._log(
            f"perk 6: settled — waiting {_PERK6_POST_SETTLE_SEC:g}s "
            "before next roll"
        )
        await asyncio.sleep(_PERK6_POST_SETTLE_SEC)
        return spawn_outcome

    async def _wait_for_matching_perk6_spawn(
        self,
        parent_name: str,
    ) -> tuple[Any, Any] | None:
        """Poll for a perk-6 spawn tied to ``parent_name``, then scan the queue."""
        collect = getattr(self._actions, "collect_queued", None)
        if collect is not None:
            queued = collect(
                lambda snapshot, parsed: (
                    not snapshot.edited
                    and is_perk6_spawn_parse_result(
                        parsed,
                        parent_character=parent_name,
                    )
                )
            )
            if queued:
                return queued[0]

        deadline = time.monotonic() + _PERK6_SPAWN_WAIT_SEC
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = await self._actions.wait_for_perk6_spawn(
                parent_character=parent_name,
                timeout=min(_PERK6_SPAWN_POLL_SEC, remaining),
            )
            if result is not None:
                return result

        if collect is not None:
            queued = collect(
                lambda snapshot, parsed: (
                    not snapshot.edited
                    and is_perk6_spawn_parse_result(
                        parsed,
                        parent_character=parent_name,
                    )
                )
            )
            if queued:
                return queued[0]
        return None

    async def _process_perk6_spawn(
        self,
        snapshot: Any,
        parsed: Any,
        *,
        roll_index: int,
        session_records: list[RollRecord],
        us_roll: bool,
        stop_on_interrupt: bool,
        rolls_left: int | None,
    ) -> _RollOutcome:
        spawn_name = parsed.fields.get("character_name") or "?"
        spawner = parsed.fields.get("spawned_by") or "?"
        self._log(
            f"perk 6: {spawn_name} spawned by {spawner} "
            f"(roll {roll_index}) — reacting before next roll"
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
        return spawn_outcome

    async def _drain_pending_perk6_spawns(
        self,
        roll_index: int,
        session_records: list[RollRecord],
        *,
        us_roll: bool,
        stop_on_interrupt: bool,
    ) -> None:
        """Service perk-6 spawns already sitting in the queue (prevents falling behind)."""
        collect = getattr(self._actions, "collect_queued", None)
        if collect is None:
            return
        pending = collect(
            lambda snapshot, parsed: (
                not snapshot.edited
                and bool(parsed.fields.get("perk_6") or parsed.fields.get("is_perk_6_spawn"))
            )
        )
        for snapshot, parsed in pending:
            spawn_name = parsed.fields.get("character_name") or "?"
            spawner = parsed.fields.get("spawned_by") or "?"
            self._log(
                f"perk 6: queued spawn {spawn_name} (by {spawner}) — "
                "processing before next roll"
            )
            await self._process_perk6_spawn(
                snapshot,
                parsed,
                roll_index=roll_index,
                session_records=session_records,
                us_roll=us_roll,
                stop_on_interrupt=stop_on_interrupt,
                rolls_left=self._state.rolls_left,
            )
            self._log(
                f"perk 6: settled — waiting {_PERK6_POST_SETTLE_SEC:g}s "
                "before next roll"
            )
            await asyncio.sleep(_PERK6_POST_SETTLE_SEC)

    def _roll_has_react_buttons(self, fields: dict[str, Any], snapshot: Any) -> bool:
        buttons = list(fields.get("buttons") or getattr(snapshot, "buttons", []) or [])
        return any(
            isinstance(btn, dict)
            and (is_kakera_button(btn) or is_sphere_button(btn))
            and not btn.get("disabled")
            for btn in buttons
        )

    async def _refresh_roll_snapshot(
        self,
        snapshot: Any,
        parsed: Any,
    ) -> tuple[Any, Any]:
        """Re-fetch slow embeds so kakera/sphere buttons are present before reacting."""
        if self._roll_has_react_buttons(parsed.fields, snapshot):
            return snapshot, parsed
        fetch = getattr(self._monitor, "fetch_message_snapshot", None)
        if fetch is None:
            return snapshot, parsed
        try:
            fresh = await fetch(snapshot.message_id)
        except Exception:
            return snapshot, parsed
        if fresh is None:
            return snapshot, parsed
        fresh_parsed = parse_mudae_message(fresh)
        if self._roll_has_react_buttons(fresh_parsed.fields, fresh):
            return fresh, fresh_parsed
        return snapshot, parsed

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

    def _consume_roll(self, *, us_roll: bool) -> None:
        """Count one roll off the pool this roll was spending.

        Mudae only prints "N rolls left" in a roll footer near the end of the
        pool, so without a local decrement the status bar would sit on the last
        ``$tu`` figure for a whole batch. The next ``$tu`` is authoritative and
        overwrites this, so a wrong guess here is cosmetic and short-lived.

        ``$us`` rolls come off the stacked bonus first — that is why leftover
        normal rolls survive a full ``$us`` cycle and have to be spent explicitly.
        """
        if us_roll:
            bonus = self._state.rolls_us_bonus
            if bonus is not None and bonus > 0:
                self._state.rolls_us_bonus = bonus - 1
                return
        extras = chaos_extra_rolls(self._state)
        if extras > 0:
            self._state.chaos_rolls_left = extras - 1
        left = self._state.rolls_left
        if left is not None and left > 0:
            self._state.rolls_left = left - 1
        if self._persist_tu_state_enabled():
            self._save_runtime_state()

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
        return True

    def _apply_roll_footer_pool_count(self, count: int, *, us_roll: bool) -> None:
        """Map Mudae's low-roll footer to the pool it actually refers to.

        During ``$us`` rolls the footer tracks the ``$us`` usable pool, not hourly
        rolls. Chaos ``+N rolls this hour`` are ordinary hourly rolls and are
        already in this footer when Mudae prints it.
        """
        if us_roll and (self._state.rolls_us_bonus or 0) > 0:
            self._state.rolls_us_bonus = count
            return
        if us_roll:
            return
        extras = chaos_extra_rolls(self._state)
        self._state.rolls_left = count
        if extras > 0:
            self._state.chaos_rolls_left = min(extras, count)

    def _clear_phantom_bonus_normal_rolls(self, *, attempted: int | None = None) -> None:
        """Drop a bogus ``rolls_left`` count after Mudae rejects a normal roll."""
        self._state.rolls_left = 0
        self._state.chaos_rolls_left = 0
        self._notify()
        if attempted is not None:
            self._log(
                f"$us mode: {attempted} bonus normal roll(s) unavailable "
                "(hourly limit) — continuing $us rolls"
            )
        else:
            self._log(
                "$us mode: bonus normal rolls unavailable (hourly limit) — "
                "continuing $us rolls"
            )

    def _leftover_normal_rolls(self) -> int | None:
        """Bonus normal rolls to spend explicitly, or ``None`` for the stop-at-2 tail.

        Mudae announces "N rolls left" in a footer only on the way down past the
        threshold, so a pool that *starts* at or below it never triggers the tail
        and the standard pass would roll nothing. That is how one-off bonus rolls
        (chaos kakera and similar random rewards, often 1–15+) get stranded:
        ``$us`` rolls cycle and refill around them forever while the extras sit
        unused. Spend exactly what ``$tu`` reports, then resume ``$us``.
        """
        self._sync_roll_stop_config()
        rl = self._state.rolls_left
        if rl is None or int(rl) <= 0:
            return None
        if self._roll_stop.tail_remaining is not None and self._roll_stop.tail_remaining > 0:
            return None
        if int(rl) <= self._roll_stop.threshold:
            return int(rl)
        return None

    def _check_us_stop(self) -> str | None:
        rules = self._config.kakera_rules_for_roll(us_roll=True)
        return us_stop_reason(
            options=self._us_stop,
            state=self._state,
            rules=rules,
            us_rolls_done=self._us_rolls_done,
        )

    def _us_in_schedule_window(self) -> bool:
        if not self._us_stop.schedule_enabled:
            return True
        return in_local_window(
            self._us_stop.schedule_start,
            self._us_stop.schedule_end,
        )

    def _us_schedule_phase(self) -> str | None:
        """``None`` to spend ``$us``, ``wait`` until the window, or ``stop``."""
        if not self._us_stop.schedule_enabled:
            return None
        if self._us_in_schedule_window():
            self._us_schedule_entered = True
            return None
        if self._us_schedule_entered:
            return "stop"
        return "wait"

    def _us_halt_kind(self) -> str | None:
        """``None``, ``"pause"``, or ``"stop"`` for the current ``$us`` limits."""
        if self._us_schedule_phase() == "stop":
            self._us_halt_reason = "schedule window ended"
            return "stop"
        reason = self._check_us_stop()
        self._us_halt_reason = reason
        if not reason:
            return None
        if self._us_stop.keep_draining and us_stop_can_pause(reason):
            return "pause"
        return "stop"

    def _log_us_halt(self, kind: str) -> None:
        reason = self._us_halt_reason or self._check_us_stop() or "limit"
        if kind == "pause":
            self._log(f"$us mode: pausing — {reason}")
        else:
            self._log(f"$us mode: stopping — {reason}")

    async def _apply_us_halt(self, halt: str | None) -> str:
        """Turn a halt into ``""``, ``"break"``, or ``"continue"`` for the ``$us`` loop."""
        if halt == "pause":
            if not await self._wait_for_us_power():
                return "break"
            return "continue"
        if halt == "stop":
            return "break"
        return ""

    async def _run_normal_roll_segment(
        self,
        cmd: str,
        session_records: list[RollRecord],
        start_index: int,
        *,
        respect_roll_stop: bool = True,
        max_rolls: int | None = None,
    ) -> tuple[int, bool, bool]:
        """Roll normal hourly rolls with standard stop/interrupt rules.

        Returns ``(rolls_done, claimed_via_interrupt, roll_limit_hit)``.
        """
        if respect_roll_stop:
            self._sync_roll_stop_config()

        claimed_via_interrupt = False
        done = 0
        stop_rolling = False
        roll_limit_hit = False

        while not self._stop.is_set() and not stop_rolling:
            if max_rolls is not None and done >= max_rolls:
                break
            if respect_roll_stop and self._roll_stop.should_stop_before_roll(
                self._state.rolls_left
            ):
                break

            await self._run_priority_pause()

            outcome = await self._perform_roll(
                cmd,
                start_index + done + 1,
                session_records,
                us_roll=False,
                stop_on_interrupt=True,
            )
            if not outcome.ok:
                roll_limit_hit = outcome.roll_limit
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

        return done, claimed_via_interrupt, roll_limit_hit

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
        session_reason = "finished"
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
            self._us_rolls_done = 0
            self._us_schedule_wait_logged = False

            # Track the stack locally so steady state can be "$us N -> roll" once the
            # pool size is known, using Mudae's tick reaction to skip extra $tu polls.
            us_stack: float | None = None
            last_request = 0
            failed_adds = 0
            roll_timeouts = 0
            skip_tu = False
            if self._persist_tu_state_enabled():
                restore = self._restore_runtime_state()
                if can_skip_initial_tu(restore):
                    skip_tu = True
                    self._log("Using saved $tu state — skipping initial $tu")

            stop_bits: list[str] = []
            if self._us_stop.keep_draining:
                stop_bits.append("keep draining (pause on power / reset)")
            if self._us_stop.stop_on_power_exhausted:
                rules = self._config.kakera_rules_for_roll(us_roll=True)
                if rules.enabled:
                    min_cost = _minimum_kakera_cost(self._state, rules)
                    verb = "pause" if self._us_stop.keep_draining else "stop"
                    if min_cost > 0:
                        stop_bits.append(f"{verb} when power < {min_cost:g}%")
                    else:
                        stop_bits.append(f"{verb} on power (paid kakera only)")
            if self._us_stop.stop_after_rolls_enabled:
                stop_bits.append(f"stop after {self._us_stop.stop_after_rolls} rolls")
            if self._us_stop.schedule_enabled:
                stop_bits.append(
                    f"local window {self._us_stop.schedule_start}–"
                    f"{self._us_stop.schedule_end}"
                )
            if stop_bits:
                self._log(f"$us mode: {' · '.join(stop_bits)}")
            self._log("$us mode: starting")

            await self._refresh_perk8_status(at_startup=True)
            await self._run_priority_pause()

            transient_recoveries = 0
            while not self._stop.is_set():
                try:
                    await self._run_priority_pause()
                    if not skip_tu:
                        if not await self.run_tu():
                            self._log("$us mode: $tu failed — stopping")
                            break

                        await self._maybe_refresh_perk8_status()
                    else:
                        skip_tu = False

                    hourly_left = int(self._state.rolls_left or 0)
                    us_bonus = self._state.rolls_us_bonus or 0
                    reset_m = self._state.rolls_reset_minutes

                    if reset_m is not None and reset_m <= margin:
                        if hourly_left > 0 or us_bonus > 0:
                            self._log(
                                f"$us mode: rolls reset in {reset_m}m — rolling out "
                                f"{hourly_left + us_bonus} usable roll(s) "
                                "before they reset"
                            )
                            if hourly_left > 0:
                                self._reset_roll_stop_tracker()
                                segment_start = len(session_records)
                                done, claimed, roll_limit_hit = (
                                    await self._run_normal_roll_segment(
                                        cmd,
                                        session_records,
                                        roll_index,
                                        respect_roll_stop=False,
                                        max_rolls=hourly_left,
                                    )
                                )
                                roll_index += done
                                claimed_any = claimed_any or claimed
                                await self._claim_best_at_session_end(
                                    session_records[segment_start:],
                                    claimed,
                                )
                                if roll_limit_hit and done == 0 and not claimed:
                                    self._clear_phantom_bonus_normal_rolls(
                                        attempted=hourly_left,
                                    )
                                elif done == 0 and not claimed:
                                    keep, roll_timeouts = (
                                        await self._handle_us_roll_timeout(
                                            done, hourly_left, roll_timeouts
                                        )
                                    )
                                    if not keep:
                                        break
                                elif done < hourly_left:
                                    keep, roll_timeouts = (
                                        await self._handle_us_roll_timeout(
                                            done, hourly_left, roll_timeouts
                                        )
                                    )
                                    if not keep:
                                        break
                                    continue
                            if us_bonus > 0:
                                done, claimed, halt = await self._roll_us_batch(
                                    cmd,
                                    us_bonus,
                                    session_records,
                                    roll_index,
                                    us_roll=True,
                                    respect_us_stop=False,
                                )
                                roll_index += done
                                claimed_any = claimed_any or claimed
                                if halt == "stop":
                                    break
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
                        leftover = self._leftover_normal_rolls()
                        hourly_left = int(self._state.rolls_left or 0)
                        max_rolls = leftover
                        if leftover is not None:
                            self._log(
                                f"$us mode: {leftover} bonus normal roll(s) — "
                                "using before $us (chaos kakera / random reward)"
                            )
                        else:
                            self._log(
                                f"$us mode: {hourly_left} normal roll(s) — "
                                "standard macro rules"
                            )
                        segment_start = len(session_records)
                        done, claimed, roll_limit_hit = (
                            await self._run_normal_roll_segment(
                                cmd,
                                session_records,
                                roll_index,
                                respect_roll_stop=leftover is None,
                                max_rolls=max_rolls,
                            )
                        )
                        roll_index += done
                        claimed_any = claimed_any or claimed
                        if roll_limit_hit and done == 0 and not claimed:
                            self._clear_phantom_bonus_normal_rolls(
                                attempted=leftover,
                            )
                            await self._claim_best_at_session_end(
                                session_records[segment_start:],
                                claimed,
                            )
                            continue
                        if done == 0 and not claimed:
                            self._log("$us mode: normal roll failed — stopping")
                            break
                        await self._claim_best_at_session_end(
                            session_records[segment_start:],
                            claimed,
                        )
                        continue

                    if us_bonus > 0:
                        schedule_phase = self._us_schedule_phase()
                        if schedule_phase == "stop":
                            self._log(
                                "$us mode: stopping — schedule window ended "
                                "(leftover $us left on the stack)"
                            )
                            break
                        if schedule_phase == "wait":
                            if not await self._wait_for_us_schedule_window():
                                break
                            skip_tu = False
                            continue
                        if last_request > 0 and us_stack is not None:
                            us_stack -= last_request
                        last_request = 0
                        failed_adds = 0

                        done, claimed, halt = await self._roll_us_batch(
                            cmd,
                            us_bonus,
                            session_records,
                            roll_index,
                            us_roll=True,
                        )
                        roll_index += done
                        claimed_any = claimed_any or claimed
                        if halt:
                            self._log_us_halt(halt)
                            action = await self._apply_us_halt(halt)
                            if action == "break":
                                break
                            skip_tu = False
                            continue
                        keep, roll_timeouts = await self._handle_us_roll_timeout(
                            done, us_bonus, roll_timeouts
                        )
                        if not keep:
                            break
                        if done < us_bonus:
                            continue
                        if done >= us_bonus:
                            self._state.rolls_us_bonus = 0
                            self._notify()
                        if us_stack is not None and us_stack < 1:
                            break
                        if (
                            us_stack is not None
                            and us_stack >= 1
                            and failed_adds == 0
                        ):
                            skip_tu = True
                        continue

                    # Usable pool is empty — add more from the $us stack.
                    schedule_phase = self._us_schedule_phase()
                    if schedule_phase == "stop":
                        self._log(
                            "$us mode: stopping — schedule window ended "
                            "(leftover $us left on the stack)"
                        )
                        break
                    if schedule_phase == "wait":
                        if not await self._wait_for_us_schedule_window():
                            break
                        skip_tu = False
                        continue
                    halt = self._us_halt_kind()
                    if halt:
                        self._log_us_halt(halt)
                        action = await self._apply_us_halt(halt)
                        if action == "break":
                            break
                        skip_tu = False
                        continue
                    if (
                        us_stack is not None
                        and us_stack >= 1
                        and failed_adds == 0
                    ):
                        request = min(max_request, int(us_stack))
                        self._log(
                            f"$us mode: {us_stack:g} stacked — adding "
                            f"{self._config.prefix}us {request}"
                        )
                        message_id = await self._send_command_with_reconnect(
                            f"us {request}",
                            label="$us mode",
                        )
                        last_request = request
                        ticked = bool(
                            message_id
                            and await self._actions.wait_for_mudae_tick(
                                message_id,
                                timeout=add_delay,
                            )
                        )
                        if ticked:
                            us_stack -= request
                            self._state.rolls_us_bonus = request
                            failed_adds = 0
                            last_request = 0
                            self._log(
                                f"$us mode: {self._config.prefix}us {request} "
                                "acknowledged — rolling"
                            )
                            self._notify()
                            await asyncio.sleep(_US_ADD_SETTLE_SEC)
                            skip_tu = True
                            continue

                        self._log(
                            f"$us mode: no Mudae tick on "
                            f"${self._config.prefix}us {request} — checking $tu"
                        )
                        if not await self.run_tu():
                            self._log("$us mode: $tu failed — stopping")
                            break
                        await self._maybe_refresh_perk8_status()
                        confirmed = self._state.rolls_us_bonus or 0
                        if confirmed > 0:
                            us_stack -= request
                            failed_adds = 0
                            last_request = 0
                            skip_tu = True
                            continue

                        failed_adds += 1
                        if failed_adds >= _MAX_FAILED_US_ADDS:
                            self._log(
                                f"$us mode: {self._config.prefix}us {request} "
                                f"not registering after {failed_adds} attempts — "
                                "stopping (Mudae ignored it)"
                            )
                            break
                        us_stack = None
                        last_request = 0
                        await asyncio.sleep(add_delay)
                        continue

                    # Slow path: read the stack (if needed), pause, add, then $tu.
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
                    await self._actions.send_command(
                        f"us {request}", prefix=self._config.prefix
                    )
                    last_request = request
                    failed_adds += 1
                    if failed_adds >= _MAX_FAILED_US_ADDS:
                        self._log(
                            f"$us mode: ${self._config.prefix}us {request} not registering "
                            f"after {failed_adds} attempts — stopping (Mudae ignored it)"
                        )
                        break
                    await asyncio.sleep(add_delay)
                except Exception as exc:
                    recovered = await self._recover_transient_connection(
                        exc,
                        label="$us mode",
                        recoveries=transient_recoveries,
                    )
                    if recovered is None:
                        raise
                    transient_recoveries = recovered
                    us_stack = None
                    last_request = 0
                    continue

            await self._claim_best_at_session_end(session_records, claimed_any)
            self._log(f"$us mode: finished ({roll_index} roll(s))")
        except asyncio.CancelledError:
            session_reason = "stopped"
            self._log("$us mode stopped")
        except Exception as exc:  # noqa: BLE001 - surface to the activity log
            session_reason = "stopped" if is_fatal_runtime_error(exc) else "error"
            self._log(f"$us mode error: {exc}")
        finally:
            if self._stop.is_set() and session_reason == "finished":
                session_reason = "stopped"
            self._save_runtime_state()
            self._finish_session(session_reason)
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
                f"no Mudae character embed after progressive wait; "
                f"stopped after {roll_timeouts} retries"
            )
            return False, roll_timeouts
        if roll_timeouts >= _ROLL_TIMEOUT_RECONNECT_AFTER:
            self._log(
                f"$us mode: {roll_timeouts} consecutive roll timeouts — "
                "forcing Discord reconnect"
            )
            if not await self._force_discord_reconnect():
                self._log("$us mode: reconnect after roll timeout failed — stopping")
                return False, roll_timeouts
            self._actions.drain_queue()
        delay = self._config.us_roll_timeout_retry_delay()
        stages = "/".join(f"{t:g}s" for t in _ROLL_EMBED_TIMEOUTS_SEC)
        self._log(
            f"$us mode: roll timeout after {done}/{planned} roll(s) — "
            f"no character embed ({stages}); "
            f"waiting {delay:g}s then resuming "
            f"({roll_timeouts}/{_MAX_ROLL_TIMEOUT_RETRIES})"
        )
        await asyncio.sleep(delay)
        return True, roll_timeouts

    def _seconds_until_rolls_reset(self) -> float:
        return seconds_until_rolls_reset(
            self._state.rolls_reset_minutes,
            reset_at=self._state.rolls_reset_at,
        )

    def _seconds_until_perk8_refresh(self) -> float | None:
        return self._perk8.seconds_until_refill()

    def _seconds_until_minigame_refill(self) -> float | None:
        from macro.minigame_daily import load_minigame_record, seconds_until_minigame_refill

        if not self._daily_get:
            return None
        return seconds_until_minigame_refill(load_minigame_record(self._daily_get()))

    async def _sleep_interruptible(self, seconds: float) -> bool:
        return await sleep_interruptible(seconds, ctx=self._ctx)

    async def _wait_for_scheduled_wake(self, seconds: float) -> bool:
        """Sleep until a deadline, waking early for $p/$daily, perk-8, or minigames.

        Notification mode reconnects inside ``_on_scheduled_wake`` so those
        commands are not sent with the gateway down.
        """
        return await wait_for_scheduled_wake(
            seconds,
            ctx=self._ctx,
            wake_hint=earliest_wake_seconds(
                self._perk8.seconds_until_refill,
                self._priority_wake_hint,
                self._seconds_until_minigame_refill,
            ),
            on_wake=self._on_scheduled_wake,
        )

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
            if not await self._wait_for_scheduled_wake(poll_sec):
                return False
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

    async def _wait_for_us_power(self) -> bool:
        """Pause until paid kakera is affordable again (regen or usable ``$dk``).

        Returns False if the user stops the macro or ``$tu`` fails repeatedly.
        Daily minigames / perk-8 refresh still run through ``_wait_for_scheduled_wake``.
        """
        rules = self._config.kakera_rules_for_roll(us_roll=True)
        if not us_kakera_power_exhausted(self._state, rules):
            return True
        poll_sec = _RESET_POLL_SEC
        tu_every = 3
        polls = 0
        self._log("$us mode: waiting for reaction power or usable $dk")
        while not self._stop.is_set():
            if (
                self._us_stop.schedule_enabled
                and self._us_schedule_entered
                and not self._us_in_schedule_window()
            ):
                self._log("$us mode: schedule window ended while waiting for power")
                return False
            slice_sec = poll_sec
            until_end = None
            if self._us_stop.schedule_enabled:
                until_end = seconds_until_window_end(
                    self._us_stop.schedule_start,
                    self._us_stop.schedule_end,
                )
                if until_end is not None:
                    slice_sec = min(slice_sec, max(1.0, until_end))
            if not await self._wait_for_scheduled_wake(slice_sec):
                return False
            await self._maybe_refresh_perk8_status()
            polls += 1
            if polls % tu_every == 0:
                if not await self.run_tu():
                    self._log("$us mode: $tu failed while waiting for power")
                    return False
            if not us_kakera_power_exhausted(self._state, rules):
                self._log("$us mode: reaction power recovered — resuming")
                return True
        return False

    async def _wait_for_us_schedule_window(self) -> bool:
        """Pause until the local ``$us`` window. Hourly rolls still get a turn.

        Returns False if the user stops or ``$tu`` fails. Returns True when the
        window is open *or* leftover hourly rolls / an imminent reset should
        run first (the caller continues the main loop).
        """
        start = self._us_stop.schedule_start
        end = self._us_stop.schedule_end
        if not self._us_schedule_wait_logged:
            self._log(
                f"$us mode: waiting until {start} local (window ends {end}) — "
                "hourly rolls still run"
            )
            self._us_schedule_wait_logged = True
        while not self._stop.is_set():
            if self._us_in_schedule_window():
                self._us_schedule_entered = True
                self._log(f"$us mode: {start}–{end} local — starting $us")
                return True
            if (self._state.rolls_left or 0) > 0:
                return True
            margin = max(0, self._config.us_reset_margin_minutes)
            reset_m = self._state.rolls_reset_minutes
            if reset_m is not None and reset_m <= margin:
                return True
            wait_for = seconds_until_window_start(start, end)
            if reset_m is not None:
                until_reset = seconds_until_rolls_reset(
                    reset_m,
                    reset_at=self._state.rolls_reset_at,
                )
                if until_reset > 0:
                    wait_for = min(wait_for, until_reset)
            wait_for = max(1.0, wait_for)
            if not await self._wait_for_scheduled_wake(wait_for):
                return False
            await self._maybe_refresh_perk8_status()
            if not await self.run_tu():
                self._log("$us mode: $tu failed while waiting for schedule")
                return False
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

            if not await self._release_connection_for_notifications():
                self._log("Notification mode: disconnect failed — stopping")
                return False

            until = self._seconds_until_rolls_reset()
            wait_m = int(until // 60)
            self._log(
                f"No rolls remaining — waiting {wait_m}m until hourly refill"
            )
            self._waiting_for_hourly_refill = True
            try:
                woke = await self._wait_for_scheduled_wake(until)
            finally:
                self._waiting_for_hourly_refill = False
            if not woke:
                return False

            if not await self._restore_connection_for_notifications():
                self._log("Notification mode: reconnect failed — stopping")
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
        respect_us_stop: bool = True,
    ) -> tuple[int, bool, str | None]:
        """Roll ``count`` times. Returns ``(rolls_done, claimed_any, halt)``.

        ``halt`` is ``None``, ``"stop"``, or ``"pause"``. Unlike the normal
        cycle, an interrupt claim does not end the run — the claim is consumed
        but mass rolling continues so the whole ``$us`` pool is used unless a
        user stop limit triggers. Reset-imminent leftover rolls pass
        ``respect_us_stop=False`` so a power pause cannot sit through the wipe.
        """
        claimed_any = False
        done = 0
        if respect_us_stop and us_roll and count > 0:
            halt = self._us_halt_kind()
            if halt:
                return 0, False, halt
        for _ in range(count):
            if self._stop.is_set():
                break
            await self._run_priority_pause()
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
            if us_roll:
                self._us_rolls_done += 1
                if respect_us_stop:
                    halt = self._us_halt_kind()
                    if halt:
                        return done, claimed_any, halt
            if outcome.claimed:
                claimed_any = True
            await asyncio.sleep(self._config.roll_delay())
        return done, claimed_any, None

    def apply_settings_fields(self, fields: dict[str, Any]) -> None:
        """Update claim timer from parsed $settings (``settimer``)."""
        timer = fields.get("settimer")
        if timer is not None:
            self._state.claim_expire_sec = int(timer)

    def _apply_tu_fields(self, fields: dict[str, Any]) -> None:
        if "rolls_left" in fields and fields["rolls_left"] is not None:
            merge_tu_hourly_rolls(self._state, int(fields["rolls_left"]))
        # Always refresh the $us bonus (None when $tu no longer reports one).
        us_bonus = fields.get("rolls_us_bonus")
        self._state.rolls_us_bonus = int(us_bonus) if us_bonus is not None else None
        if "claim_available" in fields:
            self._state.claim_available = fields["claim_available"]
            if fields["claim_available"]:
                self._state.set_claim_cooldown(None)
        if "claim_cooldown_minutes" in fields:
            self._state.set_claim_cooldown(fields["claim_cooldown_minutes"])
        sync_reaction_power_fields(self._state, fields)
        sync_dk_fields_from_tu(self._state, fields)
        from macro.rt_manager import sync_rt_fields_from_tu

        sync_rt_fields_from_tu(self._state, fields)
        if "rolls_reset_minutes" in fields:
            self._state.set_rolls_reset(int(fields["rolls_reset_minutes"]))
        if "next_claim_reset_minutes" in fields and fields["next_claim_reset_minutes"] is not None:
            self._state.set_claim_reset(int(fields["next_claim_reset_minutes"]))
