"""Resolve active account + channel + preset into a runnable target."""

from __future__ import annotations

from gui.accounts import AccountStore
from gui.presets import PresetStore
from gui.server_profiles import ServerProfileStore
from gui.targets import ResolvedRunTarget, TargetStore


def resolve_run_target(
    accounts: AccountStore,
    profiles: ServerProfileStore,
    presets: PresetStore,
    targets: TargetStore,
) -> ResolvedRunTarget | None:
    account = accounts.active_account()
    channel = profiles.active_channel()
    if not account or not channel:
        return None
    if not account.token.strip():
        return None
    if not channel.channel_id.strip():
        return None

    preset_id = targets.preset_for(
        account.id,
        channel.id,
        presets.active_preset_id,
    )
    if preset_id not in presets.presets:
        preset_id = presets.default_preset_id
    macro = presets.find_preset(preset_id) or presets.active_preset()

    server = profiles.find_server(profiles.active_server_id)
    server_name = server.name if server else "Server"
    label = f"{account.name} · {server_name} · #{channel.name} · {preset_id}"

    return ResolvedRunTarget(
        token=account.token.strip(),
        discord_channel_id=channel.channel_id.strip(),
        macro_config=macro,
        preset_id=preset_id,
        account_id=account.id,
        channel_profile_id=channel.id,
        label=label,
    )
