"""Account-scoped daily/cooldown persistence on a channel profile.

Channel profiles store::

    daily_resets: {
        "<account_id>": { "perk8": { ... } },
        ...
    }

Legacy flat blobs (``{"perk8": ...}`` at the channel root) are ignored so
account-specific state is never shared accidentally.
"""

from __future__ import annotations

from typing import Any

from macro.perk8_daily import PERK8_DAILY_KEY

# Keys that belong inside an account slice, not at the channel root.
_ACCOUNT_SLICE_KEYS = frozenset({PERK8_DAILY_KEY, "macro_runtime"})


def is_legacy_flat_daily_store(channel_daily: dict[str, Any] | None) -> bool:
    """True when ``daily_resets`` uses the old channel-only layout."""
    if not channel_daily:
        return False
    return any(key in _ACCOUNT_SLICE_KEYS for key in channel_daily)


def get_account_daily_slice(
    channel_daily: dict[str, Any] | None,
    account_id: str,
) -> dict[str, Any]:
    """Return one account's daily blob for a channel (may be empty)."""
    if not account_id or not channel_daily:
        return {}
    raw = channel_daily.get(account_id)
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def set_account_daily_slice(
    channel_daily: dict[str, Any] | None,
    account_id: str,
    account_daily: dict[str, Any],
) -> dict[str, Any]:
    """Merge ``account_daily`` into the channel blob and drop legacy root keys."""
    out: dict[str, Any] = {}
    if channel_daily:
        for key, value in channel_daily.items():
            if key in _ACCOUNT_SLICE_KEYS:
                continue
            if isinstance(value, dict):
                out[key] = dict(value)
    if account_id:
        out[account_id] = dict(account_daily)
    return out
