"""Track user $commands and label the next Mudae reply."""

from __future__ import annotations

import re
from dataclasses import dataclass

from mudae.types import MudaeMessageSnapshot

_COMMAND_RE = re.compile(r"^\$([a-zA-Z][a-zA-Z0-9]*)")

# Canonical parser id -> how many Mudae messages follow the command.
MULTI_PART_COMMANDS: dict[str, int] = {
    "bonus": 2,
    # Rolls are one embed; ownership arrives via footer on the same message or an edit.
}


@dataclass(frozen=True)
class PendingReply:
    """User command waiting for a Mudae response."""

    command: str
    part: int
    parts: int

    @property
    def is_multipart(self) -> bool:
        return self.parts > 1


def extract_command(content: str) -> str | None:
    """Return command name without '$' (e.g. 'tu' from '$tu')."""
    match = _COMMAND_RE.match((content or "").strip())
    return match.group(1).lower() if match else None


def response_label(command: str, *, part: int = 1, parts: int = 1) -> str:
    base = f"${command} response"
    if parts > 1:
        return f"{base} ({part}/{parts})"
    return base


class CommandContextTracker:
    """Remember the last $command per channel; attach it to the next Mudae message(s)."""

    def __init__(self) -> None:
        self._states: dict[int, _ChannelCommandState] = {}

    def observe(self, snapshot: MudaeMessageSnapshot) -> None:
        if snapshot.is_mudae:
            return
        command = extract_command(snapshot.content)
        if not command:
            return
        from mudae.commands import normalize_command

        canonical = normalize_command(command)
        parts = MULTI_PART_COMMANDS.get(canonical, 1)
        self._states[snapshot.channel_id] = _ChannelCommandState(
            command=command,
            parts_total=parts,
            parts_consumed=0,
        )

    def consume(self, channel_id: int) -> PendingReply | None:
        state = self._states.get(channel_id)
        if state is None:
            return None
        state.parts_consumed += 1
        part = state.parts_consumed
        if state.parts_consumed >= state.parts_total:
            del self._states[channel_id]
        return PendingReply(
            command=state.command,
            part=part,
            parts=state.parts_total,
        )


@dataclass
class _ChannelCommandState:
    command: str
    parts_total: int
    parts_consumed: int
