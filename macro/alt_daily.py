"""Each alt's start-of-day steps: its own minigames, then the once-a-day pass.

Run from the main's session start (``RollCycleEngine.before_roll_batch``),
after the alts' ``$tu`` and after the main's own start-of-day steps, and
before the main's first roll. So the alt plays while nothing else in the
channel does — the minigame runner takes the next board it sees and does not
check whose it is.

**Once a day, then not asked again.** The main re-checks ``$ohu`` at every
session start because upgrades and chaos keep adding uses through the day.
An alt gains none, so each step is done once per Mudae day (UTC) and saved
in the ledger (``AltLedger.done_today``); until the next day the alt is not
even asked ``$ohu``. The first session of the day after the reset — or the
first after the app starts later in the day — is when it happens.

A minigame run that never reached a decision (``$ohu`` unanswered, already
running) leaves the day open, so the next session start tries again.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

MINIGAMES_STEP = "minigames"

# Plays one alt's minigames; returns the runner's result dict, or None when
# it never reached a decision.
PlayFor = Callable[[Any], Awaitable[dict[str, Any] | None]]


class AltDaily:
    def __init__(
        self,
        pool: Any,
        *,
        play_minigames: PlayFor,
        passing: Any,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._pool = pool
        self._play = play_minigames
        self._passing = passing
        self._log = log or (lambda _t: None)

    async def run_due(self) -> None:
        """Every connected alt, in turn order: what is still due today."""
        for session in list(self._pool.connected_sessions()):
            if not session.spec.rules.enabled:
                continue
            await self._minigames(session)
            await self._passing.start_of_day(session)

    async def _minigames(self, session: Any) -> None:
        ledger = getattr(self._pool, "ledger", None)
        account_id = session.spec.account_id
        if ledger is not None and ledger.done_today(account_id, MINIGAMES_STEP):
            return
        spheres = session.spec.rules.spheres
        if not spheres.minigames or not spheres.games:
            if ledger is not None:
                ledger.mark_done(account_id, MINIGAMES_STEP)
            return
        previous, session.status = session.status, "daily minigames"
        self._pool.notify()
        try:
            gap = getattr(self._pool, "own_gap", None)
            if gap is not None:
                await gap(session)  # $ohu must not land on the alt's $tu
            result = await self._play(session)
        except Exception as exc:  # noqa: BLE001 - one alt must not stop the others or the main
            self._log(f"Alts: {session.spec.name} minigames failed ({exc})")
            result = None
        finally:
            session.status = previous
            if hasattr(session, "last_command_at"):
                session.last_command_at = time.monotonic()
            self._pool.notify()
        if result is None or result.get("reason") == "ohu failed":
            self._log(f"Alts: {session.spec.name} minigames not decided — retried next session")
            return
        played = result.get("played") or {}
        if ledger is not None:
            ledger.mark_done(account_id, MINIGAMES_STEP)
        self._log(
            f"Alts: {session.spec.name} daily minigames done"
            + (f" ({', '.join('$' + g for g in played)})" if played else " (nothing left today)")
        )
