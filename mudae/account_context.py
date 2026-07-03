"""Shared account resolution for persisted statistics logs."""

from __future__ import annotations

from typing import Any

# Primary Mudae account for legacy rows with no stored account context.
DEFAULT_ACCOUNT_NAME = "lukazade234"


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
        return active_id, str(getattr(acc, "name", None) or DEFAULT_ACCOUNT_NAME)

    for account in accounts:
        account_type = str(getattr(account, "type", "") or "").strip().lower()
        if account_type == "main":
            return str(account.id), str(getattr(account, "name", None) or DEFAULT_ACCOUNT_NAME)

    if accounts:
        first = accounts[0]
        return str(first.id), str(getattr(first, "name", None) or DEFAULT_ACCOUNT_NAME)

    return "", DEFAULT_ACCOUNT_NAME


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
        name = stored_name or str(getattr(acc, "name", None) or DEFAULT_ACCOUNT_NAME)
        if name.strip().lower() == "default" and default_account_name.strip().lower() != "default":
            return default_account_id, default_account_name, True
        return stored_id, name, False

    if stored_id:
        if stored_name.lower() == "default" and default_account_name:
            return default_account_id, default_account_name, True
        return stored_id, stored_name or "Unknown", False

    return default_account_id, stored_name or default_account_name, True
