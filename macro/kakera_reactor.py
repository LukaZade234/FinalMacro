"""Click kakera buttons on a roll based on KakeraReactionRules.

Consumes :func:`macro.rule_eval.passes_kakera_reaction` for the decision and
performs the actual button clicks via :class:`macro.actions.DiscordActions`.
Tracks reaction power locally after each confirmed Mudae response.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from macro.actions import DiscordActions, is_kakera_outcome_message, normalize_kakera_outcome
from macro.chaos_followup import (
    apply_chaos_hourly_rolls,
    discounted_reaction_cost,
    is_chaos_followup_embed,
)
from macro.config import KakeraReactionRules, MacroConfig
from macro.dk_manager import apply_dk_response, has_dk_available
from macro.perk8_daily import perk8_budget_applies
from macro.perk8_power import dk_allowed_for_state
from macro.post_roll import PostRollHandler, RollRecord
from macro.reaction_power import (
    can_afford_reaction,
    display_reaction_power,
    kakera_base_cost_from_state,
    reaction_power_cost,
    spend_reaction_power,
    sync_reaction_power_from_denial,
)
from macro.rule_eval import (
    ButtonChoice,
    _has_chaos_key,
    counts_toward_perk8_budget,
    passes_kakera_reaction,
    perk8_click_budget,
    perk8_is_saving,
    perk8_mode_from_state,
    slice_kakera_budget_candidates,
)
from macro.state import AccountState
from mudae.buttons import is_claim_button, is_kakera_button
from mudae.chaos_capture import arm_idle_watch, begin_window, bind_notify, close_open_window
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

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
_CHAOS_FOLLOWUP_WAIT_SEC = 6.0


@dataclass(frozen=True)
class _KakeraClickResult:
    confirmed: bool
    wait_timed_out: bool


@dataclass
class KakeraReactor:
    actions: DiscordActions
    config: MacroConfig
    state: AccountState
    log: Callable[[str], None]
    on_perk8_exhausted: Callable[[], None] | None = None
    on_click_progress: Callable[[], None] | None = None
    on_click_timeout: Callable[[], Awaitable[None] | None] | None = None
    on_state: Callable[[], None] | None = None
    on_keys: Callable[[], None] | None = None
    debug_log: Callable[[str], None] | None = None

    def __post_init__(self) -> None:
        self._last_outcome_snapshot: MudaeMessageSnapshot | None = None
        self._last_kakera_outcome: ParseResult | None = None
        self._react_character: str = ""

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
        self._react_character = character
        decision = await self._resolve_decision(
            fields, rules, message_id, character, roll_index
        )
        if not decision.should_click:
            if rules.enabled:
                self._debug(f"kakera skip {character}: {decision.reason}")
            return 0

        candidates = decision.buttons
        mode = perk8_mode_from_state(self.state)
        budget = perk8_click_budget(self.state, rules)
        has_chaos = _has_chaos_key(fields)
        has_perk_8 = bool(fields.get("perk_8"))
        if (
            rules.perk_8_budget_mode
            and perk8_budget_applies(mode)
            and not perk8_is_saving(self.state, rules)
            and self.on_perk8_exhausted
        ):
            self.on_perk8_exhausted()
        if perk8_is_saving(self.state, rules):
            remaining = self.state.remaining_kakera_budget(budget)
            candidates = slice_kakera_budget_candidates(
                candidates,
                remaining=remaining,
                perk8=has_perk_8,
                rules=rules,
            )
            if not candidates:
                self._debug(
                    f"kakera skip {character}: daily budget "
                    f"{self.state.kakera_clicks_today}/{budget} reached"
                )
                return 0

        clicks = 0
        budget_clicks = 0
        wait_timed_out = False
        base_cost = kakera_base_cost_from_state(self.state)
        for choice in candidates:
            if not choice.custom_id:
                continue
            cost = reaction_power_cost(
                kakera_emoji=choice.emoji or "",
                has_chaos_key=has_chaos,
                has_perk_8=has_perk_8,
                base_cost=base_cost,
            )
            result = await self._click_with_power_recovery(
                message_id=message_id,
                choice=choice,
                cost=cost,
                character=character,
                roll_index=roll_index,
                rules=rules,
                perk8=has_perk_8,
            )
            # Any uncertain click can desync the count, not just a perk-8 one:
            # a click on an ordinary character still spends the daily 40 unless
            # it is a bypass colour, and the click may have landed even though
            # the wait failed. `sphere_reactor` already resyncs on every
            # timeout; this used to require `has_perk_8` and so left a normal
            # roll's uncertain click unreconciled until the next day.
            if result.wait_timed_out:
                wait_timed_out = True
            if result.confirmed:
                clicks += 1
                if counts_toward_perk8_budget(
                    emoji=choice.emoji or "",
                    perk8=has_perk_8,
                    rules=rules,
                ):
                    budget_clicks += 1
                if len(candidates) > 1 and clicks < len(candidates):
                    await asyncio.sleep(_KAKERA_BETWEEN_CLICKS_SEC)

        if clicks:
            if budget_clicks:
                self.state.record_kakera_clicks(budget_clicks)
            if self.on_click_progress and budget_clicks:
                self.on_click_progress()
            budget_note = ""
            if rules.perk_8_budget_mode and perk8_is_saving(self.state, rules):
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
            self._debug(
                f"kakera click ×{clicks} {character}: {decision.reason}"
                f"{budget_note}{power_note}{dk_note}"
            )
            if (
                rules.perk_8_budget_mode
                and budget_clicks
                and self.state.kakera_clicks_today >= budget
                and self.on_perk8_exhausted
            ):
                self.on_perk8_exhausted()
        elif decision.should_click:
            self.log(f"kakera click failed {character}")
        if wait_timed_out:
            await self._request_click_resync()
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
            and dk_allowed_for_state(
                self.state, rules, perk8=bool(fields.get("perk_8"))
            )
        ):
            if await self._try_use_dk(
                character,
                roll_index=roll_index,
                reason="insufficient power before click",
                perk8=bool(fields.get("perk_8")),
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
        perk8: bool = False,
        handle_spawns: bool = True,
    ) -> _KakeraClickResult:
        chaos = (choice.emoji or "") == _CHAOS_EMOJI
        if chaos:
            bind_notify(self.log, asyncio.get_running_loop())
            begin_window(clicked_message_id=message_id, character_name=character)
        confirmed = False
        wait_timed_out = False
        try:
            dk_attempts = 0
            while True:
                if not can_afford_reaction(self.state, cost):
                    if (
                        rules.auto_use_dk
                        and has_dk_available(self.state)
                        and dk_attempts < _MAX_DK_ATTEMPTS_PER_CLICK
                        and dk_allowed_for_state(self.state, rules, perk8=perk8)
                    ):
                        dk_attempts += 1
                        if await self._try_use_dk(
                            character,
                            attempt=dk_attempts,
                            roll_index=roll_index,
                            reason="insufficient tracked power",
                            perk8=perk8,
                        ):
                            self.log(
                                f"kakera: retrying {character} after $dk "
                                f"(need {cost:g}% · have "
                                f"{display_reaction_power(self.state.power_percent)}%)"
                            )
                            continue
                    self._debug(
                        f"kakera skip {character}: insufficient power "
                        f"({display_reaction_power(self.state.power_percent)}% "
                        f"need {cost:g}%)"
                    )
                    return _KakeraClickResult(False, wait_timed_out)
                for attempt in range(1, _MAX_KAKERA_CLICK_ATTEMPTS + 1):
                    ok = await self.actions.click_button(message_id, choice.custom_id)
                    if not ok:
                        self._debug(
                            f"kakera: button click failed {character} "
                            f"(msg {message_id})"
                        )
                        return _KakeraClickResult(False, wait_timed_out)
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
                    wait_timed_out = True
                    self._drain_stale_kakera_outcomes()
                    if attempt < _MAX_KAKERA_CLICK_ATTEMPTS:
                        self.log(
                            f"kakera: retrying click on {character} "
                            f"(attempt {attempt + 1}/{_MAX_KAKERA_CLICK_ATTEMPTS})"
                        )
                else:
                    self._log_kakera_timeout(character)
                    return _KakeraClickResult(False, True)
                if outcome.kind == MessageKind.KAKERA_REACT_DENIED:
                    cooldown = int(outcome.fields.get("kakera_cooldown_minutes") or 0)
                    sync_reaction_power_from_denial(
                        self.state,
                        cooldown_minutes=cooldown,
                        cost=cost,
                    )
                    self._notify_state()
                    self._debug(
                        f"kakera denied {character}: Mudae cooldown {cooldown}m "
                        f"(tracked power ≈ "
                        f"{display_reaction_power(self.state.power_percent)}%)"
                    )
                    if (
                        rules.auto_use_dk
                        and has_dk_available(self.state)
                        and dk_attempts < _MAX_DK_ATTEMPTS_PER_CLICK
                        and dk_allowed_for_state(self.state, rules, perk8=perk8)
                    ):
                        dk_attempts += 1
                        if await self._try_use_dk(
                            character,
                            attempt=dk_attempts,
                            roll_index=roll_index,
                            reason=f"denied · wait {cooldown}m",
                            perk8=perk8,
                        ):
                            self.log(
                                f"kakera: retrying {character} after $dk refill "
                                f"(need {cost:g}%)"
                            )
                            continue
                    return _KakeraClickResult(False, wait_timed_out)
                paid = float(cost)
                if chaos and outcome.kind == MessageKind.KAKERA_CLAIM:
                    paid = discounted_reaction_cost(
                        cost, outcome.fields.get("chaos_power_discount_pct")
                    )
                    if paid + 1e-9 < float(cost):
                        pct = outcome.fields.get("chaos_power_discount_pct")
                        self.log(
                            f"chaos: {pct:g}% power discount · "
                            f"spent {paid:g}% (was {cost:g}%)"
                        )
                if not spend_reaction_power(self.state, paid):
                    self.log(
                        f"kakera claim {character} but power tracker rejected "
                        f"{paid:g}% spend"
                    )
                    return _KakeraClickResult(False, wait_timed_out)
                self._notify_state()
                confirmed = True
                if outcome.kind == MessageKind.KAKERA_CLAIM:
                    self._apply_chaos_claim_rewards(outcome)
                if chaos:
                    arm_idle_watch()
                    self._debug(
                        f"chaos capture: watching follow-ups after {character}"
                    )
                    if handle_spawns:
                        await self._handle_chaos_spawns(
                            clicked_message_id=message_id,
                            outcome=outcome,
                        )
                return _KakeraClickResult(True, wait_timed_out)
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
        perk8: bool = False,
    ) -> bool:
        rules = self.config.kakera_reaction
        if not rules.auto_use_dk or not has_dk_available(self.state):
            if rules.auto_use_dk:
                self.log(f"$dk: none available — cannot refill for {character}")
            return False
        if not dk_allowed_for_state(self.state, rules, perk8=perk8):
            self._debug(
                f"$dk: held for perk-8 reserve — not using for {character}"
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

    async def _request_click_resync(self) -> None:
        """Ask Mudae for the true perk-8 count when ours may be wrong.

        The local counter is a stand-in for ``$ohu8``; whenever a click's
        outcome is uncertain, or was made outside the budget accounting, the
        only way back to the truth is to ask.
        """
        cb = self.on_click_timeout
        if cb is None:
            return
        result = cb()
        if asyncio.iscoroutine(result):
            await result

    async def _wait_for_kakera_outcome(self, *, timeout: float) -> ParseResult | None:
        collect = getattr(self.actions, "collect_queued", None)
        if collect is not None:
            queued = collect(is_kakera_outcome_message)
            if queued:
                snapshot, parsed = queued[0]
                return self._remember_kakera_outcome(snapshot, parsed)
        result = await self.actions.wait_for(
            is_kakera_outcome_message,
            timeout=timeout,
        )
        if result is not None:
            return self._remember_kakera_outcome(result[0], result[1])
        if collect is not None:
            queued = collect(is_kakera_outcome_message)
            if queued:
                snapshot, parsed = queued[0]
                return self._remember_kakera_outcome(snapshot, parsed)
        return None

    def _remember_kakera_outcome(
        self,
        snapshot: MudaeMessageSnapshot,
        parsed: ParseResult,
    ) -> ParseResult:
        normalized = self._normalize_kakera_outcome(snapshot, parsed)
        self._last_outcome_snapshot = snapshot
        self._last_kakera_outcome = normalized
        return normalized

    def _apply_chaos_claim_rewards(self, parsed: ParseResult) -> None:
        fields = parsed.fields or {}
        extra = int(fields.get("chaos_rolls_this_hour") or 0)
        if extra:
            total = apply_chaos_hourly_rolls(self.state, extra)
            self.log(f"chaos: +{extra} rolls this hour · {total} spendable")
            self._notify_state()
        minigames = fields.get("chaos_minigames") or {}
        if minigames:
            bits = ", ".join(
                f"+{count} ${name}" for name, count in sorted(minigames.items())
            )
            self.log(f"chaos: stored minigame uses ({bits}) — not played")
        loots = int(fields.get("chaos_kakeraloots") or 0)
        if loots:
            extra_bits: list[str] = []
            stacked = fields.get("chaos_kakeraloot_stacked")
            if stacked is not None:
                extra_bits.append(f"+{stacked:g} stacked")
            ka = fields.get("chaos_kakeraloot_kakera")
            if ka is not None:
                extra_bits.append(f"+{ka} kakera")
            protect = fields.get("chaos_wish_protect_levels")
            if protect is not None:
                extra_bits.append(f"+{protect} wish protect")
            note = f" ({', '.join(extra_bits)})" if extra_bits else ""
            self.log(f"chaos: {loots} kakeraloot(s){note} — not played")
        if int(fields.get("shop_perk5_ot") or 0):
            self.log("perk 5: +1 $ot stored")
        omega = int(fields.get("chaos_omega_keys") or 0)
        if omega:
            self._record_chaos_omega(omega)
        unparsed = fields.get("chaos_unparsed") or []
        if unparsed:
            self._debug(f"chaos unparsed: {unparsed[0]}")

    def _record_chaos_omega(self, amount: int) -> None:
        from mudae.key_log import record_chaos_omega

        snapshot = self._last_outcome_snapshot
        if snapshot is None:
            return
        created = record_chaos_omega(
            snapshot,
            amount=amount,
            character_name=self._react_character or "Chaos kakera",
        )
        if created:
            self.log(f"chaos: +{amount} omega key(s) logged")
            if self.on_keys:
                self.on_keys()

    async def _handle_chaos_spawns(
        self,
        *,
        clicked_message_id: int,
        outcome: ParseResult,
    ) -> None:
        fields = outcome.fields or {}
        want_free = int(fields.get("chaos_free_kakera") or 0) > 0
        want_wish = bool(fields.get("chaos_wish_spawn"))
        seen: list[tuple[MudaeMessageSnapshot, ParseResult]] = []
        collect = getattr(self.actions, "collect_queued", None)

        def _match(snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> bool:
            return is_chaos_followup_embed(snapshot, parsed, clicked_message_id)

        if collect is not None:
            seen.extend(collect(_match))
        if (want_free or want_wish) and not seen:
            deadline = time.monotonic() + _CHAOS_FOLLOWUP_WAIT_SEC
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                result = await self.actions.wait_for(
                    _match,
                    timeout=min(0.4, remaining),
                )
                if result is not None:
                    seen.append(result)
                    break
            if collect is not None:
                seen.extend(collect(_match))
        handled: set[int] = set()
        for snapshot, parsed in seen:
            if snapshot.message_id in handled:
                continue
            handled.add(snapshot.message_id)
            await self._act_on_chaos_spawn(
                snapshot,
                parsed,
                want_free=want_free,
                want_wish=want_wish,
            )

    async def _act_on_chaos_spawn(
        self,
        snapshot: MudaeMessageSnapshot,
        parsed: ParseResult,
        *,
        want_free: bool,
        want_wish: bool,
    ) -> None:
        fields = dict(parsed.fields)
        buttons = list(snapshot.buttons or fields.get("buttons") or [])
        kakera = [
            btn
            for btn in buttons
            if isinstance(btn, dict)
            and is_kakera_button(btn)
            and not btn.get("disabled")
        ]
        claimable = bool(fields.get("can_claim")) or any(
            is_claim_button(btn) and not btn.get("disabled")
            for btn in buttons
            if isinstance(btn, dict)
        )
        wished = bool(fields.get("wished_by")) or want_wish
        if wished and claimable:
            await self._claim_chaos_wish(snapshot, fields)
            return
        if kakera and (want_free or not claimable):
            name = str(fields.get("character_name") or "?")
            self.log(f"chaos: free kakera on {name} — clicking {len(kakera)}")
            await self._click_free_kakera(
                snapshot.message_id, kakera, character=name
            )

    async def _click_free_kakera(
        self,
        message_id: int,
        buttons: list[dict[str, Any]],
        *,
        character: str,
    ) -> None:
        """Click the free kakera a chaos spawn granted on a character we own.

        These are real kakera reactions, but they never pass through
        ``counts_toward_perk8_budget`` / ``record_kakera_clicks`` — the budget
        accounting lives in :meth:`react`, and this is a separate path. Rather
        than guess whether Mudae charges them against the daily 40, resync from
        ``$ohu8`` afterwards and take its answer.
        """
        clicked = False
        for index, btn in enumerate(buttons):
            custom_id = str(btn.get("custom_id") or "")
            if not custom_id:
                continue
            raw_emoji = btn.get("emoji") or ""
            if isinstance(raw_emoji, dict):
                emoji = str(raw_emoji.get("name") or "")
            else:
                emoji = str(raw_emoji)
            choice = ButtonChoice(
                custom_id=custom_id,
                message_id=message_id,
                kind="kakera",
                emoji=emoji,
            )
            result = await self._click_with_power_recovery(
                message_id=message_id,
                choice=choice,
                cost=0.0,
                character=character,
                roll_index=0,
                rules=self.config.kakera_reaction,
                perk8=False,
                handle_spawns=False,
            )
            clicked = clicked or result.confirmed or result.wait_timed_out
            if index + 1 < len(buttons):
                await asyncio.sleep(_KAKERA_BETWEEN_CLICKS_SEC)
        if clicked:
            await self._request_click_resync()

    async def _claim_chaos_wish(
        self,
        snapshot: MudaeMessageSnapshot,
        fields: dict[str, Any],
    ) -> None:
        rules = self.config.character_claim
        if not rules.claim_on_wish_ping:
            self.log("chaos wish spawn — wish claim off, skipped")
            return
        claim_fields = dict(fields)
        if not claim_fields.get("wished_by") and self.state.own_user_ids:
            claim_fields["wished_by"] = list(self.state.own_user_ids)
        if not claim_fields.get("can_claim"):
            buttons = claim_fields.get("buttons") or snapshot.buttons or []
            claim_fields["can_claim"] = any(
                is_claim_button(btn) and not btn.get("disabled")
                for btn in buttons
                if isinstance(btn, dict)
            )
        record = RollRecord(
            message_id=snapshot.message_id,
            character_name=claim_fields.get("character_name"),
            fields=claim_fields,
        )
        handler = PostRollHandler(
            self.actions, self.config, self.state, log=self.log
        )
        await handler.claim_record(
            record,
            reason="chaos wish spawn",
            allow_rt=True,
        )
        self._notify_state()

    def _notify_state(self) -> None:
        if self.on_state:
            self.on_state()
