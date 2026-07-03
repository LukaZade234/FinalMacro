"""Shared account resolution for statistics logs."""

from __future__ import annotations

from dataclasses import dataclass

from gui.accounts import AccountProfile
from mudae.account_context import (
    main_account_defaults,
    resolve_log_account,
)


@dataclass
class _FakeStore:
    accounts: list[AccountProfile]
    active_account_id: str = ""


def test_main_account_defaults_prefers_active_account():
    store = _FakeStore(
        accounts=[
            AccountProfile(id="default", name="Default", type="Main"),
            AccountProfile(id="active", name="lukazade234", type="Main"),
        ],
        active_account_id="active",
    )
    assert main_account_defaults(store.accounts, active_account_id=store.active_account_id) == (
        "active",
        "lukazade234",
    )


def test_resolve_log_account_remaps_legacy_default_name():
    by_id = {
        "default": AccountProfile(id="default", name="Default", type="Main"),
        "active": AccountProfile(id="active", name="lukazade234", type="Main"),
    }
    acc_id, acc_name, inferred = resolve_log_account(
        {"account_id": "default", "account_name": "Default"},
        account_by_id=by_id,
        default_account_id="active",
        default_account_name="lukazade234",
    )
    assert acc_id == "active"
    assert acc_name == "lukazade234"
    assert inferred is True
