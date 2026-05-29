"""Roll-cycle macro engine: $tu, roll until stop, then claim best character."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from macro.actions import DiscordActions
from macro.activity_log import ActivityLog
from macro.claim_window import is_final_roll_session_before_claim_reset
from macro.config import MacroConfig
from macro.kakera_reactor import KakeraReactor
from macro.post_roll import PostRollHandler, RollRecord
from macro.roll_interrupts import RollInterruptContext, evaluate_claim_trigger
from macro.roll_stop import RollStopTracker
from macro.sphere_reactor import SphereReactor
from macro.state import AccountState, MacroPhase, RuleTraceEntry


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
    ) -> None:
        self._actions = actions
        self._config = config
        self._state = state
        self._monitor = monitor
        self._on_state = on_state
        self._on_persist = on_persist
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
        return KakeraReactor(
            actions=self._actions,
            config=self._config,
            state=self._state,
            log=self._log,
        )

    def _make_sphere_reactor(self) -> SphereReactor:
        return SphereReactor(
            actions=self._actions,
            config=self._config,
            state=self._state,
            log=self._log,
        )

    def _sync_claim_window_from_tu(self, fields: dict[str, Any]) -> None:
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
        await asyncio.sleep(2.5)
        parsed = await self._actions.wait_for_tu(timeout=12.0)
        if parsed is None:
            self._log("$tu timeout")
            self._state.phase = MacroPhase.IDLE
            self._notify()
            return False
        self._apply_tu_fields(parsed.fields)
        self._sync_claim_window_from_tu(parsed.fields)
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
        self._log(
            f"$tu OK · {self._state.rolls_left or '?'} rolls · "
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

    async def _run_cycle(self) -> None:
        try:
            self._monitor.macro_active = True
            self._actions.drain_queue()
            self._sync_roll_stop_config()
            self._roll_stop = RollStopTracker(
                threshold=self._roll_stop.threshold,
                tail_count=self._roll_stop.tail_count,
            )

            if not await self.run_tu():
                return

            if self._roll_stop.should_stop_before_roll(self._state.rolls_left):
                self._log("No rolls remaining")
                return

            cmd = self._config.normalized_roll_command()
            session_records: list[RollRecord] = []
            roll_index = 0
            stop_rolling = False
            claimed_via_interrupt = False

            while not self._stop.is_set() and not stop_rolling:
                if self._roll_stop.should_stop_before_roll(self._state.rolls_left):
                    self._log("No rolls remaining")
                    break

                self._state.phase = MacroPhase.ROLLING
                self._notify()

                roll_index += 1
                self._log(f"Roll {roll_index}: ${cmd}")
                await self._actions.send_command(cmd, prefix=self._config.prefix)
                result = await self._actions.wait_for_roll(
                    roll_command=cmd,
                    timeout=25.0,
                )
                if result is None:
                    self._log("Roll embed timeout")
                    break

                snapshot, parsed = result
                fields = dict(parsed.fields)
                name = fields.get("character_name") or "?"
                ka = fields.get("total_kakera")
                ka_text = f" · {ka} ka" if ka is not None else ""
                wished = fields.get("wished_by")
                if wished:
                    ka_text += f" · wish×{len(wished)}"
                self._log(f"→ {name}{ka_text}")

                rl = fields.get("rolls_left")
                if rl is not None:
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
                    self._log(f"{interrupt.reason} — stop rolling, claim now")
                    self._state.append_rule_trace(
                        RuleTraceEntry(
                            block="character",
                            roll_index=roll_index,
                            character=name,
                            decision="claim",
                            reason=interrupt.reason,
                        )
                    )
                    stop_rolling = True
                    self._state.phase = MacroPhase.POST_ROLL
                    self._notify()
                    claimed_via_interrupt = await self._make_post_roll_handler().claim_record(
                        record,
                        reason=interrupt.reason,
                    )
                    break

                await self._make_kakera_reactor().react(
                    message_id=snapshot.message_id,
                    fields=fields,
                    roll_index=roll_index,
                )
                await self._make_sphere_reactor().react(
                    message_id=snapshot.message_id,
                    fields=fields,
                    roll_index=roll_index,
                )

                if rl is not None and int(rl) == self._roll_stop.threshold and not self._roll_stop.saw_warning:
                    self._log(
                        f"Parsed {rl} rolls left — "
                        f"{self._roll_stop.tail_count} more roll(s) then stop"
                    )

                if self._roll_stop.on_roll_parsed(int(rl) if rl is not None else None):
                    self._log("Finished rolls after warning")
                    stop_rolling = True

                await asyncio.sleep(self._config.roll_delay())

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

            self._log("Macro finished")
        except asyncio.CancelledError:
            self._log("Macro stopped")
        finally:
            self._monitor.macro_active = False
            self._state.phase = MacroPhase.IDLE
            self._notify()
            self._task = None

    def apply_settings_fields(self, fields: dict[str, Any]) -> None:
        """Update claim timer from parsed $settings (``settimer``)."""
        timer = fields.get("settimer")
        if timer is not None:
            self._state.claim_expire_sec = int(timer)

    def _apply_tu_fields(self, fields: dict[str, Any]) -> None:
        if "rolls_left" in fields and fields["rolls_left"] is not None:
            self._state.rolls_left = int(fields["rolls_left"])
        if "claim_available" in fields:
            self._state.claim_available = fields["claim_available"]
        if "claim_cooldown_minutes" in fields:
            self._state.claim_cooldown_minutes = fields["claim_cooldown_minutes"]
        if "power_percent" in fields:
            self._state.power_percent = fields["power_percent"]
        if "rolls_reset_minutes" in fields:
            self._state.rolls_reset_minutes = int(fields["rolls_reset_minutes"])
        if "next_claim_reset_minutes" in fields and fields["next_claim_reset_minutes"] is not None:
            self._state.next_claim_reset_minutes = int(fields["next_claim_reset_minutes"])
