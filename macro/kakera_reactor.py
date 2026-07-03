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

from macro.actions import DiscordActions
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
    perk8_click_budget,
    perk8_mode_from_state,
)
from macro.state import AccountState, RuleTraceEntry
from mudae.types import MessageKind

# Pauses around ``$dk`` so Mudae finishes processing the prior kakera denial.
_DK_PAUSE_BEFORE_SEC = 1.0
_DK_PAUSE_AFTER_SEC = 1.0
_DK_RETRY_PAUSE_BEFORE_SEC = 3.0
_DK_RETRY_PAUSE_AFTER_SEC = 2.0
_DK_RESPONSE_TIMEOUT_SEC = 12.0
_MAX_DK_ATTEMPTS_PER_CLICK = 2


@dataclass
class KakeraReactor:
    actions: DiscordActions
    config: MacroConfig
    state: AccountState
    log: Callable[[str], None]
    on_perk8_exhausted: Callable[[], None] | None = None
    on_click_progress: Callable[[], None] | None = None
    on_state: Callable[[], None] | None = None

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
        character = fields.get("character_name") or "?"
        decision = await self._resolve_decision(
            fields, rules, message_id, character, roll_index
        )
        if not decision.should_click:
            if rules.enabled:
                self._trace("skip", character, roll_index, decision.reason)
                self.log(f"kakera skip {character}: {decision.reason}")
            return 0

        candidates = decision.buttons
        mode = perk8_mode_from_state(self.state)
        budget = perk8_click_budget(self.state, rules)
        if rules.perk_8_budget_mode and perk8_budget_applies(mode):
            remaining = self.state.remaining_kakera_budget(budget)
            if remaining <= 0:
                self._trace(
                    "skip",
                    character,
                    roll_index,
                    f"budget {self.state.kakera_clicks_today}/{budget}",
                )
                self.log(
                    f"kakera skip {character}: daily budget "
                    f"{self.state.kakera_clicks_today}/{budget} reached"
                )
                return 0
            candidates = candidates[:remaining]

        has_chaos = _has_chaos_key(fields)
        has_perk_8 = bool(fields.get("perk_8"))
        clicks = 0
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

        if clicks:
            self.state.record_kakera_clicks(clicks)
            if self.on_click_progress:
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
            self._trace(
                "click",
                character,
                roll_index,
                decision.reason
                + (
                    f" · budget {self.state.kakera_clicks_today}/{budget}"
                    if rules.perk_8_budget_mode and perk8_budget_applies(mode)
                    else ""
                )
                + (
                    f" · power {display_reaction_power(self.state.power_percent)}%"
                    if self.state.power_percent is not None
                    else ""
                ),
            )
            if (
                rules.perk_8_budget_mode
                and perk8_budget_applies(mode)
                and self.state.kakera_clicks_today >= budget
                and self.on_perk8_exhausted
            ):
                self.on_perk8_exhausted()
        elif decision.should_click:
            self.log(f"kakera click failed {character}")
            self._trace("skip", character, roll_index, "click failed")
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
                self._trace(
                    "skip",
                    character,
                    roll_index,
                    f"insufficient power need {cost:g}%",
                )
                return False
            ok = await self.actions.click_button(message_id, choice.custom_id)
            if not ok:
                return False
            outcome = await self.actions.wait_for_kakera_outcome(timeout=8.0)
            if outcome is None:
                self.log(f"kakera click timeout {character}")
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
                self._trace(
                    "skip",
                    character,
                    roll_index,
                    f"denied · wait {cooldown}m",
                )
                return False
            if not spend_reaction_power(self.state, cost):
                self.log(
                    f"kakera claim {character} but power tracker rejected "
                    f"{cost:g}% spend"
                )
                return False
            self._notify_state()
            return True

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
                self._trace_dk(
                    "skip",
                    character,
                    roll_index,
                    "no $dk stock",
                )
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
        self._trace_dk(
            "wait",
            character,
            roll_index,
            f"pause {pause_before:g}s before attempt {attempt} ({reason})",
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
            self._trace_dk(
                "fail",
                character,
                roll_index,
                f"timeout after attempt {attempt}",
            )
            return False

        fields = dict(parsed.fields)
        if not (fields.get("dk_used") or fields.get("amount") is not None):
            self.log(
                f"$dk: response did not look like a successful claim "
                f"(attempt {attempt}) — kakera retry cancelled"
            )
            self._trace_dk(
                "fail",
                character,
                roll_index,
                f"unexpected response attempt {attempt}",
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
        self._trace_dk(
            "use",
            character,
            roll_index,
            f"attempt {attempt}: {power_before}%→{power_after}% · "
            f"{stock_before}→{stock_after} $dk ({reason})",
        )

        self.log(f"$dk: waiting {pause_after:g}s for Mudae to settle before kakera retry")
        await asyncio.sleep(pause_after)
        self._notify_state()
        return True

    def _trace_dk(
        self,
        decision: str,
        character: str,
        roll_index: int,
        reason: str,
    ) -> None:
        self.state.append_rule_trace(
            RuleTraceEntry(
                block="dk",
                roll_index=roll_index,
                character=character,
                decision=decision,
                reason=reason,
            )
        )

    def _notify_state(self) -> None:
        if self.on_state:
            self.on_state()

    def _trace(self, decision: str, character: str, roll_index: int, reason: str) -> None:
        self.state.append_rule_trace(
            RuleTraceEntry(
                block="kakera",
                roll_index=roll_index,
                character=character,
                decision=decision,
                reason=reason,
            )
        )
