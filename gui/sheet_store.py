"""Account-scoped ``$bonus`` / ``$shop`` sheets on a channel profile.

Channel profiles store::

    bonus_by_account: {
        "<account_id>": {"fields": {...}, "summary": "...", "read_at": "<iso>"},
        ...
    }
    shop_by_account: { ... same shape ... }

``$settings`` deliberately stays flat on the channel: it is the *server's* rule
sheet and reads the same whoever fetched it. The other two are not. ``$bonus``
mixes server settings with the connected account's own perks, and ``$shop`` is
that account's ouroperk sheet — ``docs/MUDAE_LOGIC.md`` says so and then says it
is "stored on the channel profile like ``$bonus``", which is the bug: with
several accounts on one channel, whichever fetched last won, and
:func:`macro.sheet_caps.apply_sheet_caps` then fed the *wrong* account's
``power_max_percent`` / ``perk9_click_max`` / ``perk9_sphere_value_pct`` into
``AccountState`` — the values the perk-8 reserve and the perk-9 EV bar run on.

This is the same shape :mod:`macro.daily_store` already uses for
``daily_resets`` one field below, for the same reason.

A sheet written before the split carries no account. Rather than silently credit
it to whoever happens to be connected now, it is read back **only for the main
account** and flagged ``inferred`` — the treatment
:func:`mudae.account_context.resolve_log_account` already gives pre-account log
rows. Every other account starts empty, which is honest: we do not know their
sheets. The first real fetch per account replaces the guess, and writing an
account sheet drops the legacy blob so it cannot be inferred twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mudae.clock import utc_now

# ``$settings`` is not here on purpose — see the module docstring.
ACCOUNT_SHEET_KINDS = ("bonus", "shop")


def by_account_field(kind: str) -> str:
    """``"bonus"`` -> ``"bonus_by_account"``, the ChannelProfile attribute name."""
    return f"{kind}_by_account"


@dataclass
class SheetRead:
    """One account's view of a stored sheet, with why we believe it."""

    fields: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    read_at: str = ""
    inferred: bool = False

    @property
    def present(self) -> bool:
        return bool(self.fields)


def _entry(raw: Any) -> dict[str, Any] | None:
    """Normalise one stored ``{account_id: entry}`` value."""
    if not isinstance(raw, dict):
        return None
    fields = raw.get("fields")
    if not isinstance(fields, dict):
        return None
    return {
        "fields": dict(fields),
        "summary": str(raw.get("summary") or ""),
        "read_at": str(raw.get("read_at") or ""),
    }


def clean_by_account(raw: Any) -> dict[str, dict[str, Any]]:
    """Load a persisted ``*_by_account`` map, dropping anything malformed."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for account_id, value in raw.items():
        key = str(account_id or "").strip()
        if not key:
            continue
        entry = _entry(value)
        if entry is not None:
            out[key] = entry
    return out


def read_sheet(
    by_account: dict[str, Any] | None,
    *,
    account_id: str,
    legacy_fields: dict[str, Any] | None = None,
    legacy_summary: str = "",
    main_account_id: str = "",
) -> SheetRead:
    """Return ``account_id``'s sheet, falling back to a pre-split blob.

    The fallback applies to the main account only. Handing the same unattributed
    sheet to every account is exactly the leak this module exists to close.
    """
    account_id = str(account_id or "").strip()
    if account_id:
        entry = _entry((by_account or {}).get(account_id))
        if entry is not None:
            return SheetRead(
                fields=entry["fields"],
                summary=entry["summary"],
                read_at=entry["read_at"],
            )

    legacy = dict(legacy_fields or {})
    main_id = str(main_account_id or "").strip()
    if legacy and account_id and main_id and account_id == main_id:
        return SheetRead(fields=legacy, summary=str(legacy_summary or ""), inferred=True)
    return SheetRead()


def write_sheet(
    by_account: dict[str, Any] | None,
    *,
    account_id: str,
    fields: dict[str, Any],
    summary: str = "",
    read_at: str = "",
) -> dict[str, dict[str, Any]]:
    """Return a new map with ``account_id``'s sheet replaced.

    Other accounts' sheets are carried through untouched — that is the whole
    point. A blank ``account_id`` is a no-op rather than a shared write.
    """
    out = clean_by_account(by_account)
    account_id = str(account_id or "").strip()
    if not account_id:
        return out
    out[account_id] = {
        "fields": dict(fields or {}),
        "summary": str(summary or ""),
        "read_at": str(read_at or "") or utc_now().isoformat(),
    }
    return out


def known_account_ids(by_account: dict[str, Any] | None) -> list[str]:
    """Accounts that have a stored sheet, for "who has been read here" displays."""
    return sorted(clean_by_account(by_account))
