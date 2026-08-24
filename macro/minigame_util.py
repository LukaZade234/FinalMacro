"""Shared helpers for ``$oh`` / ``$oc`` / ``$oq`` minigame commands."""

from __future__ import annotations

from typing import Any

from mudae.parsers.minigame_exhausted import (
    format_exhausted_activity,
    is_minigame_exhausted_message,
    parse_minigame_exhausted,
)

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


def snapshot_is_minigame_exhausted(snapshot: Any) -> bool:
    return is_minigame_exhausted_message(getattr(snapshot, "content", "") or "")


def exhausted_fields_from_snapshot(snapshot: Any) -> dict[str, Any] | None:
    content = getattr(snapshot, "content", "") or ""
    if not is_minigame_exhausted_message(content):
        return None
    return dict(parse_minigame_exhausted(content).fields)


async def wait_for_grid_or_exhausted(
    actions: Any,
    predicate: Any,
    *,
    timeout: float,
) -> tuple[Any | None, dict[str, Any] | None]:
    """Wait for a minigame grid or Mudae's daily-uses-exhausted reply."""
    result = await actions.wait_for(predicate, timeout=timeout)
    if not result:
        return None, None
    snapshot = result[0]
    fields = exhausted_fields_from_snapshot(snapshot)
    if fields is not None:
        return None, fields
    return snapshot, None


def empty_minigame_result(
    reason: str,
    *,
    extra: dict[str, Any] | None = None,
    exhausted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "clicks": 0,
        "reward": 0,
        "reason": reason,
    }
    if extra:
        result.update(extra)
    if exhausted:
        result["game"] = exhausted.get("game")
        result["refill_minutes"] = exhausted.get("refill_minutes")
        result["reason"] = "exhausted"
    return result


def log_minigame_exhausted(log: Any, fields: dict[str, Any]) -> None:
    log(format_exhausted_activity(fields))
