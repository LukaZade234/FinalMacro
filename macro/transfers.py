"""Hand characters, kakera and spheres from an alt to the main.

The three exchanges (captured 2026-11-05, ``mudae/parsers/transfers.py``):

* ``$give <@main> Lucy`` — Mudae asks the **receiver**; the main types ``y``.
* ``$givek <@main> 1000`` / ``$givesp <@main> 100`` — Mudae asks the
  **giver**; the alt types ``y``.

The ping is always ``<@id>``, a real mention: ``@name`` is not one.

**Every ``y`` is gated**, the way ``$forcedivorce``'s is. Before answering, the
prompt must name exactly what was asked for — the character and the receiver's
id, or the giver's Discord username and the amount. Anything else is answered ``n``,
so a wrong question is closed rather than left open for a later ``y`` to
confirm by accident.

**No other question may be open** on either account while this runs: a bare
``y`` answers whatever Mudae asked last. Both accounts' open-prompt locks
(``DiscordActions.open_prompt``) are held for the whole exchange, and the
main's own ``$forcedivorce`` / ``$kl`` / list questions hold the same lock.

Replies are read on the **giver's** connection only — it sees the whole channel,
and nothing else consumes its queue — so the main's engine never has a
transfer message taken from under one of its own waits.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from macro.actions import prompt_guard
from mudae.parsers.transfers import KIND_CHARACTER, KIND_KAKERA, KIND_SPHERES
from mudae.types import MessageKind

PROMPT_TIMEOUT_SEC = 12.0
RESULT_TIMEOUT_SEC = 12.0
# Between reading the question and typing the answer (the 1 s spacing rule).
STEP_PAUSE_SEC = 1.0

_COMMANDS = {KIND_KAKERA: "givek", KIND_SPHERES: "givesp"}


@dataclass
class TransferParty:
    """One side of a transfer: its actions, Discord id and Discord usernames."""

    actions: Any
    user_id: int | str
    names: list[str] = field(default_factory=list)

    def is_named(self, name: str) -> bool:
        wanted = _norm(name)
        return bool(wanted) and any(_norm(n) == wanted for n in self.names)


@dataclass
class TransferResult:
    ok: bool
    transfer: str
    amount: int | None = None
    character: str | None = None
    reason: str = ""
    # ``y`` was sent: on a missing result the transfer may still have landed.
    confirmed: bool = False


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def mention(user_id: int | str) -> str:
    return f"<@{int(user_id)}>"


class Transfers:
    def __init__(
        self,
        *,
        prefix: str = "$",
        log: Callable[[str], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        prompt_timeout: float = PROMPT_TIMEOUT_SEC,
        result_timeout: float = RESULT_TIMEOUT_SEC,
        step_pause: float = STEP_PAUSE_SEC,
    ) -> None:
        self._prefix = prefix
        self._log = log or (lambda _t: None)
        self._sleep = sleep or asyncio.sleep
        self._prompt_timeout = prompt_timeout
        self._result_timeout = result_timeout
        self._pause = step_pause

    # ---- character -------------------------------------------------------

    async def give_character(
        self, giver: TransferParty, receiver: TransferParty, character: str
    ) -> TransferResult:
        name = " ".join(str(character or "").split())
        if not name:
            return TransferResult(False, KIND_CHARACTER, reason="no character named")
        async with prompt_guard(giver.actions), prompt_guard(receiver.actions):
            return await self._give_character(giver, receiver, name)

    async def _give_character(
        self, giver: TransferParty, receiver: TransferParty, name: str
    ) -> TransferResult:
        to = str(int(receiver.user_id))
        giver.actions.drain_queue()
        sent = await giver.actions.send_command(f"give {mention(to)} {name}", prefix=self._prefix)
        if sent is None:
            return TransferResult(False, KIND_CHARACTER, character=name, reason="send failed")

        prompt = await self._wait(
            giver,
            lambda p: p.kind == MessageKind.TRANSFER_PROMPT
            and p.fields.get("transfer") == KIND_CHARACTER
            and str(p.fields.get("recipient_id")) == to,
            self._prompt_timeout,
            sent,
        )
        if prompt is None:
            return TransferResult(
                False, KIND_CHARACTER, character=name, reason="no confirmation prompt"
            )
        named = str(prompt.fields.get("character") or "")
        from_name = str(prompt.fields.get("giver_name") or "")
        if _norm(named) != _norm(name) or (giver.names and not giver.is_named(from_name)):
            await self._sleep(self._pause)
            await receiver.actions.send_text("n")
            self._log(
                f"$give: Mudae asked about {named or '?'} from {from_name or '?'}, "
                f"not {name} — answered n"
            )
            return TransferResult(False, KIND_CHARACTER, character=name, reason="prompt mismatch")

        await self._sleep(self._pause)
        if await receiver.actions.send_text("y") is None:
            return TransferResult(False, KIND_CHARACTER, character=name, reason="could not send y")
        result = await self._wait(
            giver,
            lambda p: p.kind == MessageKind.TRANSFER_RESULT
            and p.fields.get("transfer") == KIND_CHARACTER
            and str(p.fields.get("recipient_id")) == to
            and _norm(p.fields.get("character")) == _norm(name),
            self._result_timeout,
            sent,
        )
        # The main's "y" was not one of its own commands: free the lane for it.
        _release(receiver.actions)
        if result is None:
            return TransferResult(
                False, KIND_CHARACTER, character=name, reason="no result after y", confirmed=True
            )
        self._log(f"$give: {name} given to the main")
        return TransferResult(True, KIND_CHARACTER, character=name, confirmed=True)

    # ---- kakera / spheres ------------------------------------------------

    async def give_amount(
        self, giver: TransferParty, receiver: TransferParty, kind: str, amount: int
    ) -> TransferResult:
        if kind not in _COMMANDS:
            raise ValueError(f"unknown transfer kind {kind!r}")
        amount = int(amount)
        if amount <= 0:
            return TransferResult(False, kind, amount=amount, reason="nothing to give")
        async with prompt_guard(giver.actions), prompt_guard(receiver.actions):
            return await self._give_amount(giver, receiver, kind, amount)

    async def _give_amount(
        self, giver: TransferParty, receiver: TransferParty, kind: str, amount: int
    ) -> TransferResult:
        command = _COMMANDS[kind]
        to = str(int(receiver.user_id))
        giver.actions.drain_queue()
        sent = await giver.actions.send_command(f"{command} {mention(to)} {amount}", prefix=self._prefix)
        if sent is None:
            return TransferResult(False, kind, amount=amount, reason="send failed")

        prompt = await self._wait(
            giver,
            lambda p: p.kind == MessageKind.TRANSFER_PROMPT
            and p.fields.get("transfer") == kind
            and (not giver.names or giver.is_named(str(p.fields.get("giver_name") or ""))),
            self._prompt_timeout,
            sent,
        )
        if prompt is None:
            return TransferResult(False, kind, amount=amount, reason="no confirmation prompt")
        asked = prompt.fields.get("amount")
        if asked != amount:
            await self._sleep(self._pause)
            await giver.actions.send_text("n")
            self._log(f"${command}: Mudae asked to give {asked}, expected {amount:,} — answered n")
            return TransferResult(False, kind, amount=amount, reason="prompt mismatch")

        await self._sleep(self._pause)
        if await giver.actions.send_text("y") is None:
            return TransferResult(False, kind, amount=amount, reason="could not send y")
        giver_id = str(int(giver.user_id))
        result = await self._wait(
            giver,
            lambda p: p.kind == MessageKind.TRANSFER_RESULT
            and p.fields.get("transfer") == kind
            and str(p.fields.get("giver_id")) == giver_id
            and str(p.fields.get("recipient_id")) == to
            and p.fields.get("amount") == amount,
            self._result_timeout,
            sent,
        )
        if result is None:
            return TransferResult(
                False, kind, amount=amount, reason="no result after y", confirmed=True
            )
        self._log(f"${command}: {amount:,} {kind} given to the main")
        return TransferResult(True, kind, amount=amount, confirmed=True)

    # ---- helpers ---------------------------------------------------------

    async def _wait(
        self,
        party: TransferParty,
        match: Callable[[Any], bool],
        timeout: float,
        after: Any = None,
    ) -> Any:
        """The first match newer than ``after`` (the command's message id).

        The same character goes back and forth on every force-divorce cycle,
        so an earlier exchange's prompt or result can still be queued.
        """
        floor = after if isinstance(after, int) and not isinstance(after, bool) else 0

        def newer(s: Any) -> bool:
            try:
                return int(getattr(s, "message_id", 0) or 0) > floor
            except (TypeError, ValueError):
                return True

        found = await party.actions.wait_for(lambda s, p: newer(s) and match(p), timeout=timeout)
        return found[1] if found else None


def _release(actions: Any) -> None:
    release = getattr(actions, "release_hold", None)
    if release is not None:
        release()
