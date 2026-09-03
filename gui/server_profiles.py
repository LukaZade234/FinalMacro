"""Server / channel profiles with parsed $settings and $bonus data."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from gui.sheet_store import SheetRead, clean_by_account, read_sheet, write_sheet
from mudae.parsers.bonus import merge_bonus_fields


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class ChannelProfile:
    id: str
    name: str
    channel_id: str
    guild_id: str | None = None
    guild_name: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    # ``$settings`` is the server's rule sheet, so it stays flat on the channel.
    # ``$bonus`` / ``$shop`` belong to the *connected account* and are keyed by
    # account id below. The bare ``bonus`` / ``shop`` dicts are the pre-split
    # layout, kept only so an old profile can still be read once — see
    # ``gui.sheet_store``.
    bonus: dict[str, Any] = field(default_factory=dict)
    shop: dict[str, Any] = field(default_factory=dict)
    bonus_by_account: dict[str, Any] = field(default_factory=dict)
    shop_by_account: dict[str, Any] = field(default_factory=dict)
    settings_summary: str = ""
    bonus_summary: str = ""
    shop_summary: str = ""
    daily_resets: dict[str, Any] = field(default_factory=dict)
    # ``daily_resets`` is keyed by account id; each value holds per-account
    # daily/cooldown blobs (e.g. ``perk8``). See ``macro.daily_store``.

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelProfile:
        return cls(
            id=str(data.get("id") or _new_id()),
            name=str(data.get("name") or "Channel"),
            channel_id=str(data.get("channel_id") or ""),
            guild_id=str(data["guild_id"]) if data.get("guild_id") is not None else None,
            guild_name=str(data["guild_name"]) if data.get("guild_name") is not None else None,
            settings=dict(data.get("settings") or {}),
            bonus=dict(data.get("bonus") or {}),
            shop=dict(data.get("shop") or {}),
            bonus_by_account=clean_by_account(data.get("bonus_by_account")),
            shop_by_account=clean_by_account(data.get("shop_by_account")),
            settings_summary=str(data.get("settings_summary") or ""),
            bonus_summary=str(data.get("bonus_summary") or ""),
            shop_summary=str(data.get("shop_summary") or ""),
            daily_resets=dict(data.get("daily_resets") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ServerProfile:
    id: str
    name: str
    guild_id: str | None = None
    channels: list[ChannelProfile] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerProfile:
        channels = [
            ChannelProfile.from_dict(item)
            for item in (data.get("channels") or [])
            if isinstance(item, dict)
        ]
        return cls(
            id=str(data.get("id") or _new_id()),
            name=str(data.get("name") or "Server"),
            guild_id=str(data["guild_id"]) if data.get("guild_id") is not None else None,
            channels=channels,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "guild_id": self.guild_id,
            "channels": [ch.to_dict() for ch in self.channels],
        }


class ServerProfileStore:
    def __init__(self) -> None:
        self.servers: list[ServerProfile] = []
        self.active_server_id: str = ""
        self.active_channel_id: str = ""
        # Who a pre-split ``$bonus`` / ``$shop`` blob is credited to. Set by the
        # GUI from the accounts store; blank means no sheet is ever inferred.
        self.main_account_id: str = ""

    def account_sheet(
        self,
        channel: ChannelProfile,
        kind: str,
        *,
        account_id: str,
    ) -> SheetRead:
        """One account's ``$bonus`` / ``$shop`` for a channel.

        Falls back to the pre-split blob for the main account only, flagged
        ``inferred``; see :mod:`gui.sheet_store`.
        """
        legacy = channel.bonus if kind == "bonus" else channel.shop
        legacy_summary = (
            channel.bonus_summary if kind == "bonus" else channel.shop_summary
        )
        by_account = (
            channel.bonus_by_account if kind == "bonus" else channel.shop_by_account
        )
        return read_sheet(
            by_account,
            account_id=account_id,
            legacy_fields=legacy,
            legacy_summary=legacy_summary,
            main_account_id=self.main_account_id,
        )

    def load_from_settings(self, data: dict[str, Any]) -> None:
        raw_servers = data.get("servers") or []
        self.servers = [
            ServerProfile.from_dict(item)
            for item in raw_servers
            if isinstance(item, dict)
        ]
        self.active_server_id = str(data.get("active_server_id") or "")
        self.active_channel_id = str(data.get("active_channel_id") or "")

        legacy_channel = str(data.get("channel_id") or "").strip()
        if legacy_channel and not self.servers:
            server = ServerProfile(id=_new_id(), name="Default")
            server.channels.append(
                ChannelProfile(
                    id=_new_id(),
                    name="Main",
                    channel_id=legacy_channel,
                )
            )
            self.servers.append(server)
            self.active_server_id = server.id
            self.active_channel_id = server.channels[0].id

        self._ensure_active_selection()

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            "servers": [srv.to_dict() for srv in self.servers],
            "active_server_id": self.active_server_id,
            "active_channel_id": self.active_channel_id,
        }

    def to_client_dict(self) -> dict[str, Any]:
        active = self.active_channel()
        return {
            "servers": [srv.to_dict() for srv in self.servers],
            "active_server_id": self.active_server_id,
            "active_channel_id": self.active_channel_id,
            "active_channel_discord_id": active.channel_id if active else "",
            "active_label": self.active_label(),
        }

    def active_label(self) -> str:
        server = self.find_server(self.active_server_id)
        channel = self.find_channel(self.active_server_id, self.active_channel_id)
        if server and channel:
            return f"{server.name} · #{channel.name}"
        if channel:
            return f"#{channel.name}"
        return ""

    def _ensure_active_selection(self) -> None:
        if self.servers and not self.find_server(self.active_server_id):
            self.active_server_id = self.servers[0].id
        server = self.find_server(self.active_server_id)
        if server and server.channels and not self.find_channel(
            self.active_server_id, self.active_channel_id
        ):
            self.active_channel_id = server.channels[0].id
        if not self.servers:
            self.active_server_id = ""
            self.active_channel_id = ""

    def find_server(self, server_id: str) -> ServerProfile | None:
        for server in self.servers:
            if server.id == server_id:
                return server
        return None

    def find_channel(
        self, server_id: str, channel_id: str
    ) -> ChannelProfile | None:
        server = self.find_server(server_id)
        if not server:
            return None
        for channel in server.channels:
            if channel.id == channel_id:
                return channel
        return None

    def find_channel_by_profile_id(self, channel_profile_id: str) -> tuple[ServerProfile, ChannelProfile] | None:
        for server in self.servers:
            for channel in server.channels:
                if channel.id == channel_profile_id:
                    return server, channel
        return None

    def all_channels(self) -> list[tuple[ServerProfile, ChannelProfile]]:
        pairs: list[tuple[ServerProfile, ChannelProfile]] = []
        for server in self.servers:
            for channel in server.channels:
                pairs.append((server, channel))
        return pairs

    def find_channel_by_discord_id(self, discord_channel_id: int | str) -> tuple[ServerProfile, ChannelProfile] | None:
        target = str(discord_channel_id).strip()
        for server in self.servers:
            for channel in server.channels:
                if channel.channel_id == target:
                    return server, channel
        return None

    def active_channel(self) -> ChannelProfile | None:
        return self.find_channel(self.active_server_id, self.active_channel_id)

    def active_discord_channel_id(self) -> str:
        channel = self.active_channel()
        return channel.channel_id.strip() if channel else ""

    def set_active(self, server_id: str, channel_profile_id: str) -> None:
        self.active_server_id = server_id
        self.active_channel_id = channel_profile_id
        self._ensure_active_selection()

    def add_server(self, name: str) -> str:
        server = ServerProfile(id=_new_id(), name=name.strip() or "Server")
        self.servers.append(server)
        if len(self.servers) == 1:
            self.active_server_id = server.id
        return server.id

    def remove_server(self, server_id: str) -> None:
        self.servers = [s for s in self.servers if s.id != server_id]
        self._ensure_active_selection()

    def rename_server(self, server_id: str, name: str) -> None:
        server = self.find_server(server_id)
        if server:
            server.name = name.strip() or server.name

    def add_channel(
        self,
        server_id: str,
        name: str,
        channel_id: str,
    ) -> str | None:
        server = self.find_server(server_id)
        if not server:
            return None
        channel = ChannelProfile(
            id=_new_id(),
            name=name.strip() or "Channel",
            channel_id=channel_id.strip(),
        )
        server.channels.append(channel)
        if len(server.channels) == 1 and self.active_server_id == server_id:
            self.active_channel_id = channel.id
        return channel.id

    def remove_channel(self, server_id: str, channel_profile_id: str) -> None:
        server = self.find_server(server_id)
        if not server:
            return
        server.channels = [c for c in server.channels if c.id != channel_profile_id]
        self._ensure_active_selection()

    def update_channel(
        self,
        server_id: str,
        channel_profile_id: str,
        *,
        name: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        channel = self.find_channel(server_id, channel_profile_id)
        if not channel:
            return
        if name is not None:
            channel.name = name.strip() or channel.name
        if channel_id is not None:
            channel.channel_id = channel_id.strip()

    def apply_parsed(
        self,
        discord_channel_id: int,
        *,
        kind: str,
        fields: dict[str, Any],
        summary: str,
        guild_id: int | None = None,
        guild_name: str | None = None,
        channel_name: str | None = None,
        account_id: str = "",
    ) -> None:
        found = self.find_channel_by_discord_id(discord_channel_id)
        if found:
            server, channel = found
        else:
            server_name = guild_name or "Server"
            server = ServerProfile(id=_new_id(), name=server_name)
            ch_label = channel_name or f"channel-{discord_channel_id}"
            channel = ChannelProfile(
                id=_new_id(),
                name=ch_label,
                channel_id=str(discord_channel_id),
            )
            server.channels.append(channel)
            self.servers.append(server)

        if guild_id is not None:
            gid = str(guild_id)
            server.guild_id = gid
            channel.guild_id = gid
        if guild_name:
            server.name = guild_name
        if channel_name:
            channel.name = channel_name

        if kind == "settings":
            channel.settings = dict(fields)
            if summary:
                channel.settings_summary = summary
        elif kind in ("bonus", "shop"):
            # No account to credit (no accounts configured yet, or a fetch off a
            # target that never resolved) means the sheet is genuinely
            # unattributed, so it goes to the unattributed slot rather than
            # being dropped — it reads back as ``inferred``.
            owner = str(account_id or "").strip() or self.main_account_id
            if kind == "bonus":
                # ``$bonus`` arrives in two parts (1/2 then 2/2), so merge onto
                # what *this account* already has, never onto another's.
                previous = self.account_sheet(channel, "bonus", account_id=owner)
                merged = merge_bonus_fields(dict(previous.fields), fields)
                if not owner:
                    channel.bonus = merge_bonus_fields(channel.bonus, fields)
                    if summary:
                        channel.bonus_summary = summary
                else:
                    channel.bonus_by_account = write_sheet(
                        channel.bonus_by_account,
                        account_id=owner,
                        fields=merged,
                        summary=summary or previous.summary,
                    )
                    # The pre-split blob is superseded for this account; leaving
                    # it would let the same sheet be inferred a second time.
                    channel.bonus = {}
                    channel.bonus_summary = ""
            elif not owner:
                channel.shop = dict(fields)
                if summary:
                    channel.shop_summary = summary
            else:
                channel.shop_by_account = write_sheet(
                    channel.shop_by_account,
                    account_id=owner,
                    fields=dict(fields),
                    summary=summary,
                )
                channel.shop = {}
                channel.shop_summary = ""
