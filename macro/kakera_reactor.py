"""Click kakera buttons on a roll based on KakeraReactionRules.

Consumes :func:`macro.rule_eval.passes_kakera_reaction` for the decision and
performs the actual button clicks via :class:`macro.actions.DiscordActions`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions
from macro.config import MacroConfig
from macro.rule_eval import passes_kakera_reaction
from macro.state import AccountState, RuleTraceEntry


@dataclass
class KakeraReactor:
    actions: DiscordActions
    config: MacroConfig
    state: AccountState
    log: Callable[[str], None]

    async def react(
        self,
        *,
        message_id: int,
        fields: dict[str, Any],
        roll_index: int = 0,
    ) -> int:
        """React to one parsed roll. Returns number of buttons clicked."""
        rules = self.config.kakera_reaction
        decision = passes_kakera_reaction(
            fields,
            rules,
            self.state,
            message_id=message_id,
        )
        character = fields.get("character_name") or "?"
        if not decision.should_click:
            if rules.enabled:
                self._trace("skip", character, roll_index, decision.reason)
                self.log(f"kakera skip {character}: {decision.reason}")
            return 0

        # Apply perk-8 budget cap on the *count* we actually click.
        candidates = decision.buttons
        remaining = self.state.remaining_kakera_budget(rules.daily_click_budget)
        if rules.perk_8_budget_mode and not fields.get("perk_8"):
            if remaining <= 0:
                self._trace(
                    "skip",
                    character,
                    roll_index,
                    f"budget {self.state.kakera_clicks_today}/{rules.daily_click_budget}",
                )
                self.log(
                    f"kakera skip {character}: daily budget "
                    f"{self.state.kakera_clicks_today}/{rules.daily_click_budget} reached"
                )
                return 0
            candidates = candidates[:remaining]

        clicks = 0
        for choice in candidates:
            if not choice.custom_id:
                continue
            ok = await self.actions.click_button(message_id, choice.custom_id)
            if ok:
                clicks += 1

        if clicks:
            self.state.record_kakera_clicks(clicks)
            budget_note = ""
            if rules.perk_8_budget_mode:
                budget_note = (
                    f" · budget {self.state.kakera_clicks_today}/"
                    f"{rules.daily_click_budget}"
                )
            self.log(f"kakera click ×{clicks} {character}: {decision.reason}{budget_note}")
            self._trace(
                "click",
                character,
                roll_index,
                decision.reason
                + (
                    f" · budget {self.state.kakera_clicks_today}/{rules.daily_click_budget}"
                    if rules.perk_8_budget_mode
                    else ""
                ),
            )
        else:
            self.log(f"kakera click failed {character}")
            self._trace("skip", character, roll_index, "click failed")
        return clicks

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
