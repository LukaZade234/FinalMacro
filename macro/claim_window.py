"""Claim-window timing from $tu (when to use the claim slot)."""

from __future__ import annotations


def is_final_roll_session_before_claim_reset(
    next_claim_reset_minutes: int | None,
    rolls_reset_minutes: int | None,
) -> bool:
    """
    True when the next roll reset aligns with the next claim reset (last roll hour
    of the current claim window).

    Example (3h claim / 1h rolls): claim_reset 60, rolls_reset 60 → True.
    claim_reset 180, rolls_reset 60 → False (rolls reset first — another roll hour
    before claim resets).
    """
    if next_claim_reset_minutes is None or rolls_reset_minutes is None:
        return False
    return next_claim_reset_minutes == rolls_reset_minutes
