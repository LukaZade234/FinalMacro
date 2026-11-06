"""Turn-taking for several accounts in one channel.

The main and its alts watch the same rolls and send into the same channel, so
without an arbiter they would all jump at the same trigger: two accounts
clicking one claim button, three alts racing for a force-divorced character,
two commands landing in the same second. Preventing that is this module's
only job, and every alt action goes through it.

Three rules:

1. **One account per trigger.** A trigger (a claimable roll, one kakera button,
   one force-divorce claim window) has a stable key. :meth:`assign` hands it to
   the first eligible account in turn order and remembers the answer, so asking
   again — from any account — returns the same owner. An account acts only on
   triggers it owns.
2. **Fixed turn order.** The main first, then the alts in their configured
   order. Every account sees the same order, so "whose turn is it" never
   depends on who noticed first.
3. **One command lane.** Commands from every account go through
   :meth:`command_lane`, which lets one account type at a time and keeps
   different accounts' commands at least ``command_gap`` apart. After a
   command the lane stays *held* for that account until its reply has been
   read (:meth:`reply_seen`) or ``reply_hold`` runs out, so no other account's
   command lands while the first is still waiting on Mudae — two ``$tu`` in
   flight at once could each read the other's answer.

``$us`` belongs to the main alone (:meth:`may_roll_us`).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Iterable

# Gap between two commands from *different* accounts (the 1 s spacing rule).
COMMAND_GAP_SEC = 1.0
# Longest another account waits for the last sender's reply before typing.
REPLY_HOLD_SEC = 4.0
# Triggers remembered; old ones are forgotten first. A busy hour is a few
# hundred rolls with a handful of buttons each.
MAX_REMEMBERED_TRIGGERS = 4000


def claim_key(message_id: int) -> str:
    return f"claim:{int(message_id)}"


def kakera_key(message_id: int, custom_id: str) -> str:
    return f"kakera:{int(message_id)}:{custom_id}"


def force_divorce_key(cycle: int | str) -> str:
    return f"fd:{cycle}"


class ChannelCoordinator:
    def __init__(
        self,
        main_id: str,
        alt_ids: Iterable[str] = (),
        *,
        command_gap: float = COMMAND_GAP_SEC,
        reply_hold: float = REPLY_HOLD_SEC,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.main_id = str(main_id)
        self._alts: list[str] = []
        self.set_alt_order(alt_ids)
        self._gap = float(command_gap)
        self._clock = clock
        self._sleep = sleep or asyncio.sleep
        self._owners: OrderedDict[str, str] = OrderedDict()
        self._passed: dict[str, set[str]] = {}
        self._lane = asyncio.Lock()
        self._last_sent_at: float | None = None
        self._last_sender: str | None = None
        self._reply_hold = float(reply_hold)
        self._hold_owner: str | None = None
        self._hold_until = 0.0
        self._hold_cleared: asyncio.Event | None = None

    # ---- order -----------------------------------------------------------

    def set_alt_order(self, alt_ids: Iterable[str]) -> None:
        seen: list[str] = []
        for acc in alt_ids:
            acc = str(acc)
            if acc and acc != self.main_id and acc not in seen:
                seen.append(acc)
        self._alts = seen

    @property
    def alts(self) -> list[str]:
        return list(self._alts)

    @property
    def roster(self) -> list[str]:
        """Everyone, in turn order: the main, then the alts."""
        return [self.main_id, *self._alts]

    def is_main(self, account_id: str) -> bool:
        return str(account_id) == self.main_id

    def may_roll_us(self, account_id: str) -> bool:
        return self.is_main(account_id)

    # ---- triggers --------------------------------------------------------

    def assign(
        self,
        key: str,
        eligible: Callable[[str], bool],
        *,
        alts_only: bool = False,
    ) -> str | None:
        """The one account that acts on ``key``.

        Already assigned → the same owner, whoever asks. Otherwise the first
        account in turn order that ``eligible`` accepts and that has not passed
        on this trigger; ``alts_only`` leaves the main out (the main decides
        its own rolls before any alt is asked). ``None`` when nobody may act.
        """
        owner = self._owners.get(key)
        if owner is not None:
            return owner
        passed = self._passed.get(key, set())
        candidates = self._alts if alts_only else self.roster
        for acc in candidates:
            if acc in passed:
                continue
            if eligible(acc):
                self._remember(key, acc)
                return acc
        return None

    def owner(self, key: str) -> str | None:
        return self._owners.get(key)

    def owns(self, key: str, account_id: str) -> bool:
        return self._owners.get(key) == str(account_id)

    def pass_on(self, key: str, account_id: str) -> None:
        """The owner could not act (claim failed to send, no power after all).

        It loses the trigger and is skipped when :meth:`assign` is asked
        again, so the next account in order gets its turn — never the same
        one twice, and never two at once.
        """
        if self._owners.get(key) == str(account_id):
            del self._owners[key]
        self._passed.setdefault(key, set()).add(str(account_id))

    def _remember(self, key: str, account_id: str) -> None:
        self._owners[key] = account_id
        self._owners.move_to_end(key)
        while len(self._owners) > MAX_REMEMBERED_TRIGGERS:
            old, _ = self._owners.popitem(last=False)
            self._passed.pop(old, None)

    # ---- force divorce ---------------------------------------------------

    def force_divorce_claimers(self, ready: Callable[[str], bool]) -> list[str]:
        """Who claims the target this reset, in order.

        Each alt with a claim in hand gets one cycle, in turn order, and the
        main claims last, so the character always ends the reset with the main.
        The main is included only when ``ready`` says it has a slot.
        """
        order = [acc for acc in self._alts if ready(acc)]
        if ready(self.main_id):
            order.append(self.main_id)
        return order

    # ---- command lane ----------------------------------------------------

    @asynccontextmanager
    async def command_lane(self, account_id: str) -> AsyncIterator[None]:
        """Hold the channel's command lane while one account sends.

        A command from a different account than the last one waits until
        ``command_gap`` has passed since that last command. The same account
        keeps its own pacing (roll delay, waits on replies) inside its engine.
        """
        account_id = str(account_id)
        async with self._lane:
            await self._wait_out_hold(account_id)
            if self._last_sent_at is not None and self._last_sender != account_id:
                wait = self._gap - (self._clock() - self._last_sent_at)
                if wait > 0:
                    await self._sleep(wait)
            try:
                yield
            finally:
                self._last_sent_at = self._clock()
                self._last_sender = account_id
                if self._reply_hold > 0:
                    self._hold_owner = account_id
                    self._hold_until = self._clock() + self._reply_hold
                    self._hold_cleared = asyncio.Event()

    def reply_seen(self, account_id: str) -> None:
        """``account_id`` has read the reply it was waiting for: free the lane."""
        if self._hold_owner == str(account_id):
            self._hold_owner = None
            if self._hold_cleared is not None:
                self._hold_cleared.set()

    async def _wait_out_hold(self, account_id: str) -> None:
        owner, event = self._hold_owner, self._hold_cleared
        if owner is None or owner == account_id or event is None:
            return
        remaining = self._hold_until - self._clock()
        if remaining > 0:
            try:
                await asyncio.wait_for(event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass
        if self._hold_owner == owner:
            self._hold_owner = None
