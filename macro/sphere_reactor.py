"""Click sphere buttons on a roll based on SphereReactionRules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions
from macro.config import MacroConfig
from macro.rule_eval import passes_sphere_reaction
from macro.state import AccountState, RuleTraceEntry


@dataclass
class SphereReactor:
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
        rules = self.config.sphere_reaction
        decision = passes_sphere_reaction(
            fields,
            rules,
            self.state,
            message_id=message_id,
        )
        character = fields.get("character_name") or "?"
        if not decision.should_click:
            if rules.enabled:
                self._trace("skip", character, roll_index, decision.reason)
                self.log(f"sphere skip {character}: {decision.reason}")
            return 0

        clicks = 0
        for choice in decision.buttons:
            if not choice.custom_id:
                continue
            ok = await self.actions.click_button(message_id, choice.custom_id)
            if ok:
                clicks += 1

        if clicks:
            self.log(f"sphere click ×{clicks} {character}: {decision.reason}")
            self._trace("click", character, roll_index, decision.reason)
        else:
            self.log(f"sphere click failed {character}")
            self._trace("skip", character, roll_index, "click failed")
        return clicks

    def _trace(self, decision: str, character: str, roll_index: int, reason: str) -> None:
        self.state.append_rule_trace(
            RuleTraceEntry(
                block="sphere",
                roll_index=roll_index,
                character=character,
                decision=decision,
                reason=reason,
            )
        )
