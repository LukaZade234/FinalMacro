"""Alts pass kakera and spheres to the main on their own, per their Transfers.

Two moments, both while the main is not rolling and nothing else has a y/n
question open; one alt at a time, in turn order.

Per resource (Kakera › Pass to main, Spheres › Pass to main):

* ``never`` — nothing.
* ``session`` (end of session) — every batch end, after the claimed
  characters are given (:meth:`AltPassing.batch_end`).
* ``daily`` (once a day) — one of the alt's start-of-day steps, after its
  own minigames (:meth:`AltPassing.start_of_day`, from
  ``macro/alt_daily.py``). Marked done for the Mudae day (UTC) once the
  transfer went through or there was nothing above the reserve; a failure
  is retried at the next session start that day.
* ``above`` (above reserve) — every batch end, like end of session, and
  also straight after the alt's minigames, when its spheres jump.

Each pass sends everything above the alt's reserve (``keep``) for that
resource, from the stock the macro already knows — no ``$tu`` just before it:

* kakera — the alt's session-start ``$tu``, plus what it earned since on
  the main's rolls and claims (``AltKakera`` / ``AltClaims`` add it), minus
  what it passed;
* spheres — the session-start ``$tu``, then the ``(Stock: N)`` Mudae prints
  as each of the alt's minigames finishes.

Only a stock the macro has never seen is read (``$tu``, then ``$ku`` /
``$ohu``). Every transfer waits :data:`PASS_GAP_SEC` after the alt's last
command (Mudae drops a command sent straight after another one); when Mudae
never asks to confirm, nothing was sent, so it is tried once more. Kakera
and spheres are separate: one failing does not stop the other.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from macro.alt_rules import PASS_ABOVE, PASS_DAILY, PASS_SESSION
from mudae.parsers.transfers import KIND_KAKERA, KIND_SPHERES

PASS_GAP_SEC = 2.0
RETRY_PAUSE_SEC = 3.0
_NO_PROMPT = "no confirmation prompt"

_WHY = {PASS_SESSION: "end of session", PASS_DAILY: "once a day", PASS_ABOVE: "above reserve"}


class AltPassing:
    def __init__(
        self,
        pool: Any,
        *,
        log: Callable[[str], None] | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._pool = pool
        self._log = log or (lambda _t: None)
        self._sleep = sleep

    def _plan(self, session: Any, modes: tuple[str, ...]) -> list[tuple[str, str, int]]:
        rules = session.spec.rules
        if not rules.enabled:
            return []
        ledger = getattr(self._pool, "ledger", None)
        out = []
        for resource, mode, keep in (
            (KIND_KAKERA, rules.kakera.pass_mode, rules.kakera.keep),
            (KIND_SPHERES, rules.spheres.pass_mode, rules.spheres.keep),
        ):
            if mode not in modes:
                continue
            if mode == PASS_DAILY and ledger is not None and ledger.passed_today(session.spec.account_id, resource):
                continue
            out.append((resource, mode, keep))
        return out

    async def batch_end(self) -> int:
        """End-of-session and above-reserve passes for every connected alt."""
        made = 0
        for session in list(self._pool.connected_sessions()):
            due = self._plan(session, (PASS_SESSION, PASS_ABOVE))
            if due:
                made += await self._pass(session, due)
        return made

    async def start_of_day(self, session: Any) -> int:
        """Once-a-day passes (and above-reserve, after the minigames) for one alt."""
        due = self._plan(session, (PASS_DAILY, PASS_ABOVE))
        return await self._pass(session, due) if due else 0

    async def _pass(self, session: Any, due: list[tuple[str, str, int]]) -> int:
        account_id = session.spec.account_id
        state = session.state
        if any(
            getattr(state, "kakera_stock" if r == KIND_KAKERA else "sphere_stock") is None
            for r, _m, _k in due
        ):
            # Never seen this session (no $tu yet): the one case worth asking.
            await self._pool.read_stocks(account_id)
        made = 0
        ledger = getattr(self._pool, "ledger", None)
        for resource, mode, keep in due:
            attr = "kakera_stock" if resource == KIND_KAKERA else "sphere_stock"
            stock = getattr(state, attr)
            if stock is None:
                self._log(f"Alts: {session.spec.name} — {resource} stock unknown, not passed")
                continue
            amount = self._pool.amount_to_pass(stock, keep)
            if amount <= 0:
                if mode == PASS_DAILY and ledger is not None:
                    ledger.mark_passed(account_id, resource)  # nothing above the reserve today
                continue
            ok = False
            for attempt in (1, 2):
                await self._sleep(PASS_GAP_SEC if attempt == 1 else RETRY_PAUSE_SEC)
                results = await self._pool.pass_to_main(
                    account_id,
                    kakera_keep=keep if resource == KIND_KAKERA else None,
                    spheres_keep=keep if resource == KIND_SPHERES else None,
                    why=_WHY[mode],
                )
                last = results[-1] if results else None
                ok = bool(last and last.ok)
                # Mudae never asked: nothing was given, so one more try is safe.
                # Anything else (a y went out) is not retried blind.
                if ok or last is None or last.confirmed or last.reason != _NO_PROMPT:
                    break
                self._log(f"Alts: {session.spec.name} — Mudae didn't ask to confirm, trying once more")
            if ok:
                made += 1
                if mode == PASS_DAILY and ledger is not None:
                    ledger.mark_passed(account_id, resource)
                unit = "ka" if resource == KIND_KAKERA else "sp"
                self._log(
                    f"Alts: {session.spec.name} passed {amount:,} {unit} to the main "
                    f"({_WHY[mode]}, kept {int(keep):,})"
                )
            # A failure leaves this resource for next time; the other still goes.
        return made
