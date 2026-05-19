"""Run targets: account + channel profile + preset bindings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from macro.config import MacroConfig


@dataclass
class RunTarget:
    account_id: str
    channel_profile_id: str
    preset_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunTarget:
        return cls(
            account_id=str(data.get("account_id") or ""),
            channel_profile_id=str(data.get("channel_profile_id") or ""),
            preset_id=str(data.get("preset_id") or "default"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResolvedRunTarget:
    token: str
    discord_channel_id: str
    macro_config: MacroConfig
    preset_id: str
    account_id: str
    channel_profile_id: str
    label: str


class TargetStore:
    def __init__(self) -> None:
        self.targets: list[RunTarget] = []

    def load_from_settings(self, data: dict[str, Any]) -> None:
        raw = data.get("targets") or []
        self.targets = [
            RunTarget.from_dict(item)
            for item in raw
            if isinstance(item, dict)
        ]

    def to_settings_fragment(self) -> dict[str, Any]:
        return {"targets": [t.to_dict() for t in self.targets]}

    def to_client_dict(self) -> dict[str, Any]:
        return {"targets": [t.to_dict() for t in self.targets]}

    def find_target(self, account_id: str, channel_profile_id: str) -> RunTarget | None:
        for target in self.targets:
            if (
                target.account_id == account_id
                and target.channel_profile_id == channel_profile_id
            ):
                return target
        return None

    def preset_for(self, account_id: str, channel_profile_id: str, default: str) -> str:
        found = self.find_target(account_id, channel_profile_id)
        return found.preset_id if found else default

    def ensure_target(
        self,
        account_id: str,
        channel_profile_id: str,
        preset_id: str,
    ) -> None:
        found = self.find_target(account_id, channel_profile_id)
        if found:
            found.preset_id = preset_id
            return
        self.targets.append(
            RunTarget(
                account_id=account_id,
                channel_profile_id=channel_profile_id,
                preset_id=preset_id,
            )
        )

    def remove_targets_for_account(self, account_id: str) -> None:
        self.targets = [t for t in self.targets if t.account_id != account_id]

    def remove_targets_for_channel(self, channel_profile_id: str) -> None:
        self.targets = [
            t for t in self.targets if t.channel_profile_id != channel_profile_id
        ]
