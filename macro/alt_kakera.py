"""Alts click kakera on the main's rolls once the main is out of power.

The trigger is the main's own reactor: when it leaves a roll's kakera for
power it calls :meth:`AltKakera.main_power_short` with the buttons it did not
take. "For power" is either

* out of it — before clicking, or part-way through a roll with several
  buttons; or
* holding it back — the perk-8 power save keeping enough for the next
  perk-8 burst ("reserving power for perk-8 burst"), or the perk-8 budget
  saving its clicks for perk-8 rolls. The main chose not to spend; an alt
  pays from its own bar, so the kakera is not lost while the main saves.

Nothing else starts an alt click, so an alt never competes with the main for
a button the main is going to click.

Per button, the channel coordinator picks **one** alt, the first in turn
order that may take it:

* ready — its own ``$bonus`` is applied (``macro/alt_readiness.py``);
* Kakera › "On the main's rolls" is on and the colour is in its list;
* it can afford it at **full** price. The keys on the main's characters are
  not the alt's soulkeys, so the chaos-key (10+ keys) half price never
  applies, and its own ``$bonus`` base cost is used.

If that alt's click fails or Mudae refuses it, the button passes to the next
alt; it is never tried twice by the same one. Never on a perk-8 roll (that
kakera pays the roller) and never a sphere button.

**``$dk`` when it runs short** (Kakera › "$dk when power runs out"): an alt
that cannot afford the button but holds a ``$dk`` still counts as able. It
sends its own ``$dk`` first (spaced from its last command), and clicks once
the bar is full. A refusal the bar did not predict gets the same: one ``$dk``,
one more try. One ``$dk`` at a time per alt; a second button waiting on it
finds the bar already full.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from macro.actions import is_kakera_outcome_message, normalize_kakera_outcome
from macro.dk_manager import apply_dk_response, has_dk_available
from macro.reaction_power import (
    can_afford_reaction,
    kakera_base_cost_from_state,
    reaction_power_cost,
    refresh_reaction_power,
    spend_reaction_power,
    sync_reaction_power_from_denial,
)
from macro.rule_eval import _kakera_emoji
from macro.turns import kakera_key
from mudae.parsers.dk import extract_dk_fields, is_dk_claim
from mudae.types import MessageKind

OUTCOME_TIMEOUT_SEC = 8.0
DK_REPLY_TIMEOUT_SEC = 12.0
# After the $dk reply, before the click: the main's reactor waits the same.
DK_SETTLE_SEC = 1.0


def alt_click_cost(state: Any, emoji: str) -> float:
    """What one button costs an alt on the main's roll: its own base, no
    soulkey half price, no perk 8 (those rolls are skipped)."""
    return reaction_power_cost(
        kakera_emoji=emoji,
        has_chaos_key=False,
        has_perk_8=False,
        base_cost=kakera_base_cost_from_state(state),
    )


class AltKakera:
    def __init__(
        self,
        pool: Any,
        *,
        log: Callable[[str], None] | None = None,
        outcome_timeout: float = OUTCOME_TIMEOUT_SEC,
        dk_timeout: float = DK_REPLY_TIMEOUT_SEC,
        dk_settle: float = DK_SETTLE_SEC,
    ) -> None:
        self._pool = pool
        self._log = log or (lambda _t: None)
        self._timeout = outcome_timeout
        self._dk_timeout = dk_timeout
        self._dk_settle = dk_settle
        self._dk_locks: dict[str, asyncio.Lock] = {}
        self._done: set[str] = set()
        self._tasks: set[asyncio.Task[Any]] = set()

    # ---- called by the main's reactor -------------------------------------

    def main_power_short(self, message_id: int, fields: dict[str, Any]) -> None:
        """The main left this roll's kakera for lack of power. Never blocks."""
        if fields.get("perk_8"):
            return
        buttons = [
            b
            for b in fields.get("buttons") or []
            if isinstance(b, dict) and b.get("is_kakera") and not b.get("disabled")
        ]
        if not buttons:
            return
        task = asyncio.get_running_loop().create_task(self.handle(int(message_id), buttons))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ---- per button: one alt at a time ------------------------------------

    def _eligible(self, account_id: str, emoji: str) -> bool:
        session = self._pool.sessions.get(account_id)
        if session is None or not session.connected or not session.ready:
            return False
        rules = session.spec.rules
        if not rules.enabled or not rules.kakera.on_main_rolls:
            return False
        if emoji not in rules.kakera.main_roll_types:
            return False
        state = session.state
        refresh_reaction_power(state)
        if state.power_percent is None:
            return False  # an unread bar is not a full one
        if can_afford_reaction(state, alt_click_cost(state, emoji)):
            return True
        return self._may_dk(session)

    @staticmethod
    def _may_dk(session: Any) -> bool:
        return bool(session.spec.rules.kakera.use_dk) and has_dk_available(session.state)

    async def _use_dk(self, session: Any, cost: float, emoji: str) -> bool:
        """The alt's own ``$dk``; True when its bar can now pay ``cost``."""
        lock = self._dk_locks.setdefault(session.account_id, asyncio.Lock())
        async with lock:
            state = session.state
            refresh_reaction_power(state)
            if state.power_percent is not None and can_afford_reaction(state, cost):
                return True  # another button's $dk already refilled it
            if not self._may_dk(session):
                return False
            name = session.spec.name
            before = state.power_percent
            session.status = "$dk"
            self._pool.notify()
            gap = getattr(self._pool, "own_gap", None)
            if gap is not None:
                await gap(session)
            sent = await session.actions.send_command("dk", prefix=session.spec.config.prefix)
            session.last_command_at = time.monotonic()
            if sent is None:
                self._log(f"Alts: {name} could not send $dk")
                return False
            found = await session.actions.wait_for(
                lambda s, p: int(getattr(s, "message_id", 0) or 0) > int(sent)
                and (bool(p.fields.get("dk_used")) or is_dk_claim(getattr(s, "content", "") or "")),
                timeout=self._dk_timeout,
            )
            if found is None:
                session.actions.release_hold()
                self._log(f"Alts: {name} $dk — no answer from Mudae")
                return False
            snap, parsed = found
            fields = dict(parsed.fields)
            if not fields.get("dk_used"):
                fields.update(extract_dk_fields(getattr(snap, "content", "") or ""))
            apply_dk_response(state, fields)
            amount = int(fields.get("amount") or 0)
            if amount and state.kakera_stock is not None:
                state.kakera_stock = int(state.kakera_stock) + amount
            if amount and getattr(self._pool, "ledger", None) is not None:
                self._pool.ledger.add(session.account_id, "kakera_earned", amount)
            self._log(
                f"Alts: {name} used $dk for {emoji} on the main's roll · power "
                f"{before if before is not None else '?'}% → {state.power_percent:g}%"
                + (f" · +{amount:,} kakera" if amount else "")
                + (f" · {state.dk_stock} $dk left" if state.dk_stock is not None else "")
            )
            await asyncio.sleep(self._dk_settle)
            return can_afford_reaction(state, cost)

    async def handle(self, message_id: int, buttons: list[dict[str, Any]]) -> int:
        clicked = 0
        coordinator = self._pool.coordinator
        for button in buttons:
            emoji = _kakera_emoji(button)
            custom_id = str(button.get("custom_id") or "")
            if not custom_id or emoji == "kakeraP":
                continue  # purple is free: the main never leaves it for power
            key = kakera_key(message_id, custom_id)
            if key in self._done:
                continue
            while True:
                owner = coordinator.assign(key, lambda acc: self._eligible(acc, emoji), alts_only=True)
                if owner is None:
                    break
                if await self._click(owner, message_id, custom_id, emoji):
                    self._done.add(key)
                    clicked += 1
                    break
                coordinator.pass_on(key, owner)
        return clicked

    async def _click(self, account_id: str, message_id: int, custom_id: str, emoji: str) -> bool:
        session = self._pool.sessions[account_id]
        state = session.state
        cost = alt_click_cost(state, emoji)
        previous = session.status
        try:
            refresh_reaction_power(state)
            if not can_afford_reaction(state, cost) and not await self._use_dk(session, cost, emoji):
                return False
            result = await self._click_once(session, message_id, custom_id, emoji, cost)
            if result is None and await self._use_dk(session, cost, emoji):
                # Refused although the bar said it could pay: refill, try once more.
                result = await self._click_once(session, message_id, custom_id, emoji, cost)
            return bool(result)
        finally:
            session.status = previous
            self._pool.notify()

    async def _click_once(
        self, session: Any, message_id: int, custom_id: str, emoji: str, cost: float
    ) -> bool | None:
        """True clicked, False failed, None refused for power."""
        account_id = session.account_id
        state = session.state
        names = {n.casefold() for n in session.names()}
        session.status = f"kakera on the main's roll ({emoji})"
        self._pool.notify()
        if not await session.actions.click_button(message_id, custom_id):
            self._log(f"Alts: {session.spec.name} could not click {emoji}")
            return False
        found = await session.actions.wait_for(
            # Newer than the roll: never an earlier outcome left in the queue.
            lambda s, p: int(getattr(s, "message_id", 0) or 0) > int(message_id)
            and is_kakera_outcome_message(s, p)
            and str(normalize_kakera_outcome(s, p).fields.get("claimed_by") or "").casefold() in names,
            timeout=self._timeout,
        )
        if found is None:
            self._log(f"Alts: {session.spec.name} clicked {emoji} — no answer from Mudae")
            return False
        outcome = normalize_kakera_outcome(*found)
        if outcome.kind == MessageKind.KAKERA_REACT_DENIED:
            wait = outcome.fields.get("kakera_cooldown_minutes")
            if wait is not None:
                sync_reaction_power_from_denial(state, cooldown_minutes=int(wait), cost=cost)
            else:
                state.power_percent = 0
            self._log(f"Alts: {session.spec.name} refused {emoji} — out of power")
            return None
        spend_reaction_power(state, cost)
        amount = outcome.fields.get("amount")
        session.kakera_from_main_rolls += int(amount or 0)
        if amount and state.kakera_stock is not None:
            # Kept current so a pass needs no $tu (macro/alt_passing.py).
            state.kakera_stock = int(state.kakera_stock) + int(amount)
        if getattr(self._pool, "ledger", None) is not None and amount:
            self._pool.ledger.add(account_id, "kakera_earned", int(amount))
        self._log(
            f"Alts: {session.spec.name} took {emoji} on the main's roll"
            + (f" (+{int(amount):,})" if amount else "")
            + f" · {cost:g}% power"
        )
        return True
