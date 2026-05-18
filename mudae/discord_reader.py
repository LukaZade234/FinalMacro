"""Discord self-client: monitor one channel and capture all messages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import discord
from discord import Client as DiscordClient

from mudae.command_context import CommandContextTracker
from mudae.parsers.embed import is_character_embed
from mudae.parsers.pipeline import format_entry_for_gui, parse_message
from mudae.serialization import snapshot_from_message

OnEntryCallback = Callable[[dict[str, Any]], None]
OnStatusCallback = Callable[[str], None]


class ChannelMonitor:
    """Connect with a user token and capture every message in a channel."""

    def __init__(
        self,
        token: str,
        channel_id: int,
        on_entry: OnEntryCallback | None = None,
        on_status: OnStatusCallback | None = None,
    ) -> None:
        self.token = token.strip()
        self.channel_id = channel_id
        self.on_entry = on_entry
        self.on_status = on_status
        self._client: DiscordClient | None = None
        self._ready = asyncio.Event()
        self._connected = False
        self._commands = CommandContextTracker()

    def _emit_status(self, text: str) -> None:
        if self.on_status:
            self.on_status(text)

    def _emit_entry(self, payload: dict[str, Any]) -> None:
        if self.on_entry:
            self.on_entry(payload)

    async def _handle_message(self, message: discord.Message, *, edited: bool) -> None:
        if message.channel.id != self.channel_id:
            return
        snapshot = snapshot_from_message(message, edited=edited)

        # Mudae often edits the roll embed (footer, key icon). Already shown on first message.
        if (
            snapshot.is_mudae
            and snapshot.edited
            and snapshot.embeds
            and is_character_embed(snapshot.embeds[0])
        ):
            return

        reply_to_command: str | None = None
        reply_part = 1
        reply_parts = 1
        if snapshot.is_mudae:
            # Edits (e.g. footer → Belongs to …) are not a second command reply.
            if not snapshot.edited:
                pending = self._commands.consume(snapshot.channel_id)
                if pending is not None:
                    reply_to_command = pending.command
                    reply_part = pending.part
                    reply_parts = pending.parts
        else:
            self._commands.observe(snapshot)
        parsed = parse_message(
            snapshot,
            reply_to_command=reply_to_command,
            reply_part=reply_part,
            reply_parts=reply_parts,
        )
        self._emit_entry(format_entry_for_gui(snapshot, parsed))

    async def connect(self) -> None:
        discord_logger = logging.getLogger("discord")
        discord_logger.setLevel(logging.WARNING)

        # discord.py-self has no Intents API (unlike discord.py bot library).
        self._client = DiscordClient(chunk_guilds_at_startup=False)

        @self._client.event
        async def on_ready() -> None:
            user = self._client.user
            name = user.name if user else "?"
            self._connected = True
            channel_label = str(self.channel_id)
            try:
                ch = self._client.get_channel(self.channel_id)
                if ch is None:
                    ch = await self._client.fetch_channel(self.channel_id)
                if hasattr(ch, "name"):
                    channel_label = f"#{ch.name} ({self.channel_id})"
            except Exception as exc:
                channel_label = f"{self.channel_id} (could not resolve: {exc})"
            self._emit_status(f"Connected as {name} · monitoring {channel_label}")
            self._ready.set()

        @self._client.event
        async def on_message(message: discord.Message) -> None:
            await self._handle_message(message, edited=False)

        @self._client.event
        async def on_message_edit(_before: discord.Message, after: discord.Message) -> None:
            await self._handle_message(after, edited=True)

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
        if self._client:
            await self._client.close()
            self._client = None
        self._emit_status("Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected


# Backwards-compatible alias
MudaeReader = ChannelMonitor
