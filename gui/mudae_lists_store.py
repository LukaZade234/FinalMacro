"""Captured ``$dl`` / ``$adl`` listings, and named presets of all three lists.

Two things live here, under two ``settings.json`` keys:

* ``mudae_lists`` — the latest ``$dld`` and ``$adl`` capture for each
  ``account_id|channel_profile_id`` pair. Per pair, never borrowed: a
  disablelist belongs to one player on one server. ``$wl`` is *not* stored
  here; its capture already lives in `gui/mudae_wishlist_store.py`, where
  `$bw` and the Spheres pages read it, and one copy is enough.
* ``mudae_list_presets`` — named copies a user saves from a capture, kept
  per list type (``dl`` / ``adl`` / ``wl``) and **global**, so one preset can
  later be sent to any server. Each remembers the pair it was saved from.

Nothing here sends anything; the editing step that turns a preset back into
Mudae commands comes later.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from gui.wishlist_store import scope_key

KINDS = ("dl", "adl", "wl")
# Kinds with a snapshot stored here; `wl` reads MudaeWishlistStore.
SNAPSHOT_KINDS = ("dl", "adl")

_POOLS = ("wa", "ha", "wg", "hg")

# Wish-type flags a saved `$wl` preset carries — what the editing step needs to
# rebuild the list. `owned` is deliberately not one: it says the character is
# claimed, which belongs to the live capture, not to a choice of wishes.
WISH_FLAGS = ("starwish", "locked", "kakera_wish")

# Mudae's own separator, and one name per line. Not commas: names contain them
# ("The Ghost Flower , Dianthus .").
_ENTRY_SPLIT = re.compile(r"[$\n\r]+")


def split_list_input(text: str) -> list[str]:
    """``A$B$C`` (or one per line) → names in order, spacing tidied, no repeats."""
    names: list[str] = []
    seen: set[str] = set()
    for chunk in _ENTRY_SPLIT.split(str(text or "")):
        name = " ".join(chunk.split())
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def _num(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _pools(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    cleaned = {pool: _num(raw.get(pool)) for pool in _POOLS}
    cleaned = {k: v for k, v in cleaned.items() if v is not None}
    return cleaned or None


def _names(raw: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        name = str((item.get("name") if isinstance(item, dict) else item) or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def _toggles(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        command = str(item.get("command") or "").strip()
        if name:
            out.append({"name": name, "command": command})
    return out


def clean_list_data(kind: str, raw: Any) -> dict[str, Any]:
    """The fields a stored listing of ``kind`` keeps, typed and nothing else."""
    raw = raw if isinstance(raw, dict) else {}
    base = {
        "owner": str(raw.get("owner") or ""),
        "used": _num(raw.get("used")),
        "max": _num(raw.get("max")),
        "pages": _num(raw.get("pages")),
        "seen_pages": [n for n in (_num(p) for p in raw.get("seen_pages") or []) if n],
        "complete": bool(raw.get("complete")),
        "count_matches": bool(raw.get("count_matches")),
        "entries": _names(raw.get("entries")),
    }
    if kind == "dl":
        base.update(
            {
                "total": _num(raw.get("total")),
                "pools": _pools(raw.get("pools")),
                "pool_limits": _pools(raw.get("pool_limits")),
                "floor": str(raw.get("floor") or ""),
                "limit_warnings": [str(x) for x in raw.get("limit_warnings") or [] if x],
                "toggles": _toggles(raw.get("toggles")),
            }
        )
    elif kind == "adl":
        base["characters"] = _num(raw.get("characters"))
    return base


def clean_wishlist_entries(raw: Any) -> list[dict[str, Any]]:
    """A preset's wishlist rows: name, order, and the wish type — no spheres.

    The type flags are what the editing step needs to rebuild the list
    (`$sw`, `$wishl`, `$wishk` …); spheres and upgrades belong to the live
    capture, not to a saved choice of wishes.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw or []:
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        rows.append({"name": name, **{flag: bool(item.get(flag)) for flag in WISH_FLAGS}})
    return rows


@dataclass
class ListSnapshot:
    """One capture of ``$dld`` or ``$adl`` for one pair."""

    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = ""
    route: str = ""
    reason: str = ""

    @classmethod
    def from_dict(cls, kind: str, raw: Any) -> ListSnapshot:
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            kind=kind,
            data=clean_list_data(kind, raw.get("data") if "data" in raw else raw),
            fetched_at=str(raw.get("fetched_at") or ""),
            route=str(raw.get("route") or ""),
            reason=str(raw.get("reason") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "fetched_at": self.fetched_at,
            "route": self.route,
            "reason": self.reason,
        }


@dataclass
class ListPreset:
    id: str
    kind: str
    name: str
    saved_at: str
    data: dict[str, Any]
    source_account_id: str = ""
    source_channel_profile_id: str = ""
    source_label: str = ""

    @classmethod
    def from_dict(cls, kind: str, raw: Any) -> ListPreset | None:
        if not isinstance(raw, dict):
            return None
        preset_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not preset_id or not name:
            return None
        payload = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        if kind == "wl":
            data = {
                "owner": str(payload.get("owner") or ""),
                "wl_used": _num(payload.get("wl_used")),
                "wl_max": _num(payload.get("wl_max")),
                "sw_used": _num(payload.get("sw_used")),
                "sw_max": _num(payload.get("sw_max")),
                "entries": clean_wishlist_entries(payload.get("entries")),
            }
        else:
            data = clean_list_data(kind, payload)
        return cls(
            id=preset_id,
            kind=kind,
            name=name,
            saved_at=str(raw.get("saved_at") or ""),
            data=data,
            source_account_id=str(raw.get("source_account_id") or ""),
            source_channel_profile_id=str(raw.get("source_channel_profile_id") or ""),
            source_label=str(raw.get("source_label") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "saved_at": self.saved_at,
            "data": self.data,
            "source_account_id": self.source_account_id,
            "source_channel_profile_id": self.source_channel_profile_id,
            "source_label": self.source_label,
        }


class MudaeListsStore:
    SNAPSHOT_KEY = "mudae_lists"
    PRESET_KEY = "mudae_list_presets"

    def __init__(self) -> None:
        self.snapshots: dict[str, dict[str, ListSnapshot]] = {k: {} for k in SNAPSHOT_KINDS}
        self.presets: dict[str, list[ListPreset]] = {k: [] for k in KINDS}

    # --- persistence -------------------------------------------------------

    def load_from_settings(self, saved: dict[str, Any]) -> None:
        self.snapshots = {k: {} for k in SNAPSHOT_KINDS}
        self.presets = {k: [] for k in KINDS}
        raw_snaps = saved.get(self.SNAPSHOT_KEY)
        if isinstance(raw_snaps, dict):
            for kind in SNAPSHOT_KINDS:
                by_scope = raw_snaps.get(kind)
                if not isinstance(by_scope, dict):
                    continue
                for scope, payload in by_scope.items():
                    if str(scope or "").strip():
                        self.snapshots[kind][str(scope)] = ListSnapshot.from_dict(kind, payload)
        raw_presets = saved.get(self.PRESET_KEY)
        if isinstance(raw_presets, dict):
            for kind in KINDS:
                for payload in raw_presets.get(kind) or []:
                    preset = ListPreset.from_dict(kind, payload)
                    if preset is not None:
                        self.presets[kind].append(preset)

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            self.SNAPSHOT_KEY: {
                kind: {scope: snap.to_dict() for scope, snap in sorted(by_scope.items())}
                for kind, by_scope in self.snapshots.items()
            },
            self.PRESET_KEY: {
                kind: [preset.to_dict() for preset in presets]
                for kind, presets in self.presets.items()
            },
        }

    # --- snapshots ---------------------------------------------------------

    def get(self, kind: str, account_id: str, channel_profile_id: str) -> ListSnapshot:
        key = scope_key(account_id, channel_profile_id)
        if kind not in self.snapshots or not key:
            return ListSnapshot(kind=kind, data=clean_list_data(kind, {}))
        return self.snapshots[kind].get(key) or ListSnapshot(kind=kind, data=clean_list_data(kind, {}))

    def set(
        self,
        kind: str,
        account_id: str,
        channel_profile_id: str,
        data: dict[str, Any],
        *,
        route: str = "pages",
        reason: str = "",
    ) -> ListSnapshot:
        key = scope_key(account_id, channel_profile_id)
        snap = ListSnapshot(
            kind=kind,
            data=clean_list_data(kind, data),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            route=route,
            reason=reason,
        )
        if kind in self.snapshots and key:
            self.snapshots[kind][key] = snap
        return snap

    # --- presets -----------------------------------------------------------

    def save_preset(
        self,
        kind: str,
        name: str,
        data: dict[str, Any],
        *,
        account_id: str = "",
        channel_profile_id: str = "",
        source_label: str = "",
    ) -> ListPreset | None:
        name = str(name or "").strip()
        if kind not in self.presets or not name:
            return None
        preset = ListPreset.from_dict(
            kind,
            {
                "id": uuid.uuid4().hex[:12],
                "name": name,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "data": data,
                "source_account_id": account_id,
                "source_channel_profile_id": channel_profile_id,
                "source_label": source_label,
            },
        )
        if preset is not None:
            self.presets[kind].append(preset)
        return preset

    def rename_preset(self, kind: str, preset_id: str, name: str) -> bool:
        name = str(name or "").strip()
        for preset in self.presets.get(kind, []):
            if preset.id == preset_id and name:
                preset.name = name
                return True
        return False

    def find_preset(self, kind: str, preset_id: str) -> ListPreset | None:
        for preset in self.presets.get(kind, []):
            if preset.id == preset_id:
                return preset
        return None

    # --- editing a saved preset --------------------------------------------
    #
    # Only saved presets are edited; "Current on Mudae" is a capture and stays
    # exactly what Mudae printed. The slot counts follow the rows (`$adl`
    # series slots, `$dl` slots, `$wl` / `$sw` sizes). The other figures — `$adl`
    # characters, `$dl` total and per-pool counts — are the user's to type, or
    # to leave blank; Mudae is the only thing that can compute them.

    def _edited(self, preset: ListPreset) -> None:
        data = preset.data
        entries = data.get("entries") or []
        if preset.kind == "wl":
            data["wl_used"] = len(entries)
            data["sw_used"] = sum(1 for e in entries if e.get("starwish"))
            return
        data["used"] = len(entries)
        data["complete"] = True
        data["count_matches"] = True
        data["pages"] = None
        data["seen_pages"] = []
        if preset.kind == "dl":
            # Limits differ per server; a preset does not carry them.
            data["pool_limits"] = None
            data["floor"] = ""
            data["limit_warnings"] = []

    def add_entries(self, kind: str, preset_id: str, text: str) -> int:
        """Append plain names / commands from ``text``; returns rows added."""
        return int(self.apply_input(kind, preset_id, text)["added"])

    def apply_input(self, kind: str, preset_id: str, text: str) -> dict[str, Any]:
        """Apply the Add box: names, `$toggle…` and wish commands.

        A name already on the list is not added twice; a wish command naming
        it sets that command's flags on it instead (``$swl reze`` makes an
        existing Reze a locked starwish) and, with ``i``, moves it.
        """
        from macro.list_input import parse_list_input

        summary: dict[str, Any] = {"added": 0, "updated": 0, "toggles": 0, "ignored": []}
        preset = self.find_preset(kind, preset_id)
        if preset is None:
            return summary
        parsed = parse_list_input(kind, text)
        summary["ignored"] = list(parsed.ignored)
        entries = preset.data.setdefault("entries", [])

        def key(entry: Any) -> str:
            return str(entry.get("name") if isinstance(entry, dict) else entry).lower()

        for batch in parsed.batches:
            # Where this batch goes: an index, or the end.
            insert_at: int | None = None
            if batch.position is not None:
                insert_at = max(0, min(len(entries), batch.position - 1))
            elif batch.after:
                for i, entry in enumerate(entries):
                    if key(entry) == batch.after.lower():
                        insert_at = i + 1
                        break
            for name in batch.names:
                existing = next((i for i, e in enumerate(entries) if key(e) == name.lower()), None)
                if existing is not None:
                    entry = entries[existing]
                    if kind == "wl" and isinstance(entry, dict):
                        for flag in WISH_FLAGS:
                            if getattr(batch, flag):
                                entry[flag] = True
                    if insert_at is not None:
                        entries.pop(existing)
                        if existing < insert_at:
                            insert_at -= 1
                        entries.insert(insert_at, entry)
                        insert_at += 1
                    summary["updated"] += 1
                    continue
                entry = (
                    {"name": name, **{flag: bool(getattr(batch, flag)) for flag in WISH_FLAGS}}
                    if kind == "wl"
                    else name
                )
                if insert_at is None:
                    entries.append(entry)
                else:
                    entries.insert(insert_at, entry)
                    insert_at += 1
                summary["added"] += 1

        for command in parsed.toggles:
            if self.set_toggle(kind, preset_id, command, True, _edit=False):
                summary["toggles"] += 1
            elif command not in {t.get("command") for t in preset.data.get("toggles") or []}:
                summary["ignored"].append(command)

        if summary["added"] or summary["updated"] or summary["toggles"]:
            self._edited(preset)
        return summary

    def set_toggle(
        self, kind: str, preset_id: str, command: str, on: bool, *, _edit: bool = True
    ) -> bool:
        """Tick or untick a whole-category toggle on a `$dl` preset.

        Only the toggles Mudae is known to print (`macro.list_input.KNOWN_TOGGLES`)
        can be added, since the label is Mudae's wording, not a guess; any
        toggle can be removed.
        """
        from macro.list_input import KNOWN_TOGGLES

        preset = self.find_preset(kind, preset_id)
        if preset is None or kind != "dl":
            return False
        command = "$" + str(command or "").strip().lstrip("$").lower()
        toggles = preset.data.setdefault("toggles", [])
        present = any(t.get("command") == command for t in toggles)
        if on:
            if present or command not in KNOWN_TOGGLES:
                return False
            toggles.append({"name": KNOWN_TOGGLES[command], "command": command})
        else:
            if not present:
                return False
            preset.data["toggles"] = [t for t in toggles if t.get("command") != command]
        if _edit:
            self._edited(preset)
        return True

    # Hand-typed figures: `$adl` characters, `$dl` total and per-pool counts.
    COUNT_FIELDS = {"adl": ("characters",), "dl": ("total", "wa", "ha", "wg", "hg")}

    def set_count(self, kind: str, preset_id: str, field_name: str, value: Any) -> bool:
        """Set one optional figure; blank (or junk) clears it."""
        if field_name not in self.COUNT_FIELDS.get(kind, ()):
            return False
        preset = self.find_preset(kind, preset_id)
        if preset is None:
            return False
        number = _num(str(value).replace(",", "").strip()) if str(value or "").strip() else None
        if number is not None and number < 0:
            number = None
        if field_name in ("wa", "ha", "wg", "hg"):
            pools = dict(preset.data.get("pools") or {})
            if number is None:
                pools.pop(field_name, None)
            else:
                pools[field_name] = number
            preset.data["pools"] = pools or None
        else:
            preset.data[field_name] = number
        return True

    def remove_entry(self, kind: str, preset_id: str, index: int) -> bool:
        preset = self.find_preset(kind, preset_id)
        entries = preset.data.get("entries") if preset else None
        if not entries or not 0 <= index < len(entries):
            return False
        del entries[index]
        self._edited(preset)
        return True

    def rename_entry(self, kind: str, preset_id: str, index: int, name: str) -> bool:
        """Rename one row; refused when the new name is blank or already listed."""
        name = " ".join(str(name or "").split())
        preset = self.find_preset(kind, preset_id)
        entries = preset.data.get("entries") if preset else None
        if not name or not entries or not 0 <= index < len(entries):
            return False
        for i, entry in enumerate(entries):
            other = entry.get("name") if isinstance(entry, dict) else entry
            if i != index and str(other).lower() == name.lower():
                return False
        if isinstance(entries[index], dict):
            entries[index]["name"] = name
        else:
            entries[index] = name
        self._edited(preset)
        return True

    def move_entry(self, kind: str, preset_id: str, index: int, delta: int) -> bool:
        """Move a row up (-1) or down (+1)."""
        return self.move_entry_to(kind, preset_id, index, index + delta)

    def move_entry_to(self, kind: str, preset_id: str, source: int, target: int) -> bool:
        """Move row ``source`` so it ends up at index ``target`` (drag and drop).

        Order matters for `$wl`: the perk-1 bonus wraps around neighbours.
        """
        preset = self.find_preset(kind, preset_id)
        entries = preset.data.get("entries") if preset else None
        if not entries or not 0 <= source < len(entries) or not 0 <= target < len(entries):
            return False
        if source == target:
            return False
        entries.insert(target, entries.pop(source))
        return True

    def set_entry_flag(
        self, kind: str, preset_id: str, index: int, flag: str, value: bool
    ) -> bool:
        if kind != "wl" or flag not in WISH_FLAGS:
            return False
        preset = self.find_preset(kind, preset_id)
        entries = preset.data.get("entries") if preset else None
        if not entries or not 0 <= index < len(entries):
            return False
        entries[index][flag] = bool(value)
        self._edited(preset)
        return True

    def remove_toggle(self, kind: str, preset_id: str, index: int) -> bool:
        preset = self.find_preset(kind, preset_id)
        toggles = preset.data.get("toggles") if preset else None
        if not toggles or not 0 <= index < len(toggles):
            return False
        del toggles[index]
        return True

    def delete_preset(self, kind: str, preset_id: str) -> bool:
        presets = self.presets.get(kind, [])
        kept = [p for p in presets if p.id != preset_id]
        if len(kept) == len(presets):
            return False
        self.presets[kind] = kept
        return True
