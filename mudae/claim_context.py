"""Correlate claim text messages with roll embed ownership edits."""

from __future__ import annotations

from dataclasses import dataclass


def names_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left.strip().casefold() == right.strip().casefold()


@dataclass(frozen=True)
class PendingClaim:
    winner: str
    character: str


class ClaimContextTracker:
    """Remember the latest claim line per channel until an embed edit confirms it."""

    def __init__(self) -> None:
        self._pending: dict[int, PendingClaim] = {}

    def register(self, channel_id: int, *, winner: str, character: str) -> None:
        self._pending[channel_id] = PendingClaim(
            winner=winner.strip(),
            character=character.strip(),
        )

    def try_confirm_embed(
        self,
        channel_id: int,
        *,
        character_name: str,
        owner: str,
    ) -> PendingClaim | None:
        """Return and clear pending claim when embed matches winner + character."""
        pending = self._pending.get(channel_id)
        if pending is None:
            return None
        if not names_match(pending.character, character_name):
            return None
        if not names_match(pending.winner, owner):
            return None
        del self._pending[channel_id]
        return pending

    def clear(self, channel_id: int) -> None:
        self._pending.pop(channel_id, None)
