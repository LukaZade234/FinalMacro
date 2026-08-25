"""Discord account profiles (tokens and enabled channels)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class AccountProfile:
    id: str
    name: str
    token: str = ""
    type: str = "Main"
    enabled_channel_ids: list[str] = field(default_factory=list)
    # Channel profile id used for account-global $p / $daily (empty = disabled).
    daily_channel_id: str = ""
    p_next_ready_at: str = ""
    daily_next_ready_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccountProfile:
        enabled = data.get("enabled_channel_ids") or []
        return cls(
            id=str(data.get("id") or _new_id()),
            name=str(data.get("name") or "Account"),
            token=str(data.get("token") or ""),
            type=str(data.get("type") or "Main"),
            enabled_channel_ids=[str(x) for x in enabled if x],
            daily_channel_id=str(data.get("daily_channel_id") or ""),
            p_next_ready_at=str(data.get("p_next_ready_at") or ""),
            daily_next_ready_at=str(data.get("daily_next_ready_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AccountStore:
    def __init__(self) -> None:
        self.accounts: list[AccountProfile] = []
        self.active_account_id: str = ""

    def load_from_settings(self, data: dict[str, Any]) -> None:
        raw = data.get("accounts") or []
        self.accounts = [
            AccountProfile.from_dict(item)
            for item in raw
            if isinstance(item, dict)
        ]
        self.active_account_id = str(data.get("active_account_id") or "")

        legacy_token = str(data.get("token") or "").strip()
        if legacy_token and not self.accounts:
            account = AccountProfile(
                id=_new_id(),
                name="Default",
                token=legacy_token,
                type="Main",
            )
            self.accounts.append(account)
            self.active_account_id = account.id

        self._ensure_active_selection()

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            "accounts": [acc.to_dict() for acc in self.accounts],
            "active_account_id": self.active_account_id,
        }

    def to_client_dict(self) -> dict[str, Any]:
        active = self.active_account()
        return {
            "accounts": [acc.to_dict() for acc in self.accounts],
            "active_account_id": self.active_account_id,
            "active_account_name": active.name if active else "",
        }

    def _ensure_active_selection(self) -> None:
        if self.accounts and not self.find_account(self.active_account_id):
            self.active_account_id = self.accounts[0].id
        if not self.accounts:
            self.active_account_id = ""

    def find_account(self, account_id: str) -> AccountProfile | None:
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def active_account(self) -> AccountProfile | None:
        return self.find_account(self.active_account_id)

    def active_token(self) -> str:
        account = self.active_account()
        return account.token.strip() if account else ""

    def set_active(self, account_id: str) -> None:
        self.active_account_id = account_id
        self._ensure_active_selection()

    def add_account(self, name: str, *, token: str = "", account_type: str = "Main") -> str:
        account = AccountProfile(
            id=_new_id(),
            name=name.strip() or "Account",
            token=token.strip(),
            type=account_type.strip() or "Main",
        )
        self.accounts.append(account)
        if len(self.accounts) == 1:
            self.active_account_id = account.id
        return account.id

    def remove_account(self, account_id: str) -> None:
        self.accounts = [a for a in self.accounts if a.id != account_id]
        self._ensure_active_selection()

    def update_account(
        self,
        account_id: str,
        *,
        name: str | None = None,
        token: str | None = None,
        account_type: str | None = None,
        enabled_channel_ids: list[str] | None = None,
        daily_channel_id: str | None = None,
        p_next_ready_at: str | None = None,
        daily_next_ready_at: str | None = None,
    ) -> None:
        account = self.find_account(account_id)
        if not account:
            return
        if name is not None:
            account.name = name.strip() or account.name
        if token is not None:
            account.token = token.strip()
        if account_type is not None:
            account.type = account_type.strip() or account.type
        if enabled_channel_ids is not None:
            account.enabled_channel_ids = list(enabled_channel_ids)
        if daily_channel_id is not None:
            account.daily_channel_id = daily_channel_id.strip()
        if p_next_ready_at is not None:
            account.p_next_ready_at = p_next_ready_at.strip()
        if daily_next_ready_at is not None:
            account.daily_next_ready_at = daily_next_ready_at.strip()
