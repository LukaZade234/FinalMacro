"""Click sphere buttons on a roll based on SphereReactionRules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions
from macro.config import MacroConfig
from mudae.constants import SPHERE_ROLL_FREE_EMOJIS, canonical_sphere_emoji

# Mudae edits the roll message with ``(used/max)`` after a sphere click.
SPHERE_CLICK_TIMEOUT_SEC = 10.0
from macro.perk9_threshold import (
    Perk9ThresholdContext,
    build_perk9_threshold_context,
    estimate_opportunities_left,
    is_spend_down_window,
)
from macro.rule_eval import passes_sphere_reaction
from macro.state import AccountState


@dataclass
class SphereReactor:
    actions: DiscordActions
    config: MacroConfig
    state: AccountState
    log: Callable[[str], None]
    debug_log: Callable[[str], None] | None = None
    on_spawn: Callable[[int], None] | None = None
    on_roll: Callable[[bool], None] | None = None
    on_click_progress: Callable[[], None] | None = None
    on_click_timeout: Callable[[], Awaitable[None]] | None = None
    on_exhausted: Callable[[], Awaitable[None]] | None = None

    def _debug(self, text: str) -> None:
        if self.debug_log:
            self.debug_log(text)

    def _threshold_context(self) -> Perk9ThresholdContext | None:
        """Rebuilt per roll — clicks left and spawns left both move every roll."""
        rules = self.config.sphere_reaction
        if not rules.budget_aware:
            return None
        state = self.state
        clicks_left = int(state.perk9_click_max) - int(state.perk9_clicks_today)
        spawns = estimate_opportunities_left(
            state,
            manual_override=rules.expected_daily_opportunities,
            rolls_per_hour=state.rolls_per_hour_net,
        )
        if spawns is None:
            return None
        return build_perk9_threshold_context(
            opportunities_left=spawns,
            clicks_left=clicks_left,
            base_values=rules.sphere_values or None,
            frequency=rules.sphere_frequency or None,
            double_chance_pct=state.sphere_double_chance_pct,
            additional_spheres=state.additional_spheres,
            shop9_bonus_pct=state.perk9_sphere_value_pct,
            spend_down=is_spend_down_window(),
        )

    async def react(
        self,
        *,
        message_id: int,
        fields: dict[str, Any],
        roll_index: int = 0,
        us_roll: bool = False,
    ) -> int:
        """React to one parsed roll. Returns number of buttons clicked."""
        rules = self.config.sphere_reaction
        # Before the spawn is counted, so the stretch boundary falls between the
        # two rolls rather than inside this one. ``$us`` rolls spawn perk-9
        # buttons like any other roll, but a burst of them clears the pool far
        # faster than ordinary rolling, so the learned arrival rate is measured
        # across ordinary rolls only and this roll's spawn belongs to whichever
        # side of the boundary the roll itself does.
        if self.on_roll:
            self.on_roll(us_roll)
        self._count_spawns(fields)
        decision = passes_sphere_reaction(
            fields,
            rules,
            self.state,
            message_id=message_id,
            threshold_ctx=self._threshold_context(),
        )
        character = fields.get("character_name") or "?"
        if not decision.should_click:
            if rules.enabled:
                self._debug(f"sphere skip {character}: {decision.reason}")
            return 0

        clicks = 0
        timed_out = False
        for choice in decision.buttons:
            if not choice.custom_id:
                continue
            ok = await self.actions.click_button(message_id, choice.custom_id)
            if not ok:
                continue
            clicks += 1
            if self._paid_click(choice.emoji):
                # A click can land on Mudae even when the confirmation never
                # arrives, so an unseen reply means the count may be short.
                confirmed = await self.actions.wait_for_sphere_click(
                    timeout=SPHERE_CLICK_TIMEOUT_SEC
                )
                if confirmed is None:
                    timed_out = True

        if clicks:
            self._debug(f"sphere click ×{clicks} {character}: {decision.reason}")
            if self.on_click_progress:
                self.on_click_progress()
        else:
            self.log(f"sphere click failed {character}")

        if timed_out and self.on_click_timeout:
            await self.on_click_timeout()
        elif clicks and self._at_click_cap() and self.on_exhausted:
            await self.on_exhausted()
        return clicks

    def _count_spawns(self, fields: dict[str, Any]) -> None:
        """Every paid sphere button on a roll is one perk-9 spawn."""
        if not self.on_spawn:
            return
        buttons = fields.get("buttons") or []
        spawned = sum(
            1
            for b in buttons
            if isinstance(b, dict)
            and b.get("is_sphere")
            and self._paid_click(_button_emoji(b))
        )
        if spawned:
            self.on_spawn(spawned)

    def _paid_click(self, emoji: str | None) -> bool:
        """Megasphere is a free roll bonus and never spends a perk-9 slot."""
        return canonical_sphere_emoji(emoji) not in SPHERE_ROLL_FREE_EMOJIS

    def _at_click_cap(self) -> bool:
        cap = int(getattr(self.state, "perk9_click_max", 0) or 0)
        return cap > 0 and int(self.state.perk9_clicks_today) >= cap


def _button_emoji(button: dict[str, Any]) -> str:
    emoji = button.get("emoji") or ""
    if isinstance(emoji, dict):
        return str(emoji.get("name") or "")
    return str(emoji or "")
