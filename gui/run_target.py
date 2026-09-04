"""Resolve an account + channel + preset pair into a runnable target.

Two entry points, and the difference matters. :func:`resolve_run_target`
answers *"what would Run connect to"* — it reads the active selections, so it
moves whenever the Run target moves. :func:`resolve_scope_target` answers
*"what would a fetch on this page's scope bar connect to"*, which is a
different pair the moment a page is detached from Run.
"""

from __future__ import annotations

from gui.accounts import AccountProfile, AccountStore
from gui.presets import PresetStore
from gui.server_profiles import ChannelProfile, ServerProfile, ServerProfileStore
from gui.targets import ResolvedRunTarget, TargetStore


def _resolve(
    account: AccountProfile,
    server: ServerProfile | None,
    channel: ChannelProfile,
    presets: PresetStore,
    targets: TargetStore,
) -> ResolvedRunTarget | None:
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
    server = profiles.find_server(profiles.active_server_id)
    return _resolve(account, server, channel, presets, targets)


def resolve_scope_target(
    accounts: AccountStore,
    profiles: ServerProfileStore,
    presets: PresetStore,
    targets: TargetStore,
    account_id: str,
    channel_profile_id: str,
) -> ResolvedRunTarget | None:
    """Resolve one explicit pair, without reading or moving the actives.

    A page's scope bar deliberately keeps its selection to itself, so a fetch
    fired from it must resolve the pair it is *pointed at* rather than the one
    Run happens to be on.
    """
    account = accounts.find_account(account_id)
    found = profiles.find_channel_by_profile_id(channel_profile_id)
    if account is None or found is None:
        return None
    server, channel = found
    return _resolve(account, server, channel, presets, targets)
