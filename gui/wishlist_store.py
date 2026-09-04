"""Persist the app-only character/series wishlist.

One `data/settings.json` top-level key (``"wishlist"``). A **global** toggle
decides what the macro actually matches against:

* **on** — one list used on every account and server.
* **off** — a separate list per ``(account, channel)`` pair, so an alt or a
  second server can want different characters.

Both are kept, so flipping the toggle back does not lose the other side's
names. Matching during a run always resolves against the **run target**;
the page edits whichever pair its own scope bar is pointed at, which can
differ (see `gui/components/ScopeBar.qml`).

See `macro/wishlist.py` for the roll-matching this feeds and the input
parsing, and `AppWishlistView.qml` for the page that edits it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Both halves of a scope are ids without this character, and pinning both is
# required — a server hosts several accounts and an account plays several
# servers, so half a scope is not a scope.
_SCOPE_SEP = "|"


def scope_key(account_id: str, channel_profile_id: str) -> str:
    """Storage key for one ``(account, channel)`` pair, or "" if either is unset."""
    account = str(account_id or "").strip()
    channel = str(channel_profile_id or "").strip()
    if not account or not channel:
        return ""
    return f"{account}{_SCOPE_SEP}{channel}"


def _clean_names(raw: Any) -> list[str]:
    """Trim, drop blanks, and drop case-insensitive duplicates (first wins)."""
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    return cleaned


@dataclass
class WishlistEntries:
    """One list pair — the whole wishlist when global, one scope's when not."""

    characters: list[str] = field(default_factory=list)
    series: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WishlistEntries:
        data = data if isinstance(data, dict) else {}
        return cls(
            characters=_clean_names(data.get("characters")),
            series=_clean_names(data.get("series")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"characters": list(self.characters), "series": list(self.series)}

    def add_characters(self, names: list[str]) -> int:
        return self._add(self.characters, names)

    def add_series(self, names: list[str]) -> int:
        return self._add(self.series, names)

    def remove_character(self, name: str) -> bool:
        return self._remove(self.characters, name)

    def remove_series(self, name: str) -> bool:
        return self._remove(self.series, name)

    @staticmethod
    def _add(existing: list[str], names: list[str]) -> int:
        """Append the names not already present; returns how many were new."""
        added = 0
        for raw in names:
            name = str(raw or "").strip()
            if not name:
                continue
            if any(current.lower() == name.lower() for current in existing):
                continue
            existing.append(name)
            added += 1
        return added

    @staticmethod
    def _remove(existing: list[str], name: str) -> bool:
        target = str(name or "").strip().lower()
        for current in existing:
            if current.lower() == target:
                existing.remove(current)
                return True
        return False


@dataclass
class Wishlist:
    is_global: bool = True
    entries: WishlistEntries = field(default_factory=WishlistEntries)
    scoped: dict[str, WishlistEntries] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Wishlist:
        data = data if isinstance(data, dict) else {}
        raw_scoped = data.get("scopes")
        scoped: dict[str, WishlistEntries] = {}
        if isinstance(raw_scoped, dict):
            for key, value in raw_scoped.items():
                entries = WishlistEntries.from_dict(value)
                if entries.characters or entries.series:
                    scoped[str(key)] = entries
        return cls(
            # Defaults to global: with no scope picked yet that is the only
            # setting that can match anything at all.
            is_global=bool(data.get("global", True)),
            entries=WishlistEntries.from_dict(data),
            scoped=scoped,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"global": self.is_global}
        payload.update(self.entries.to_dict())
        payload["scopes"] = {
            key: value.to_dict() for key, value in sorted(self.scoped.items())
        }
        return payload

    def to_settings_fragment(self) -> dict[str, Any]:
        return {"wishlist": self.to_dict()}

    def entries_for(self, account_id: str, channel_profile_id: str) -> WishlistEntries:
        """The list this pair edits — the global one, or its own when scoped.

        Creates the scope's list on demand so the page can add to it; an
        untouched scope stays out of the saved file (:meth:`to_dict` keeps
        only non-empty ones).
        """
        if self.is_global:
            return self.entries
        key = scope_key(account_id, channel_profile_id)
        if not key:
            return WishlistEntries()
        return self.scoped.setdefault(key, WishlistEntries())

    def match_lists_for(
        self,
        account_id: str,
        channel_profile_id: str,
    ) -> tuple[list[str], list[str]]:
        """What the macro matches a roll against for this run target.

        Read-only twin of :meth:`entries_for` — never creates a scope, so the
        roll loop asking on every roll cannot grow the settings file.
        """
        if self.is_global:
            return list(self.entries.characters), list(self.entries.series)
        key = scope_key(account_id, channel_profile_id)
        entries = self.scoped.get(key) if key else None
        if entries is None:
            return [], []
        return list(entries.characters), list(entries.series)
