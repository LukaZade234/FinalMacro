"""Alts claim the main's rolls the main can't, then ``$give`` them to it.

Two triggers, both from the main's engine, both judged by the **main's**
claim rules (an alt has no say in what is worth claiming on the main's rolls):

* **Mid-batch, main on cooldown** (:meth:`AltClaims.offer`) — a roll the main
  would claim right now (a wish, or an instant trigger such as its kakera or
  rank threshold) but has no claim for. One alt claims it at once; the main
  keeps rolling.
* **End of the batch** (:meth:`AltClaims.batch_end`) — after the main's own
  end-of-batch claim, the alts take the next best eligible rolls in turn
  order: the first alt the best roll left, the second the next, and so on.
  If the main claimed the best, the alts get the 2nd and 3rd; if the main had
  no claim, they get the 1st and 2nd. Only rolls still inside the claim timer
  count, as for the main.

Each claim goes to one alt through the channel coordinator (``claim_key``),
and is confirmed only by Mudae's claim message naming that alt. The
characters are given to the main by :meth:`AltClaims.give_pending` once the
main's batch is over, never while it rolls.

An alt may claim when it is ready (``$bonus`` read), connected, its rules are
on, its Claims source includes the main's rolls, and its own ``$tu`` said it
can claim. Never a perk-6 free claim: that green button is the roller's.

**``$rt`` in the force-divorce farm** (Claims › "Spend $rt"): an alt whose
claim is spent but whose ``$rt`` is ready is one more alt cycle. Only when
the main has no claim of its own (the main's own slot comes first, and its
``$rt`` stays for its wishes), and only with at least
``RT_MIN_MINUTES_BEFORE_RESET`` left before the alt's claim reset, the same
rule the main keeps. The alt sends ``$rt`` when the target rolls; Mudae
confirms with a tick on the command and nothing else, and without the tick
the alt's ``$tu`` decides.
"""

from __future__ import annotations

import asyncio
import copy
import time
from typing import Any, Callable

from macro.alt_rules import SOURCE_BOTH, SOURCE_MAIN
from macro.force_divorce import RT_MIN_MINUTES_BEFORE_RESET
from macro.live_clock import remaining_minutes
from macro.rt_manager import apply_rt_response
from macro.post_roll import RollRecord, records_within_claim_timer, roll_total_kakera
from macro.rule_eval import passes_character_claim
from macro.turns import claim_key
from mudae.types import MessageKind

CLAIM_REPLY_TIMEOUT_SEC = 8.0
RT_TICK_TIMEOUT_SEC = 8.0
# Between the tick and the claim, as the main waits.
RT_SETTLE_SEC = 1.0
CLAIM_REACTION_EMOJI = "💖"


def rank_for_alts(
    records: list[RollRecord],
    rules: Any,
    main_state: Any,
    *,
    final_hour: bool,
    expire_sec: int,
) -> list[RollRecord]:
    """The batch's rolls the main's rules would claim, best first.

    Judged as if a claim were in hand: whether the *main* has one is not the
    question for an alt's claim.
    """
    state = copy.copy(main_state)
    state.claim_available = True
    out = []
    for record in records_within_claim_timer(records, expire_sec):
        fields = record.fields
        if fields.get("claimed") or not fields.get("can_claim") or fields.get("free_claim"):
            continue
        decision = passes_character_claim(
            fields, rules, state, final_hour=final_hour, wished_pinged=False
        )
        if decision.should_claim or decision.reason == "eligible at end of batch":
            out.append(record)
    out.sort(key=lambda r: roll_total_kakera(r.fields), reverse=True)
    return out


class AltClaims:
    def __init__(
        self,
        pool: Any,
        *,
        log: Callable[[str], None] | None = None,
        reply_timeout: float = CLAIM_REPLY_TIMEOUT_SEC,
        farm_active: Callable[[], bool] | None = None,
        main_has_claim: Callable[[], bool] | None = None,
        rt_settle: float = RT_SETTLE_SEC,
    ) -> None:
        self._pool = pool
        # The main's own claim comes before an alt's $rt in the farm.
        self._main_has_claim = main_has_claim or (lambda: False)
        self._rt_settle = rt_settle
        # True while the main runs the force-divorce farm: alts with Claims ›
        # Force divorce on keep their claims for the farm's alt cycles.
        self._farm_active = farm_active or (lambda: False)
        self._log = log or (lambda _t: None)
        self._timeout = reply_timeout
        self._tasks: set[asyncio.Task[Any]] = set()
        # account id → characters claimed for the main, not yet given. Kept
        # in the ledger, so a restart before the batch-end $give keeps them.
        ledger = getattr(pool, "ledger", None)
        self.pending: dict[str, list[str]] = (
            {acc: list(names) for acc, names in ledger.pending.items()} if ledger is not None else {}
        )
        for acc, names in self.pending.items():
            session = pool.sessions.get(acc)
            if session is not None:
                session.claimed_for_main = list(names)

    def _save_pending(self, account_id: str) -> None:
        ledger = getattr(self._pool, "ledger", None)
        if ledger is not None:
            ledger.set_pending(account_id, self.pending.get(account_id, []))

    # ---- who may claim ----------------------------------------------------

    def _eligible(self, account_id: str) -> bool:
        session = self._pool.sessions.get(account_id)
        if session is None or not session.connected or not session.ready:
            return False
        rules = session.spec.rules
        if not rules.enabled or rules.claims.source not in (SOURCE_MAIN, SOURCE_BOTH):
            return False
        if rules.claims.force_divorce and self._farm_active():
            return False  # its claim is the farm's this reset
        # Unknown is not "available": the alt's session-start $tu says so.
        return session.state.claim_available is True

    def _farm_eligible(self, account_id: str) -> bool:
        """May claim the force-divorce target on an alt cycle."""
        session = self._pool.sessions.get(account_id)
        if session is None or not session.connected or not session.ready:
            return False
        rules = session.spec.rules
        if not rules.enabled or not rules.claims.force_divorce:
            return False
        return session.state.claim_available is True or self._rt_slot(session)

    def _rt_slot(self, session: Any) -> bool:
        """The alt's ``$rt`` may buy it a farm claim right now."""
        if not session.spec.rules.claims.spend_rt or session.state.rt_available is not True:
            return False
        try:
            if self._main_has_claim():
                return False
        except Exception:  # noqa: BLE001
            return False
        state = session.state
        left = remaining_minutes(getattr(state, "claim_reset_at", "") or "")
        if left is None:
            left = state.next_claim_reset_minutes
        # Unknown is not "plenty": a reset bought just before the claim reset is wasted.
        return left is not None and int(left) >= RT_MIN_MINUTES_BEFORE_RESET

    async def _use_rt(self, session: Any) -> bool:
        """The alt's ``$rt``; True once it has a claim again."""
        name = session.spec.name
        gap = getattr(self._pool, "own_gap", None)
        if gap is not None:
            await gap(session)
        sent = await session.actions.send_command("rt", prefix=session.spec.config.prefix)
        session.last_command_at = time.monotonic()
        if sent is None:
            self._log(f"Alts: {name} could not send $rt")
            return False
        ticked = await session.actions.wait_for_mudae_tick(sent, timeout=RT_TICK_TIMEOUT_SEC)
        # A tick is all Mudae sends: nothing else will clear the lane's hold.
        session.actions.release_hold()
        if not ticked:
            self._log(f"Alts: {name} $rt — no tick, asking $tu")
            refresh = getattr(self._pool, "refresh_status", None)
            if refresh is None or not await refresh(session):
                return False
            if session.state.claim_available is not True:
                self._log(f"Alts: {name} $rt did not land")
                return False
        else:
            apply_rt_response(session.state, {"rt_used": True, "claim_available": True})
            await asyncio.sleep(self._rt_settle)
        session.state.rt_available = False
        self._log(f"Alts: {name} used $rt for the force-divorce alt cycle")
        return True

    # ---- force-divorce alt cycle ------------------------------------------

    def farm_ready(self) -> bool:
        """Some alt can claim the target this cycle (a slot for the divorce)."""
        return any(self._farm_eligible(acc) for acc in self._pool.coordinator.alts)

    async def claim_for_farm(self, record: RollRecord) -> dict[str, Any] | None:
        """One alt claims the farm's target; the engine gives it back.

        Returns ``{"account_id", "name", "kakera", "spheres"}`` or ``None``
        (the main's own slot is then the fallback). Nothing is queued for the
        batch-end give: the target goes back at once, before the next divorce.
        """
        return await self._claim_one(record, "$forcedivorce alt cycle", farm=True)

    # ---- mid-batch --------------------------------------------------------

    def offer(self, record: RollRecord, reason: str) -> None:
        """The main would claim this now but has no claim. Never blocks."""
        if record.fields.get("free_claim"):
            return
        task = asyncio.get_running_loop().create_task(self._claim_one(record, reason))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ---- end of the batch -------------------------------------------------

    async def batch_end(self, ranked: list[RollRecord]) -> int:
        """Hand the best rolls left to the alts, one each, in turn order."""
        claimed = 0
        for record in ranked:
            if not any(self._eligible(acc) for acc in self._pool.coordinator.alts):
                break
            if record.fields.get("claimed"):
                continue
            if await self._claim_one(record, "best left this batch"):
                claimed += 1
        return claimed

    async def wait_idle(self) -> None:
        """Let mid-batch claims finish before the batch-end ones and the gives."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ---- one roll, one alt at a time --------------------------------------

    async def _claim_one(
        self, record: RollRecord, reason: str, *, farm: bool = False
    ) -> dict[str, Any] | None:
        coordinator = self._pool.coordinator
        key = claim_key(record.message_id)
        eligible = self._farm_eligible if farm else self._eligible
        while True:
            owner = coordinator.assign(key, eligible, alts_only=True)
            if owner is None:
                return None
            result = await self._claim(owner, record, reason, farm=farm)
            if result is not None:
                return result
            if record.fields.get("claimed"):
                return None  # someone else got it — nothing to pass on
            coordinator.pass_on(key, owner)

    async def _claim(
        self, account_id: str, record: RollRecord, reason: str, *, farm: bool = False
    ) -> dict[str, Any] | None:
        session = self._pool.sessions[account_id]
        name = record.character_name or "?"
        names = {n.casefold() for n in session.names()}
        previous, session.status = session.status, f"claiming {name} for the main"
        self._pool.notify()
        try:
            if farm and session.state.claim_available is not True:
                if not self._rt_slot(session) or not await self._use_rt(session):
                    return None
            if not await self._send(session, record):
                self._log(f"Alts: {session.spec.name} could not claim {name}")
                return None
            # Only replies newer than this roll: an earlier claim of the same
            # character (the farm claims one target over and over) is still in
            # the queue, and taking it read kleinam0n's own claim as
            # lukijade's (2026-11-06).
            found = await session.actions.wait_for(
                lambda s, p: _after(s, record.message_id)
                and (
                    p.kind == MessageKind.CLAIM_INTERVAL
                    or (
                        p.kind in (MessageKind.CLAIM, MessageKind.MARRIAGE)
                        and _same_name(p.fields.get("character"), name)
                    )
                ),
                timeout=self._timeout,
            )
            if found is None:
                self._log(f"Alts: {session.spec.name} claimed {name} — no answer from Mudae")
                return None
            parsed = found[1]
            if parsed.kind == MessageKind.CLAIM_INTERVAL:
                session.state.claim_available = False
                self._log(f"Alts: {session.spec.name} has no claim after all")
                return None
            winner = str(parsed.fields.get("winner") or "").casefold()
            record.fields["claimed"] = True
            if winner not in names:
                self._log(f"Alts: {name} went to {parsed.fields.get('winner') or 'someone else'}")
                return None
            session.state.claim_available = False
            gained = parsed.fields.get("kakera")
            if gained and session.state.kakera_stock is not None:
                # The claim's payout is the alt's: keep its stock current.
                session.state.kakera_stock = int(session.state.kakera_stock) + int(gained)
            ledger = getattr(self._pool, "ledger", None)
            if farm:
                if ledger is not None:
                    ledger.add(account_id, "fd_cycles", 1)
                    ledger.add(account_id, "kakera_earned", int(gained or 0))
            else:
                self.pending.setdefault(account_id, []).append(name)
                session.claimed_for_main = list(self.pending[account_id])
                self._save_pending(account_id)
                if ledger is not None:
                    ledger.add(account_id, "claims", 1)
            self._log(f"Alts: {session.spec.name} claimed {name} for the main ({reason})")
            return {
                "account_id": account_id,
                "name": session.spec.name,
                "kakera": int(gained or 0),
                "spheres": int(parsed.fields.get("spheres") or 0),
            }
        finally:
            session.status = previous
            self._pool.notify()

    async def _send(self, session: Any, record: RollRecord) -> bool:
        method = record.fields.get("claim_method")
        if method == "reaction":
            return bool(await session.actions.add_reaction(record.message_id, CLAIM_REACTION_EMOJI))
        from mudae.buttons import is_claim_button

        button = next(
            (
                b
                for b in record.fields.get("buttons") or []
                if isinstance(b, dict) and is_claim_button(b) and not b.get("disabled")
            ),
            None,
        )
        custom_id = str((button or {}).get("custom_id") or "")
        if not custom_id:
            return False
        return bool(await session.actions.click_button(record.message_id, custom_id))

    # ---- give to the main -------------------------------------------------

    async def give_pending(self) -> int:
        """``$give`` every character the alts claimed this batch to the main."""
        given = 0
        for account_id in list(self._pool.coordinator.alts):
            names = self.pending.get(account_id) or []
            session = self._pool.sessions.get(account_id)
            while names and session is not None and session.connected:
                character = names[0]
                result = await self._pool.give_to_main(
                    account_id, character=character, why="claimed for the main"
                )
                if not result.ok:
                    self._log(
                        f"Alts: {session.spec.name} could not give {character} to the main "
                        f"({result.reason}) — kept for the next batch end"
                    )
                    break
                names.pop(0)
                given += 1
                self._save_pending(account_id)
            if session is not None:
                session.claimed_for_main = list(names)
        self._pool.notify()
        return given


def _after(snapshot: Any, message_id: Any) -> bool:
    """Discord ids grow with time: a reply to a roll comes after the roll."""
    try:
        return int(getattr(snapshot, "message_id", 0) or 0) > int(message_id or 0)
    except (TypeError, ValueError):
        return True


def _same_name(a: Any, b: Any) -> bool:
    return str(a or "").strip().casefold() == str(b or "").strip().casefold()
