"""Persist a captured Mudae ``$wl`` listing, per (account, channel).

Keyed by the same ``account_id|channel_profile_id`` pair the rest of the app
scopes by, so switching either half of the scope bar shows that pair's own
capture and nothing else. A pair that has never been captured reads as empty
rather than borrowing another pair's rows — half a scope is not a scope, and
showing one server's roster under another is exactly the kind of silent
mix-up the per-pairing rule exists to stop.

Stored separately from ``accounts[]`` rather than on the account record — a
listing is 160 rows and the account record holds a token, so keeping a bulk
data blob out of it keeps the credential entry small and easy to eyeball.

The captured rows carry the ouroperk roster the app has never had (see
`mudae/parsers/wishlist.py`), which is what `macro/sphere_upgrades.py`
abstains on for perk 1, and the wishlist sizes the ``$bw`` optimum needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gui.wishlist_store import scope_key

# Cost of each level of perks 1-5, in spheres; the sixth level is the jump.
PERK_LEVEL_COSTS: tuple[int, ...] = (200, 400, 600, 800, 1000, 2000)
# Perks 6-10 are a single unlock.
PERK_UNLOCK_COST = 1000
# Perks 1-5 have six levels; 6-10 have one.
MULTI_LEVEL_PERKS = frozenset({1, 2, 3, 4, 5})
# Every perk maxed. Matches the "30,000 sp - Full" rows exactly.
FULL_COST = len(MULTI_LEVEL_PERKS) * sum(PERK_LEVEL_COSTS) + 5 * PERK_UNLOCK_COST


def sphere_cost(upgrades: dict[Any, Any], *, full: bool = False) -> int:
    """Spheres a roster costs, from the published ladder.

    Derived rather than read back, so it can be checked against the ``N sp``
    Mudae prints on the row — they agree on every real row seen so far, which
    is what makes the roster trustworthy as evidence.
    """
    if full:
        return FULL_COST
    total = 0
    for raw_perk, raw_count in (upgrades or {}).items():
        try:
            perk = int(raw_perk)
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        if perk in MULTI_LEVEL_PERKS:
            total += sum(PERK_LEVEL_COSTS[: min(count, len(PERK_LEVEL_COSTS))])
        else:
            total += PERK_UNLOCK_COST * min(count, 1)
    return total


def _clean_upgrades(raw: Any) -> dict[int, int]:
    """Perk keys survive a JSON round trip as strings; put them back as ints."""
    cleaned: dict[int, int] = {}
    if not isinstance(raw, dict):
        return cleaned
    for key, value in raw.items():
        try:
            cleaned[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return cleaned


def _clean_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    try:
        spheres = int(raw.get("spheres") or 0)
    except (TypeError, ValueError):
        spheres = 0
    # The `+N%` is the character's **perk-1 spawn bonus**, not a sphere-value
    # bonus — see `MUDAE_LOGIC.md`'s ouroperk section for the rule that
    # reproduces every row of a real capture.
    #
    # The key keeps its original, wrong-sounding name deliberately. `data/` is
    # Syncthing-shared across machines, and an instance running an older build
    # round-trips this file: renaming the key made that instance write the row
    # back with the value dropped, wiping all 160 of them. `perk1_spawn_pct` is
    # still read so a file written by a build that did rename it survives.
    percent = raw.get("sphere_percent")
    if percent is None:
        percent = raw.get("perk1_spawn_pct")
    try:
        percent = int(percent) if percent is not None else None
    except (TypeError, ValueError):
        percent = None
    return {
        "name": name,
        "starwish": bool(raw.get("starwish")),
        "sphere_percent": percent,
        "spheres": spheres,
        "upgrades_full": bool(raw.get("upgrades_full")),
        "upgrades": _clean_upgrades(raw.get("upgrades")),
    }


@dataclass
class MudaeWishlist:
    """One account's captured listing."""

    owner: str = ""
    wl_used: int | None = None
    wl_max: int | None = None
    sw_used: int | None = None
    sw_max: int | None = None
    complete: bool = False
    route: str = ""
    fetched_at: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MudaeWishlist:
        data = data if isinstance(data, dict) else {}

        def _num(key: str) -> int | None:
            try:
                value = data.get(key)
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        entries = [
            entry
            for entry in (_clean_entry(row) for row in data.get("entries") or [])
            if entry is not None
        ]
        return cls(
            owner=str(data.get("owner") or ""),
            wl_used=_num("wl_used"),
            wl_max=_num("wl_max"),
            sw_used=_num("sw_used"),
            sw_max=_num("sw_max"),
            complete=bool(data.get("complete")),
            route=str(data.get("route") or ""),
            fetched_at=str(data.get("fetched_at") or ""),
            entries=entries,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "wl_used": self.wl_used,
            "wl_max": self.wl_max,
            "sw_used": self.sw_used,
            "sw_max": self.sw_max,
            "complete": self.complete,
            "route": self.route,
            "fetched_at": self.fetched_at,
            # Perk keys go out as strings; ``_clean_upgrades`` puts them back.
            "entries": [
                {**entry, "upgrades": {str(k): v for k, v in entry["upgrades"].items()}}
                for entry in self.entries
            ],
        }

    @property
    def starwishes(self) -> int:
        return sum(1 for entry in self.entries if entry.get("starwish"))

    def to_client_dict(self) -> dict[str, Any]:
        """Payload for the Characters page — rows plus the derived cost."""
        rows = []
        for entry in self.entries:
            derived = sphere_cost(entry["upgrades"], full=entry["upgrades_full"])
            rows.append(
                {
                    **entry,
                    "upgrades": {str(k): v for k, v in entry["upgrades"].items()},
                    "perk_count": len(entry["upgrades"]),
                    "derived_cost": derived,
                    # Mudae's own figure vs the published ladder. A mismatch
                    # means the ladder moved or the row was misread, and the
                    # page should say so rather than quietly show either.
                    "cost_matches": derived == entry["spheres"],
                }
            )
        return {
            "owner": self.owner,
            "wl_used": self.wl_used,
            "wl_max": self.wl_max,
            "sw_used": self.sw_used,
            "sw_max": self.sw_max,
            "complete": self.complete,
            "route": self.route,
            "fetched_at": self.fetched_at,
            "entries": rows,
            "total_spheres": sum(entry["spheres"] for entry in self.entries),
            "captured": bool(self.entries),
        }


class MudaeWishlistStore:
    """Every scope's listing, as one ``settings.json`` key."""

    KEY = "mudae_wishlists"

    def __init__(self) -> None:
        self.by_scope: dict[str, MudaeWishlist] = {}

    def load_from_settings(self, saved: dict[str, Any]) -> None:
        raw = saved.get(self.KEY)
        self.by_scope = {}
        if not isinstance(raw, dict):
            return
        for key, payload in raw.items():
            scope = str(key or "").strip()
            if not scope:
                continue
            self.by_scope[scope] = MudaeWishlist.from_dict(payload)

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            self.KEY: {
                scope: listing.to_dict()
                for scope, listing in sorted(self.by_scope.items())
            }
        }

    def get(self, account_id: str, channel_profile_id: str) -> MudaeWishlist:
        """This pair's listing, or an empty one — never another pair's."""
        key = scope_key(account_id, channel_profile_id)
        if not key:
            return MudaeWishlist()
        return self.by_scope.get(key, MudaeWishlist())

    def set(
        self,
        account_id: str,
        channel_profile_id: str,
        listing: MudaeWishlist,
    ) -> None:
        key = scope_key(account_id, channel_profile_id)
        if key:
            self.by_scope[key] = listing
