"""Click kakera buttons on a roll based on KakeraReactionRules.

Consumes :func:`macro.rule_eval.passes_kakera_reaction` for the decision and
performs the actual button clicks via :class:`macro.actions.DiscordActions`.
Tracks reaction power locally after each confirmed Mudae response.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions, is_kakera_outcome_message, normalize_kakera_outcome
from macro.config import KakeraReactionRules, MacroConfig
from macro.dk_manager import apply_dk_response, has_dk_available
from macro.perk8_daily import perk8_budget_applies
from macro.reaction_power import (
    can_afford_reaction,
    display_reaction_power,
    reaction_power_cost,
    spend_reaction_power,
    sync_reaction_power_from_denial,
)
from macro.rule_eval import (
    _has_chaos_key,
    passes_kakera_reaction,
    perk8_budget_bypass_types,
    perk8_click_budget,
    perk8_mode_from_state,
)
from macro.state import AccountState
from mudae.chaos_capture import arm_idle_watch, begin_window, bind_notify, close_open_window
from mudae.types import MessageKind, ParseResult

_CHAOS_EMOJI = "kakeraC"

# Pauses around ``$dk`` so Mudae finishes processing the prior kakera denial.
_DK_PAUSE_BEFORE_SEC = 1.0
_DK_PAUSE_AFTER_SEC = 1.0
_DK_RETRY_PAUSE_BEFORE_SEC = 3.0
_DK_RETRY_PAUSE_AFTER_SEC = 2.0
_DK_RESPONSE_TIMEOUT_SEC = 12.0
_MAX_DK_ATTEMPTS_PER_CLICK = 2
_KAKERA_OUTCOME_TIMEOUT_SEC = 8.0
_KAKERA_OUTCOME_RETRY_TIMEOUT_SEC = 6.0
_KAKERA_CLICK_SETTLE_SEC = 0.35
_KAKERA_BETWEEN_CLICKS_SEC = 0.5
_MAX_KAKERA_CLICK_ATTEMPTS = 2


@dataclass
class KakeraReactor:
    actions: DiscordActions
    config: MacroConfig
    state: AccountState
    log: Callable[[str], None]
    on_perk8_exhausted: Callable[[], None] | None = None
    on_click_progress: Callable[[], None] | None = None
    on_state: Callable[[], None] | None = None
    debug_log: Callable[[str], None] | None = None

    async def react(
        self,
        *,
        message_id: int,
        fields: dict[str, Any],
        roll_index: int = 0,
        rules: KakeraReactionRules | None = None,
    ) -> int:
        """React to one parsed roll. Returns number of buttons clicked."""
        rules = rules if rules is not None else self.config.kakera_reaction
        self._drain_stale_kakera_outcomes()
        character = fields.get("character_name") or "?"
        decision = await self._resolve_decision(
            fields, rules, message_id, character, roll_index
        )
        if not decision.should_click:
            if rules.enabled:
                self.log(f"kakera skip {character}: {decision.reason}")
            return 0

        candidates = decision.buttons
        mode = perk8_mode_from_state(self.state)
        budget = perk8_click_budget(self.state, rules)
        bypass = perk8_budget_bypass_types(rules)
        if rules.perk_8_budget_mode and perk8_budget_applies(mode):
            remaining = self.state.remaining_kakera_budget(budget)
            bypass_candidates = [
                c for c in candidates if (c.emoji or "") in bypass
            ]
            paid_candidates = [
                c for c in candidates if (c.emoji or "") not in bypass
            ]
            if remaining <= 0 and not paid_candidates:
                candidates = bypass_candidates
            elif remaining <= 0:
                self.log(
                    f"kakera skip {character}: daily budget "
                    f"{self.state.kakera_clicks_today}/{budget} reached"
                )
                return 0
            else:
                candidates = bypass_candidates + paid_candidates[:remaining]

            if not candidates:
                self.log(
                    f"kakera skip {character}: daily budget "
                    f"{self.state.kakera_clicks_today}/{budget} reached"
                )
                return 0

        has_chaos = _has_chaos_key(fields)
        has_perk_8 = bool(fields.get("perk_8"))
        clicks = 0
        budget_clicks = 0
        for choice in candidates:
            if not choice.custom_id:
                continue
            cost = reaction_power_cost(
                kakera_emoji=choice.emoji or "",
                has_chaos_key=has_chaos,
                has_perk_8=has_perk_8,
            )
            clicked = await self._click_with_power_recovery(
                message_id=message_id,
                choice=choice,
                cost=cost,
                character=character,
                roll_index=roll_index,
                rules=rules,
            )
            if clicked:
                clicks += 1
                if (choice.emoji or "") not in bypass:
                    budget_clicks += 1
                if len(candidates) > 1 and clicks < len(candidates):
                    await asyncio.sleep(_KAKERA_BETWEEN_CLICKS_SEC)

        if clicks:
            if budget_clicks:
                self.state.record_kakera_clicks(budget_clicks)
            if self.on_click_progress and budget_clicks:
                self.on_click_progress()
            budget_note = ""
            if rules.perk_8_budget_mode and perk8_budget_applies(mode):
                budget_note = (
                    f" · budget {self.state.kakera_clicks_today}/{budget}"
                )
            power_note = ""
            if self.state.power_percent is not None:
                power_note = (
                    f" · power {display_reaction_power(self.state.power_percent)}%"
                )
            dk_note = ""
            if self.state.dk_stock is not None:
                dk_note = f" · {self.state.dk_stock} dk"
            self.log(
                f"kakera click ×{clicks} {character}: {decision.reason}"
                f"{budget_note}{power_note}{dk_note}"
            )
            if (
                rules.perk_8_budget_mode
                and perk8_budget_applies(mode)
                and budget_clicks
                and self.state.kakera_clicks_today >= budget
                and self.on_perk8_exhausted
            ):
                self.on_perk8_exhausted()
        elif decision.should_click:
            self.log(f"kakera click failed {character}")
        return clicks

    async def _resolve_decision(
        self,
        fields: dict[str, Any],
        rules: Any,
        message_id: int,
        character: str,
        roll_index: int = 0,
    ):
        decision = passes_kakera_reaction(
            fields,
            rules,
            self.state,
            message_id=message_id,
        )
        if (
            not decision.should_click
            and rules.auto_use_dk
            and "insufficient reaction power" in decision.reason
            and has_dk_available(self.state)
        ):
            if await self._try_use_dk(
                character,
                roll_index=roll_index,
                reason="insufficient power before click",
            ):
                decision = passes_kakera_reaction(
                    fields,
                    rules,
                    self.state,
                    message_id=message_id,
                )
        return decision

    async def _click_with_power_recovery(
        self,
        *,
        message_id: int,
        choice: Any,
        cost: float,
        character: str,
        roll_index: int,
        rules: KakeraReactionRules,
    ) -> bool:
        chaos = (choice.emoji or "") == _CHAOS_EMOJI
        if chaos:
            bind_notify(self.log, asyncio.get_running_loop())
            begin_window(clicked_message_id=message_id, character_name=character)
        confirmed = False
        try:
            dk_attempts = 0
            while True:
                if not can_afford_reaction(self.state, cost):
                    if (
                        rules.auto_use_dk
                        and has_dk_available(self.state)
                        and dk_attempts < _MAX_DK_ATTEMPTS_PER_CLICK
                    ):
                        dk_attempts += 1
                        if await self._try_use_dk(
                            character,
                            attempt=dk_attempts,
                            roll_index=roll_index,
                            reason="insufficient tracked power",
                        ):
                            self.log(
                                f"kakera: retrying {character} after $dk "
                                f"(need {cost:g}% · have "
                                f"{display_reaction_power(self.state.power_percent)}%)"
                            )
                            continue
                    self.log(
                        f"kakera skip {character}: insufficient power "
                        f"({display_reaction_power(self.state.power_percent)}% "
                        f"need {cost:g}%)"
                    )
                    return False
                for attempt in range(1, _MAX_KAKERA_CLICK_ATTEMPTS + 1):
                    ok = await self.actions.click_button(message_id, choice.custom_id)
                    if not ok:
                        self._debug(
                            f"kakera: button click failed {character} "
                            f"(msg {message_id})"
                        )
                        return False
                    await asyncio.sleep(_KAKERA_CLICK_SETTLE_SEC)
                    wait_timeout = (
                        _KAKERA_OUTCOME_TIMEOUT_SEC
                        if attempt == 1
                        else _KAKERA_OUTCOME_RETRY_TIMEOUT_SEC
                    )
                    qsize = getattr(self.actions, "queue_size", lambda: 0)()
                    self._debug(
                        f"kakera: wait outcome {character} "
                        f"attempt {attempt}/{_MAX_KAKERA_CLICK_ATTEMPTS} "
                        f"timeout={wait_timeout:g}s queue={qsize}"
                    )
                    outcome = await self._wait_for_kakera_outcome(timeout=wait_timeout)
                    if outcome is not None:
                        self._debug(
                            f"kakera: outcome {character} · {outcome.kind.value} · "
                            f"{outcome.summary or '?'}"
                        )
                        break
                    self._drain_stale_kakera_outcomes()
                    if attempt < _MAX_KAKERA_CLICK_ATTEMPTS:
                        self.log(
                            f"kakera: retrying click on {character} "
                            f"(attempt {attempt + 1}/{_MAX_KAKERA_CLICK_ATTEMPTS})"
                        )
                else:
                    self._log_kakera_timeout(character)
                    return False
                if outcome.kind == MessageKind.KAKERA_REACT_DENIED:
                    cooldown = int(outcome.fields.get("kakera_cooldown_minutes") or 0)
                    sync_reaction_power_from_denial(
                        self.state,
                        cooldown_minutes=cooldown,
                        cost=cost,
                    )
                    self._notify_state()
                    self.log(
                        f"kakera denied {character}: Mudae cooldown {cooldown}m "
                        f"(tracked power ≈ "
                        f"{display_reaction_power(self.state.power_percent)}%)"
                    )
                    if (
                        rules.auto_use_dk
                        and has_dk_available(self.state)
                        and dk_attempts < _MAX_DK_ATTEMPTS_PER_CLICK
                    ):
                        dk_attempts += 1
                        if await self._try_use_dk(
                            character,
                            attempt=dk_attempts,
                            roll_index=roll_index,
                            reason=f"denied · wait {cooldown}m",
                        ):
                            self.log(
                                f"kakera: retrying {character} after $dk refill "
                                f"(need {cost:g}%)"
                            )
                            continue
                    return False
                if not spend_reaction_power(self.state, cost):
                    self.log(
                        f"kakera claim {character} but power tracker rejected "
                        f"{cost:g}% spend"
                    )
                    return False
                self._notify_state()
                confirmed = True
                if chaos:
                    arm_idle_watch()
                    self._debug(
                        f"chaos capture: watching follow-ups after {character}"
                    )
                return True
        finally:
            if chaos and not confirmed:
                close_open_window("click_unconfirmed")

    async def _try_use_dk(
        self,
        character: str,
        *,
        attempt: int = 1,
        roll_index: int = 0,
        reason: str = "low power",
    ) -> bool:
        rules = self.config.kakera_reaction
        if not rules.auto_use_dk or not has_dk_available(self.state):
            if rules.auto_use_dk:
                self.log(f"$dk: none available — cannot refill for {character}")
            return False

        stock_before = int(self.state.dk_stock or 0)
        pause_before = (
            _DK_PAUSE_BEFORE_SEC if attempt == 1 else _DK_RETRY_PAUSE_BEFORE_SEC
        )
        pause_after = _DK_PAUSE_AFTER_SEC if attempt == 1 else _DK_RETRY_PAUSE_AFTER_SEC
        power_before = display_reaction_power(self.state.power_percent)

        self.log(
            f"$dk: waiting {pause_before:g}s before send "
            f"(attempt {attempt}/{_MAX_DK_ATTEMPTS_PER_CLICK}, "
            f"{stock_before} left, power {power_before}%) — {reason} · {character}"
        )
        await asyncio.sleep(pause_before)

        await self.actions.send_command("dk", prefix=self.config.prefix)
        self.log(f"$dk: sent {self.config.prefix}dk (attempt {attempt})")
        parsed = await self.actions.wait_for_dk_use(timeout=_DK_RESPONSE_TIMEOUT_SEC)
        if parsed is None:
            self.log(
                f"$dk: no Mudae response within {_DK_RESPONSE_TIMEOUT_SEC:g}s "
                f"(attempt {attempt}) — kakera retry cancelled"
            )
            return False

        fields = dict(parsed.fields)
        if not (fields.get("dk_used") or fields.get("amount") is not None):
            self.log(
                f"$dk: response did not look like a successful claim "
                f"(attempt {attempt}) — kakera retry cancelled"
            )
            return False

        apply_dk_response(self.state, fields)
        amount = fields.get("amount")
        stock_after = self.state.dk_stock
        power_after = display_reaction_power(self.state.power_percent)
        parts = [
            f"$dk OK (attempt {attempt}): power {power_before}% → {power_after}%",
        ]
        if amount is not None:
            parts.append(f"+{amount} kakera to collection")
        if stock_after is not None:
            parts.append(f"{stock_after} $dk left")
        next_m = fields.get("dk_next_minutes")
        if next_m is not None:
            parts.append(f"next $dk in {next_m}m")
        self.log(" · ".join(parts))

        self.log(f"$dk: waiting {pause_after:g}s for Mudae to settle before kakera retry")
        await asyncio.sleep(pause_after)
        self._notify_state()
        return True

    def _debug(self, text: str) -> None:
        if self.debug_log:
            self.debug_log(text)

    def _drain_stale_kakera_outcomes(self) -> int:
        """Drop orphaned kakera claim/denial messages left after a timeout."""
        collect = getattr(self.actions, "collect_queued", None)
        if collect is None:
            return 0
        stale = collect(is_kakera_outcome_message)
        if stale:
            self.log(f"kakera: cleared {len(stale)} stale response(s) from queue")
        return len(stale)

    def _normalize_kakera_outcome(
        self,
        snapshot: Any,
        parsed: ParseResult,
    ) -> ParseResult:
        return normalize_kakera_outcome(snapshot, parsed)

    def _log_kakera_timeout(self, character: str) -> None:
        count = getattr(self.actions, "count_queued_outcomes", None)
        if count is None:
            self.log(f"kakera click timeout {character}")
            return
        from mudae.parsers.classify import snapshot_is_kakera_claim

        qsize, missed = count(
            lambda snapshot, parsed: (
                is_kakera_outcome_message(snapshot, parsed)
                or snapshot_is_kakera_claim(snapshot)
            )
        )
        if missed:
            self.log(
                f"kakera click timeout {character}: "
                f"{missed} (+$k) response(s) were in queue (size {qsize}) "
                "but not matched — report this"
            )
        elif qsize:
            self.log(
                f"kakera click timeout {character}: "
                f"no (+$k) line in queue (size {qsize})"
            )
        else:
            self.log(f"kakera click timeout {character}: no Mudae response seen")

    async def _wait_for_kakera_outcome(self, *, timeout: float) -> ParseResult | None:
        collect = getattr(self.actions, "collect_queued", None)
        if collect is not None:
            queued = collect(is_kakera_outcome_message)
            if queued:
                snapshot, parsed = queued[0]
                return self._normalize_kakera_outcome(snapshot, parsed)
        result = await self.actions.wait_for(
            is_kakera_outcome_message,
            timeout=timeout,
        )
        if result is not None:
            return self._normalize_kakera_outcome(result[0], result[1])
        if collect is not None:
            queued = collect(is_kakera_outcome_message)
            if queued:
                snapshot, parsed = queued[0]
                return self._normalize_kakera_outcome(snapshot, parsed)
        return None

    def _notify_state(self) -> None:
        if self.on_state:
            self.on_state()
