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


def is_tu_parse_result(parsed: ParseResult) -> bool:
    if parsed.kind == MessageKind.TU:
        return True
    if parsed.kind == MessageKind.COMMAND_RESPONSE:
        cmd = (parsed.fields.get("parser_command") or parsed.fields.get("command") or "").lower()
        return cmd == "tu"
    return False


class DiscordActions:
    """Send commands and wait for parsed Mudae replies on a shared monitor."""

    def __init__(self, monitor: Any) -> None:
        self._monitor = monitor
        self._queue: asyncio.Queue[tuple[MudaeMessageSnapshot, ParseResult]] = asyncio.Queue()

    def feed(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        if not snapshot.is_mudae:
            return
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
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            try:
                snapshot, parsed = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=min(remaining, 1.0),
                )
            except asyncio.TimeoutError:
                continue
            if predicate(snapshot, parsed):
                return snapshot, parsed
        return None

    async def wait_for_tu(self, *, timeout: float = 12.0) -> ParseResult | None:
        result = await self.wait_for(
            lambda _s, p: is_tu_parse_result(p),
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

    def drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
