"""Shared helpers for ``$oh`` / ``$oc`` / ``$oq`` minigame commands."""

from __future__ import annotations

# Mudae rejects multipliers above this; spend the rest in a follow-up game.
MAX_MINIGAME_USES = 10


def minigame_command(name: str, uses: int = 1) -> str:
    """Build ``oh`` / ``oh 7`` style command text (no prefix)."""
    uses = max(1, min(MAX_MINIGAME_USES, int(uses)))
    return name if uses <= 1 else f"{name} {uses}"


def minigame_use_batches(total: int, *, max_uses: int = MAX_MINIGAME_USES) -> list[int]:
    """Split ``total`` uses into chunks of at most ``max_uses`` (e.g. 11 → [10, 1])."""
    remaining = max(0, int(total))
    if remaining <= 0:
        return []
    cap = max(1, int(max_uses))
    batches: list[int] = []
    while remaining > 0:
        chunk = min(remaining, cap)
        batches.append(chunk)
        remaining -= chunk
    return batches
