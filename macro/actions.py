"""Discord actions and Mudae message waiting for the macro."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_ROLL_KINDS = frozenset(
    {
        MessageKind.ROLL,
        MessageKind.CHARACTER_EMBED,
        MessageKind.KAKERA_BUTTONS,
        MessageKind.CLAIM_BUTTONS,
        MessageKind.COMMAND_RESPONSE,
    }
)


def is_roll_parse_result(parsed: ParseResult, *, roll_command: str) -> bool:
    if parsed.kind in {
        MessageKind.TU,
        MessageKind.KAKERA_CLAIM,
        MessageKind.KAKERA_REACT_DENIED,
        MessageKind.DK_CLAIM,
        MessageKind.SPHERE_CLICK,
        MessageKind.CLAIM,
        MessageKind.MARRIAGE,
        MessageKind.CLAIM_INTERVAL,
    }:
        return False
    if parsed.kind in {
        MessageKind.CHARACTER_EMBED,
        MessageKind.KAKERA_BUTTONS,
        MessageKind.CLAIM_BUTTONS,
    }:
        return parsed.fields.get("character_name") is not None
    if parsed.kind == MessageKind.ROLL:
        return True
    if parsed.kind == MessageKind.COMMAND_RESPONSE:
        parser = (parsed.fields.get("parser_command") or "").lower()
        display = (parsed.fields.get("command") or "").lower()
        canonical = roll_command.lower()
        return parser == "roll" or display == canonical or canonical in display
    return False


def is_perk6_spawn_parse_result(
    parsed: ParseResult,
    *,
    parent_character: str,
) -> bool:
    """True for the perk-6 follow-up embed spawned by ``parent_character``."""
    from mudae.parsers.roll import perk6_spawner_matches

    if parsed.kind not in {
        MessageKind.ROLL,
        MessageKind.CHARACTER_EMBED,
        MessageKind.KAKERA_BUTTONS,
        MessageKind.CLAIM_BUTTONS,
    }:
        return False
    if not parsed.fields.get("perk_6"):
        return False
    return perk6_spawner_matches(parsed.fields.get("spawned_by"), parent_character)


def is_tu_parse_result(parsed: ParseResult) -> bool:
    if parsed.kind == MessageKind.TU:
        return True
    if parsed.kind == MessageKind.COMMAND_RESPONSE:
        cmd = (parsed.fields.get("parser_command") or parsed.fields.get("command") or "").lower()
        return cmd in {"tu", "ku"}
    return False


_DK_SETTLE_SEC = 2.5


def is_dk_use_parse_result(snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> bool:
    if parsed.kind == MessageKind.DK_CLAIM:
        return True
    if parsed.kind == MessageKind.TU:
        content = getattr(snapshot, "content", "") or ""
        from mudae.parsers.dk import is_dk_claim

        return is_dk_claim(content)
    return False


from mudae.parsers.ohu8 import is_ohu8_response


def is_ohu8_parse_result(parsed: ParseResult) -> bool:
    if parsed.kind == MessageKind.COMMAND_RESPONSE:
        cmd = (
            parsed.fields.get("parser_command")
            or parsed.fields.get("command")
            or ""
        ).lower()
        if cmd == "ohu8":
            return True
    content = parsed.fields.get("content") or parsed.summary or ""
    return is_ohu8_response(content)


# Cap on buffered Mudae messages. The queue is only consumed while the macro
# waits for replies; while idle/sleeping every channel message would otherwise
# accumulate without bound. Old entries are dropped first (stale messages are
# useless to the macro anyway — it drains before each command).
_MAX_QUEUE_SIZE = 512


class DiscordActions:
    """Send commands and wait for parsed Mudae replies on a shared monitor."""

    def __init__(self, monitor: Any) -> None:
        self._monitor = monitor
        self._queue: asyncio.Queue[tuple[MudaeMessageSnapshot, ParseResult]] = asyncio.Queue()

    def feed(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        if not snapshot.is_mudae:
            return
        while self._queue.qsize() >= _MAX_QUEUE_SIZE:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._queue.put_nowait((snapshot, parsed))

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        await self._monitor.send_command(command, prefix=prefix)

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        return await self._monitor.click_button(message_id, custom_id)

    async def wait_for(
        self,
        predicate: Callable[[MudaeMessageSnapshot, ParseResult], bool],
        *,
        timeout: float = 15.0,
    ) -> tuple[MudaeMessageSnapshot, ParseResult] | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        deferred: list[tuple[MudaeMessageSnapshot, ParseResult]] = []
        try:
            while loop.time() < deadline:
                remaining = deadline - loop.time()
                try:
                    snapshot, parsed = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=min(remaining, 0.25),
                    )
                except asyncio.TimeoutError:
                    continue
                if predicate(snapshot, parsed):
                    return snapshot, parsed
                deferred.append((snapshot, parsed))
            return None
        finally:
            # Re-queue skipped messages exactly once so later waits can still
            # match them (the finally also covers the successful return above).
            for item in deferred:
                self._queue.put_nowait(item)

    async def wait_for_tu(self, *, timeout: float = 12.0) -> ParseResult | None:
        result = await self.wait_for(
            lambda _s, p: is_tu_parse_result(p),
            timeout=timeout,
        )
        return result[1] if result else None

    async def wait_for_ohu8(self, *, timeout: float = 12.0) -> ParseResult | None:
        result = await self.wait_for(
            lambda snapshot, parsed: is_ohu8_parse_result(parsed)
            or is_ohu8_response(getattr(snapshot, "content", "") or ""),
            timeout=timeout,
        )
        return result[1] if result else None

    async def wait_for_roll(
        self,
        *,
        roll_command: str,
        timeout: float = 20.0,
    ) -> tuple[MudaeMessageSnapshot, ParseResult] | None:
        return await self.wait_for(
            lambda s, p: not s.edited and is_roll_parse_result(p, roll_command=roll_command),
            timeout=timeout,
        )

    async def wait_for_perk6_spawn(
        self,
        *,
        parent_character: str,
        timeout: float = 0.8,
    ) -> tuple[MudaeMessageSnapshot, ParseResult] | None:
        """Wait for a perk-6 spawn embed whose ``[SPAWNED BY …]`` matches ``parent_character``."""
        return await self.wait_for(
            lambda s, p: (
                not s.edited
                and is_perk6_spawn_parse_result(
                    p,
                    parent_character=parent_character,
                )
            ),
            timeout=timeout,
        )

    async def wait_for_kind(
        self,
        kind: MessageKind,
        *,
        timeout: float = 10.0,
    ) -> tuple[MudaeMessageSnapshot, ParseResult] | None:
        return await self.wait_for(
            lambda _s, p: p.kind == kind,
            timeout=timeout,
        )

    async def wait_for_claim(
        self,
        *,
        timeout: float = 8.0,
    ) -> ParseResult | None:
        result = await self.wait_for(
            lambda _s, p: p.kind in {MessageKind.CLAIM, MessageKind.MARRIAGE},
            timeout=timeout,
        )
        return result[1] if result else None

    async def wait_for_kakera_claim(
        self,
        *,
        timeout: float = 8.0,
    ) -> ParseResult | None:
        result = await self.wait_for(
            lambda _s, p: p.kind == MessageKind.KAKERA_CLAIM,
            timeout=timeout,
        )
        return result[1] if result else None

    async def wait_for_kakera_outcome(
        self,
        *,
        timeout: float = 8.0,
    ) -> ParseResult | None:
        """Wait for a successful kakera claim or an insufficient-power denial."""
        result = await self.wait_for(
            lambda _s, p: p.kind
            in {MessageKind.KAKERA_CLAIM, MessageKind.KAKERA_REACT_DENIED},
            timeout=timeout,
        )
        return result[1] if result else None

    async def wait_for_dk_use(self, *, timeout: float = 12.0) -> ParseResult | None:
        result = await self.wait_for(is_dk_use_parse_result, timeout=timeout)
        return result[1] if result else None

    def drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
