"""Import MudaeBot Account_info.json + presets.json (MacroConfig fields only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gui.accounts import AccountStore
from gui.presets import PresetStore
from gui.server_profiles import ServerProfileStore
from gui.targets import TargetStore
from macro.config import MacroConfig

_LEGACY_ROOT = Path(__file__).resolve().parent.parent / "MudaeBot---Copy"
_ACCOUNT_PATH = _LEGACY_ROOT / "Account_info.json"
_PRESETS_PATH = _LEGACY_ROOT / "presets.json"

_MACRO_FIELD_MAP = {
    "roll_command": "roll_command",
    "mudae_prefix": "prefix",
    "roll_speed": "roll_delay_sec",
}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:48] or "preset"


def _macro_from_legacy_preset(data: dict[str, Any]) -> MacroConfig:
    mapped: dict[str, Any] = {}
    for old_key, new_key in _MACRO_FIELD_MAP.items():
        if old_key in data:
            mapped[new_key] = data[old_key]
    if "prefix" not in mapped and "prefix" in data:
        mapped["prefix"] = data["prefix"]
    return MacroConfig.from_dict(mapped)


def import_legacy_config(
    accounts: AccountStore,
    profiles: ServerProfileStore,
    presets: PresetStore,
    targets: TargetStore,
) -> str:
    if not _ACCOUNT_PATH.is_file():
        return f"Legacy Account_info.json not found at {_ACCOUNT_PATH}"

    account_info = json.loads(_ACCOUNT_PATH.read_text(encoding="utf-8"))
    legacy_presets: dict[str, Any] = {}
    if _PRESETS_PATH.is_file():
        legacy_presets = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))

    channel_map: dict[str, int] = dict(account_info.get("channels") or {})
    snowflake_to_profile: dict[str, str] = {}

    for friendly, snowflake in channel_map.items():
        snowflake_str = str(snowflake)
        found = profiles.find_channel_by_discord_id(snowflake_str)
        if found:
            _, channel = found
            snowflake_to_profile[friendly] = channel.id
            continue
        server = profiles.servers[0] if profiles.servers else None
        if server is None:
            server_id = profiles.add_server("Imported")
            server = profiles.find_server(server_id)
        if not server:
            continue
        channel_id = profiles.add_channel(server.id, friendly, snowflake_str)
        if channel_id:
            snowflake_to_profile[friendly] = channel_id

    imported_presets = 0
    for name, data in legacy_presets.items():
        if not isinstance(data, dict):
            continue
        preset_id = _slugify(name)
        if preset_id not in presets.presets:
            presets.presets[preset_id] = _macro_from_legacy_preset(data)
            imported_presets += 1

    imported_accounts = 0
    imported_targets = 0
    tokens = account_info.get("tokens") or {}
    for acc_name, acc_data in tokens.items():
        if not isinstance(acc_data, dict):
            continue
        existing = next((a for a in accounts.accounts if a.name == acc_name), None)
        if existing:
            account_id = existing.id
            existing.token = str(acc_data.get("token") or existing.token)
            existing.type = str(acc_data.get("type") or existing.type)
        else:
            account_id = accounts.add_account(
                acc_name,
                token=str(acc_data.get("token") or ""),
                account_type=str(acc_data.get("type") or "Main"),
            )
            imported_accounts += 1

        default_preset_name = str(acc_data.get("default_preset") or presets.default_preset_id)
        default_preset_id = _slugify(default_preset_name)
        if default_preset_id not in presets.presets:
            legacy = legacy_presets.get(default_preset_name)
            if isinstance(legacy, dict):
                presets.presets[default_preset_id] = _macro_from_legacy_preset(legacy)
            else:
                presets.presets[default_preset_id] = MacroConfig()

        enabled: list[str] = []
        channel_presets = acc_data.get("channel_presets") or {}
        for ch_name in acc_data.get("channels") or []:
            profile_id = snowflake_to_profile.get(str(ch_name))
            if not profile_id:
                continue
            enabled.append(profile_id)
            preset_name = str(channel_presets.get(ch_name) or default_preset_name)
            preset_id = _slugify(preset_name)
            if preset_id not in presets.presets:
                legacy = legacy_presets.get(preset_name)
                if isinstance(legacy, dict):
                    presets.presets[preset_id] = _macro_from_legacy_preset(legacy)
            targets.ensure_target(account_id, profile_id, preset_id)
            imported_targets += 1

        accounts.update_account(account_id, enabled_channel_ids=enabled)

    if accounts.accounts and not accounts.active_account_id:
        accounts.active_account_id = accounts.accounts[0].id

    return (
        f"Imported {imported_accounts} accounts, {imported_presets} presets, "
        f"{imported_targets} targets from MudaeBot---Copy"
    )
