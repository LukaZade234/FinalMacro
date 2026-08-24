#!/usr/bin/env python3
"""One-off tool: connect as a configured account, send ``$settings``, extract
every ``$command`` referenced in it, then send each one bare (no arguments)
with a pause in between and record Mudae's raw reply.

This is NOT meant to be part of the app's runtime — it's a documentation
capture tool for the `$settings` parsing audit (see docs/TODO.md). Output is
a raw JSON capture (data/settings_commands_capture.json) that a follow-up
step turns into docs/archive/MUDAE_SETTINGS_COMMANDS.md.

Usage:
    .venv/bin/python scripts/document_settings_commands.py \\
        --account lukazade234 --server "Key Server 0"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import discord  # noqa: E402

from mudae.constants import MUDAE_BOT_IDS  # noqa: E402
from mudae.parsers.settings import _BULLET_RE, _CMD_SUFFIX_RE, _command_keys  # noqa: E402

SETTINGS_PATH = ROOT / "data" / "settings.json"
OUTPUT_PATH = ROOT / "data" / "settings_commands_capture.json"

SEND_PAUSE_SEC = 4.0
FIRST_REPLY_TIMEOUT_SEC = 15.0
EXTRA_MESSAGE_GRACE_SEC = 2.0


@dataclass
class PendingCommand:
    description: str
    keys: list[str]


@dataclass
class Capture:
    settings_raw: dict[str, Any] | None = None
    commands: list[dict[str, Any]] = field(default_factory=list)


def _load_target(account_name: str, server_name: str) -> tuple[str, int, str]:
    """Return (token, channel_id, channel_label) for the named account/server."""
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    token = ""
    for acc in data.get("accounts", []):
        if str(acc.get("name", "")).strip().lower() == account_name.strip().lower():
            token = str(acc.get("token", "")).strip()
            break
    if not token:
        raise SystemExit(f"Account {account_name!r} not found in {SETTINGS_PATH}")

    for server in data.get("servers", []):
        if str(server.get("name", "")).strip().lower() == server_name.strip().lower():
            channels = server.get("channels") or []
            if not channels:
                raise SystemExit(f"Server {server_name!r} has no channels configured")
            channel = channels[0]
            channel_id = int(channel["channel_id"])
            label = f"{server_name}#{channel.get('name', channel_id)}"
            return token, channel_id, label

    raise SystemExit(f"Server {server_name!r} not found in {SETTINGS_PATH}")


def _extract_commands(settings_text: str) -> list[PendingCommand]:
    """Reuse the app's own $settings bullet/command regex to list every command."""
    found: list[PendingCommand] = []
    seen_keys: set[str] = set()
    for match in _BULLET_RE.finditer(settings_text):
        line = match.group(1)
        cmd_match = _CMD_SUFFIX_RE.search(line)
        if not cmd_match:
            continue
        keys = _command_keys(cmd_match.group(1))
        if not keys:
            continue
        description = line[: cmd_match.start()].strip()
        new_keys = [k for k in keys if k not in seen_keys]
        if not new_keys:
            continue
        seen_keys.update(new_keys)
        found.append(PendingCommand(description=description, keys=new_keys))
    return found


def _message_to_dict(message: discord.Message) -> dict[str, Any]:
    return {
        "content": message.content or "",
        "embeds": [
            {
                "title": e.title or "",
                "description": e.description or "",
                "author": (e.author.name if e.author else "") or "",
                "footer": (e.footer.text if e.footer else "") or "",
                "fields": [{"name": f.name, "value": f.value} for f in (e.fields or [])],
            }
            for e in message.embeds
        ],
    }


class Runner:
    def __init__(self, token: str, channel_id: int, channel_label: str) -> None:
        self.token = token
        self.channel_id = channel_id
        self.channel_label = channel_label
        self.client = discord.Client(chunk_guilds_at_startup=False)
        self._channel: discord.TextChannel | None = None
        self._collecting = False
        self._collected: list[discord.Message] = []
        self._new_message_event = asyncio.Event()
        self.capture = Capture()

        @self.client.event
        async def on_ready() -> None:
            print(f"Connected as {self.client.user} -> monitoring {self.channel_label}", flush=True)

        @self.client.event
        async def on_message(message: discord.Message) -> None:
            if message.channel.id != self.channel_id:
                return
            if message.author.id not in MUDAE_BOT_IDS:
                return
            if not self._collecting:
                return
            self._collected.append(message)
            self._new_message_event.set()

    async def _get_channel(self) -> discord.TextChannel:
        if self._channel is None:
            channel = self.client.get_channel(self.channel_id)
            if channel is None:
                channel = await self.client.fetch_channel(self.channel_id)
            assert isinstance(channel, discord.TextChannel)
            self._channel = channel
        return self._channel

    async def send_and_capture(self, command: str) -> dict[str, Any]:
        channel = await self._get_channel()
        self._collected = []
        self._new_message_event = asyncio.Event()
        self._collecting = True
        await channel.send(command)

        try:
            await asyncio.wait_for(self._new_message_event.wait(), timeout=FIRST_REPLY_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            self._collecting = False
            return {"sent_as": command, "no_reply": True, "messages": []}

        # Grab any follow-up messages Mudae sends right after the first one.
        while True:
            self._new_message_event = asyncio.Event()
            try:
                await asyncio.wait_for(self._new_message_event.wait(), timeout=EXTRA_MESSAGE_GRACE_SEC)
            except asyncio.TimeoutError:
                break

        self._collecting = False
        return {
            "sent_as": command,
            "no_reply": False,
            "messages": [_message_to_dict(m) for m in self._collected],
        }

    async def run(self) -> None:
        await self.client.wait_until_ready()
        await asyncio.sleep(1.0)

        print("Sending $settings ...", flush=True)
        settings_reply = await self.send_and_capture("$settings")
        self.capture.settings_raw = settings_reply
        if settings_reply["no_reply"]:
            raise SystemExit("No reply received for $settings — aborting.")

        settings_text = "\n".join(
            m["content"] + "\n" + "\n".join(e["description"] for e in m["embeds"])
            for m in settings_reply["messages"]
        )
        pending = _extract_commands(settings_text)
        print(f"Extracted {sum(len(p.keys) for p in pending)} command(s) from $settings.", flush=True)

        for item in pending:
            for key in item.keys:
                command = f"${key}"
                print(f"Sending {command} ...", flush=True)
                reply = await self.send_and_capture(command)
                reply["description"] = item.description
                self.capture.commands.append(reply)
                if reply["no_reply"]:
                    print(f"  -> no reply within {FIRST_REPLY_TIMEOUT_SEC}s", flush=True)
                await asyncio.sleep(SEND_PAUSE_SEC)

        OUTPUT_PATH.write_text(
            json.dumps(
                {
                    "settings_raw": self.capture.settings_raw,
                    "commands": self.capture.commands,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Saved capture to {OUTPUT_PATH}", flush=True)

        await self.client.close()


async def _main(account: str, server: str) -> None:
    token, channel_id, label = _load_target(account, server)
    runner = Runner(token, channel_id, label)
    connect_task = asyncio.create_task(runner.client.start(token))
    run_task = asyncio.create_task(runner.run())
    done, pending = await asyncio.wait({connect_task, run_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc:
            raise exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="lukazade234")
    parser.add_argument("--server", default="Key Server 0")
    args = parser.parse_args()
    asyncio.run(_main(args.account, args.server))


if __name__ == "__main__":
    main()
