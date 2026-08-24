"""Discord self-client: monitor one channel and capture all messages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import discord
from discord import Client as DiscordClient

from mudae.command_ack import message_has_mudae_command_ack, reaction_is_mudae_command_ack
from mudae.discord_errors import is_transient_discord_error
from mudae.claim_context import ClaimContextTracker
from mudae.command_context import CommandContextTracker
from mudae.parsers.embed import get_character_owner, is_character_embed, is_ownership_footer
from mudae.parsers.pipeline import format_entry_for_gui, parse_message
from mudae.serialization import snapshot_from_message
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

OnEntryCallback = Callable[[dict[str, Any]], None]
OnStatusCallback = Callable[[str], None]
OnParsedCallback = Callable[[MudaeMessageSnapshot, ParseResult], None]

# Keep only the most recent messages for button clicks; older ones can be
# re-fetched on demand. Prevents unbounded memory growth in long sessions.
_MESSAGE_CACHE_MAX = 300
_SEND_ATTEMPTS = 3
_SEND_RETRY_SEC = 2.0

class ChannelMonitor:
    """Connect with a user token and capture every message in a channel."""

    def __init__(
        self,
        token: str,
        channel_id: int,
        on_entry: OnEntryCallback | None = None,
        on_status: OnStatusCallback | None = None,
        on_parsed: OnParsedCallback | None = None,
    ) -> None:
        self.token = token.strip()
        self.channel_id = channel_id
        self.on_entry = on_entry
        self.on_status = on_status
        self.on_parsed = on_parsed
        self._client: DiscordClient | None = None
        self._ready = asyncio.Event()
        self._connected = False
        self._commands = CommandContextTracker()
        self._claims = ClaimContextTracker()
        self._messages: dict[int, discord.Message] = {}
        self._pending_macro_command: str | None = None
        self.macro_active = False
        self._connect_task: asyncio.Task[None] | None = None
        self._tick_waiters: dict[int, asyncio.Future[bool]] = {}

    async def start_background(self) -> bool:
        """Connect in a background task; return True when the gateway is ready."""
        if self._connect_task is not None and not self._connect_task.done():
            return await self.wait_ready(timeout=30.0)
        self._ready = asyncio.Event()
        self._connect_task = asyncio.create_task(self.connect(), name="discord-connect")
        return await self.wait_ready(timeout=30.0)

    async def stop_background(self) -> None:
        """Close the gateway and cancel the background connect task."""
        await self.disconnect()
        task = self._connect_task
        self._connect_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    @property
    def claims(self) -> ClaimContextTracker:
        return self._claims

    def get_own_usernames(self) -> list[str]:
        if not self._client or not self._client.user:
            return []
        user = self._client.user
        names: list[str] = []
        for attr in ("name", "global_name", "display_name"):
            value = getattr(user, attr, None)
            if value and str(value).strip():
                names.append(str(value).strip())
        return list(dict.fromkeys(names))

    def get_own_user_id(self) -> int | None:
        if not self._client or not self._client.user:
            return None
        return int(self._client.user.id)

    def _emit_status(self, text: str) -> None:
        if self.on_status:
            self.on_status(text)

    def _emit_entry(self, payload: dict[str, Any]) -> None:
        if self.on_entry:
            self.on_entry(payload)

    def _emit_parsed(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        if self.on_parsed:
            self.on_parsed(snapshot, parsed)

    async def send_command(self, command: str, *, prefix: str | None = None) -> int | None:
        cmd = command.strip().lstrip("$")
        pre = prefix if prefix is not None else "$"
        payload = f"{pre}{cmd}"
        last_exc: BaseException | None = None
        for attempt in range(1, _SEND_ATTEMPTS + 1):
            try:
                channel = await self._get_text_channel()
                self._pending_macro_command = cmd.lower()
                message = await channel.send(payload)
                self._remember_message(message)
                return int(message.id)
            except Exception as exc:
                last_exc = exc
                if not is_transient_discord_error(exc) or attempt >= _SEND_ATTEMPTS:
                    raise
                self._emit_status(
                    f"Send failed ({exc}) — retry {attempt}/{_SEND_ATTEMPTS - 1}"
                )
                await asyncio.sleep(_SEND_RETRY_SEC * attempt)
        if last_exc is not None:
            raise last_exc
        return None

    async def force_reconnect(self) -> bool:
        """Close the gateway (if any) and open a fresh Discord connection."""
        was_active = self.macro_active
        self._emit_status("Reconnecting to Discord…")
        try:
            await self.stop_background()
        except Exception:
            pass
        self._clear_channel_state()
        ready = await self.start_background()
        if was_active:
            self.macro_active = True
        if ready:
            self._emit_status("Reconnected")
        else:
            self._emit_status("Reconnect timed out")
        return ready

    async def switch_channel(self, channel_id: int) -> bool:
        """Point the monitor at another channel without dropping the gateway."""
        self.channel_id = int(channel_id)
        self._clear_channel_state()
        if self.is_connected:
            await self._emit_channel_status("Switched")
        return True

    async def reconnect(self, *, channel_id: int | None = None) -> bool:
        """Restart the gateway — used when the account token changes."""
        if channel_id is not None:
            self.channel_id = int(channel_id)
        self._clear_channel_state()
        try:
            await self.stop_background()
        except Exception:
            pass
        ready = await self.start_background()
        if ready:
            await self._emit_channel_status("Reconnected")
        else:
            self._emit_status("Reconnect timed out")
        return ready

    def _clear_channel_state(self) -> None:
        """Drop cached messages and in-flight waits for the previous channel."""
        self._messages.clear()
        for future in self._tick_waiters.values():
            if not future.done():
                future.set_result(False)
        self._tick_waiters.clear()
        self._pending_macro_command = None
        self._commands = CommandContextTracker()
        self._claims = ClaimContextTracker()
        self.macro_active = False

    async def _resolve_channel_label(self) -> str:
        if not self._client:
            return str(self.channel_id)
        channel_label = str(self.channel_id)
        try:
            ch = self._client.get_channel(self.channel_id)
            if ch is None:
                ch = await self._client.fetch_channel(self.channel_id)
            if hasattr(ch, "name"):
                channel_label = f"#{ch.name} ({self.channel_id})"
        except Exception as exc:
            channel_label = f"{self.channel_id} (could not resolve: {exc})"
        return channel_label

    async def _emit_channel_status(self, verb: str) -> None:
        user = self._client.user if self._client else None
        name = user.name if user else "?"
        label = await self._resolve_channel_label()
        self._emit_status(f"{verb} as {name} · monitoring {label}")

    def _remember_message(self, message: discord.Message) -> None:
        self._messages[message.id] = message
        if len(self._messages) > _MESSAGE_CACHE_MAX:
            # dicts preserve insertion order; drop the oldest entries.
            for stale_id in list(self._messages)[: len(self._messages) - _MESSAGE_CACHE_MAX]:
                del self._messages[stale_id]

        return None

    def _resolve_tick_waiter(self, message_id: int, *, acknowledged: bool) -> None:
        future = self._tick_waiters.pop(message_id, None)
        if future is not None and not future.done():
            future.set_result(acknowledged)

    async def wait_for_mudae_tick(
        self,
        message_id: int,
        *,
        timeout: float = 5.0,
    ) -> bool:
        """Wait until Mudae reacts with a tick on ``message_id``, or time out."""
        cached = self._messages.get(message_id)
        if cached is not None and await message_has_mudae_command_ack(cached):
            return True

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._tick_waiters[message_id] = future
        try:
            return bool(await asyncio.wait_for(future, timeout=max(0.0, timeout)))
        except asyncio.TimeoutError:
            try:
                channel = await self._get_text_channel()
                message = await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return False
            self._remember_message(message)
            return await message_has_mudae_command_ack(message)
        finally:
            self._tick_waiters.pop(message_id, None)

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        message = self._messages.get(message_id)
        if message is None:
            channel = await self._get_text_channel()
            try:
                message = await channel.fetch_message(message_id)
                self._remember_message(message)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return False
        for row in message.components or []:
            if not isinstance(row, discord.ActionRow):
                continue
            for child in row.children:
                if not isinstance(child, discord.Button):
                    continue
                if child.custom_id != custom_id:
                    continue
                try:
                    child.message = message
                    await child.click()
                    return True
                except Exception:
                    return False
        return False

    async def fetch_message_snapshot(self, message_id: int) -> MudaeMessageSnapshot | None:
        """Re-fetch a message from Discord (used when edits are slow to arrive)."""
        try:
            channel = await self._get_text_channel()
            message = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            message = self._messages.get(message_id)
            if message is None:
                return None
        else:
            self._remember_message(message)
        return snapshot_from_message(message, edited=True)

    async def _get_text_channel(self) -> discord.TextChannel:
        if not self._client:
            raise RuntimeError("Not connected")
        channel = self._client.get_channel(self.channel_id)
        if channel is None:
            channel = await self._client.fetch_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError(f"Channel {self.channel_id} is not a text channel")
        return channel

    async def _handle_message(self, message: discord.Message, *, edited: bool) -> None:
        if message.channel.id != self.channel_id:
            return
        self._remember_message(message)
        snapshot = snapshot_from_message(message, edited=edited)

        # Roll embed edits: only show when a claim message was seen and footer matches it.
        if snapshot.is_mudae and snapshot.edited and snapshot.embeds:
            embed = snapshot.embeds[0]
            if is_character_embed(embed):
                footer = embed.get("footer") or ""
                owner = get_character_owner(footer)
                if not owner or not is_ownership_footer(footer):
                    return
                confirmed = self._claims.try_confirm_embed(
                    snapshot.channel_id,
                    character_name=embed.get("author") or "",
                    owner=owner,
                )
                if confirmed is None:
                    return

        reply_to_command: str | None = None
        reply_part = 1
        reply_parts = 1
        if snapshot.is_mudae:
            if not snapshot.edited:
                if self._pending_macro_command:
                    reply_to_command = self._pending_macro_command
                    self._pending_macro_command = None
                elif not self.macro_active:
                    pending = self._commands.consume(snapshot.channel_id)
                    if pending is not None:
                        reply_to_command = pending.command
                        reply_part = pending.part
                        reply_parts = pending.parts
        elif not self.macro_active:
            self._commands.observe(snapshot)

        parsed = parse_message(
            snapshot,
            reply_to_command=reply_to_command,
            reply_part=reply_part,
            reply_parts=reply_parts,
        )
        if snapshot.is_mudae and not snapshot.edited:
            winner = parsed.fields.get("winner")
            character = parsed.fields.get("character")
            if parsed.kind in {MessageKind.CLAIM, MessageKind.MARRIAGE} and winner and character:
                self._claims.register(
                    snapshot.channel_id,
                    winner=str(winner),
                    character=str(character),
                )
        self._emit_parsed(snapshot, parsed)
        self._emit_entry(format_entry_for_gui(snapshot, parsed))

    async def _handle_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member) -> None:
        message = reaction.message
        if message.channel.id != self.channel_id:
            return
        if message.id not in self._tick_waiters:
            return
        if not reaction_is_mudae_command_ack(reaction, getattr(user, "id", None)):
            return
        self._resolve_tick_waiter(message.id, acknowledged=True)

    async def connect(self) -> None:
        discord_logger = logging.getLogger("discord")
        discord_logger.setLevel(logging.WARNING)

        self._client = DiscordClient(chunk_guilds_at_startup=False)

        @self._client.event
        async def on_ready() -> None:
            self._connected = True
            await self._emit_channel_status("Connected")
            self._ready.set()

        @self._client.event
        async def on_message(message: discord.Message) -> None:
            await self._handle_message(message, edited=False)

        @self._client.event
        async def on_message_edit(_before: discord.Message, after: discord.Message) -> None:
            await self._handle_message(after, edited=True)

        @self._client.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User | discord.Member) -> None:
            await self._handle_reaction_add(reaction, user)

        self._emit_status("Connecting…")
        await self._client.start(self.token)

    async def wait_ready(self, timeout: float = 30.0) -> bool:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def disconnect(self) -> None:
        self._connected = False
        self._ready.clear()
        if self._client:
            await self._client.close()
            self._client = None
        self._emit_status("Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected


# Backwards-compatible alias
MudaeReader = ChannelMonitor
