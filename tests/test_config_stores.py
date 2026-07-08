"""Accounts, presets, targets, and run resolution."""

from gui.accounts import AccountStore
from gui.presets import PresetStore
from gui.run_target import resolve_run_target
from gui.server_profiles import ServerProfileStore
from gui.targets import TargetStore
from macro.config import MacroConfig


def test_legacy_token_and_macro_migration() -> None:
    accounts = AccountStore()
    presets = PresetStore()
    accounts.load_from_settings({"token": "tok123", "accounts": []})
    presets.load_from_settings({
        "macro": {"roll_command": "wg"},
        "presets": {},
    })
    assert accounts.active_token() == "tok123"
    assert presets.presets["default"].roll_command == "wg"


def test_resolve_run_target() -> None:
    accounts = AccountStore()
    presets = PresetStore()
    profiles = ServerProfileStore()
    targets = TargetStore()

    acc_id = accounts.add_account("main", token="token", account_type="Main")
    presets.presets["aggressive"] = MacroConfig(roll_command="wa")
    presets.set_active("aggressive")
    srv_id = profiles.add_server("Guild")
    ch_id = profiles.add_channel(srv_id, "mudae", "999")
    profiles.set_active(srv_id, ch_id or "")
    targets.ensure_target(acc_id, ch_id or "", "aggressive")

    resolved = resolve_run_target(accounts, profiles, presets, targets)
    assert resolved is not None
    assert resolved.token == "token"
    assert resolved.discord_channel_id == "999"
    assert resolved.macro_config.roll_command == "wa"
    assert resolved.preset_id == "aggressive"
