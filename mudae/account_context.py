"""Shared account resolution for persisted statistics logs."""

from __future__ import annotations

from typing import Any

# Display name when a log row has no account and no owner to copy.
UNKNOWN_ACCOUNT_NAME = "Unknown"
# Old app profile was named "Default" while the Discord account was already
# lukazade234; remap that placeholder to the current store name.
_LEGACY_PLACEHOLDER_NAMES = frozenset({"default"})


def account_map(accounts: list[Any]) -> dict[str, Any]:
    return {str(getattr(acc, "id", "")): acc for acc in accounts}


def main_account_defaults(
    accounts: list[Any],
    *,
    active_account_id: str = "",
) -> tuple[str, str]:
    """Prefer the GUI's active account, then the first Main, then the first account."""
    by_id = account_map(accounts)
    active_id = str(active_account_id or "").strip()
    if active_id and active_id in by_id:
        acc = by_id[active_id]
        return active_id, str(getattr(acc, "name", None) or UNKNOWN_ACCOUNT_NAME)

    for account in accounts:
        account_type = str(getattr(account, "type", "") or "").strip().lower()
        if account_type == "main":
            return str(account.id), str(getattr(account, "name", None) or UNKNOWN_ACCOUNT_NAME)

    if accounts:
        first = accounts[0]
        return str(first.id), str(getattr(first, "name", None) or UNKNOWN_ACCOUNT_NAME)

    return "", UNKNOWN_ACCOUNT_NAME


def defaults_from_store(accounts_store: Any) -> tuple[str, str, dict[str, Any]]:
    accounts = list(getattr(accounts_store, "accounts", []) or [])
    active_id = str(getattr(accounts_store, "active_account_id", "") or "")
    main_id, main_name = main_account_defaults(accounts, active_account_id=active_id)
    return main_id, main_name, account_map(accounts)


def resolve_log_account(
    entry: dict[str, Any],
    *,
    account_by_id: dict[str, Any],
    default_account_id: str,
    default_account_name: str,
) -> tuple[str, str, bool]:
    """Return ``(account_id, account_name, inferred)`` for a stored log row."""
    stored_id = str(entry.get("account_id") or "").strip()
    stored_name = str(entry.get("account_name") or "").strip()

    if stored_id and stored_id in account_by_id:
        acc = account_by_id[stored_id]
        name = stored_name or str(getattr(acc, "name", None) or UNKNOWN_ACCOUNT_NAME)
        if name.strip().lower() in _LEGACY_PLACEHOLDER_NAMES and default_account_name.strip().lower() not in _LEGACY_PLACEHOLDER_NAMES:
            return default_account_id, default_account_name, True
        return stored_id, name, False

    if stored_id:
        if stored_name.lower() in _LEGACY_PLACEHOLDER_NAMES and default_account_name:
            return default_account_id, default_account_name, True
        return stored_id, stored_name or UNKNOWN_ACCOUNT_NAME, False

    return default_account_id, stored_name or default_account_name, True
