"""Per-account daily minigame uses (``$oh`` / ``$oc`` / ``$oq`` / ``$ot``).

Persisted on the channel profile next to perk 8 so a restart can skip
``$ohu`` / play-all until the UTC refill instead of re-querying Mudae.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from macro.perk8_daily import mudae_daily_date, next_daily_reset, parse_iso

MINIGAME_DAILY_KEY = "minigames"
MINIGAME_IDS = ("oh", "oc", "oq", "ot")
PLAYABLE_MINIGAMES = ("oh", "oc", "oq", "ot")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(dt_value: dt.datetime) -> str:
    return dt_value.astimezone(dt.timezone.utc).isoformat()


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class MinigameDailyEntry:
    """One game's daily uses for an account on one channel."""

    exhausted: bool = False
    left: int | None = None
    stored: int | None = None
    total: int | None = None
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MinigameDailyEntry:
        if not data:
            return cls()
        return cls(
            exhausted=bool(data.get("exhausted", False)),
            left=_coerce_int(data.get("left")),
            stored=_coerce_int(data.get("stored")),
            total=_coerce_int(data.get("total")),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exhausted": self.exhausted,
            "left": self.left,
            "stored": self.stored,
            "total": self.total,
            "updated_at": self.updated_at,
        }


@dataclass
class MinigameDailyRecord:
    """Persisted minigame daily state for one account on one channel."""

    games: dict[str, MinigameDailyEntry] = field(default_factory=dict)
    refill_at: str = ""
    last_refill_minutes: int | None = None
    updated_at: str = ""

    def entry(self, game: str) -> MinigameDailyEntry:
        key = str(game or "").lstrip("$").lower()
        found = self.games.get(key)
        if found is None:
            found = MinigameDailyEntry()
            self.games[key] = found
        return found

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MinigameDailyRecord:
        if not data:
            return cls()
        raw_games = data.get("games")
        games: dict[str, MinigameDailyEntry] = {}
        if isinstance(raw_games, dict):
            for game_id in MINIGAME_IDS:
                raw = raw_games.get(game_id)
                if isinstance(raw, dict):
                    games[game_id] = MinigameDailyEntry.from_dict(raw)
        return cls(
            games=games,
            refill_at=str(data.get("refill_at") or ""),
            last_refill_minutes=_coerce_int(data.get("last_refill_minutes")),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "games": {
                game_id: self.entry(game_id).to_dict() for game_id in MINIGAME_IDS
            },
            "refill_at": self.refill_at,
            "last_refill_minutes": self.last_refill_minutes,
            "updated_at": self.updated_at,
        }


def load_minigame_record(daily_resets: dict[str, Any] | None) -> MinigameDailyRecord:
    if not daily_resets:
        return MinigameDailyRecord()
    raw = daily_resets.get(MINIGAME_DAILY_KEY)
    if isinstance(raw, dict):
        return MinigameDailyRecord.from_dict(raw)
    return MinigameDailyRecord()


def save_minigame_record(
    daily_resets: dict[str, Any],
    record: MinigameDailyRecord,
) -> dict[str, Any]:
    updated = dict(daily_resets or {})
    updated[MINIGAME_DAILY_KEY] = record.to_dict()
    return updated


def _set_refill_deadline(
    record: MinigameDailyRecord,
    now: dt.datetime,
    *,
    refill_minutes: int | None = None,
) -> None:
    minutes = refill_minutes if refill_minutes is not None else record.last_refill_minutes
    if minutes is not None and minutes > 0:
        deadline = now + dt.timedelta(minutes=minutes)
        reset_at = next_daily_reset(now)
        if deadline > reset_at:
            deadline = reset_at
        record.last_refill_minutes = int((deadline - now).total_seconds() // 60) or 1
        record.refill_at = _iso(deadline)
        return
    reset_at = next_daily_reset(now)
    record.last_refill_minutes = int((reset_at - now).total_seconds() // 60) or 1
    record.refill_at = _iso(reset_at)


def refresh_minigames_if_refill_passed(
    record: MinigameDailyRecord,
    *,
    now: dt.datetime | None = None,
) -> MinigameDailyRecord:
    """Clear stale exhausted flags once the daily refill has passed."""
    now = now or _utc_now()
    updated = parse_iso(record.updated_at)
    refill_at = parse_iso(record.refill_at)
    new_day = bool(
        updated is not None and mudae_daily_date(updated) < mudae_daily_date(now)
    )
    refill_passed = bool(refill_at is not None and now >= refill_at)
    if not (new_day or refill_passed):
        return record
    for entry in record.games.values():
        entry.exhausted = False
        entry.left = None
        entry.stored = None
        entry.total = None
    return record


def should_skip_game(
    record: MinigameDailyRecord,
    game: str,
    *,
    now: dt.datetime | None = None,
) -> bool:
    """True when this game's daily uses are spent and refill has not passed."""
    now = now or _utc_now()
    record = refresh_minigames_if_refill_passed(record, now=now)
    entry = record.games.get(str(game or "").lstrip("$").lower())
    if entry is None or not entry.exhausted:
        return False
    refill_at = parse_iso(record.refill_at)
    if refill_at is None:
        return True
    return now < refill_at


def seconds_until_minigame_refill(
    record: MinigameDailyRecord,
    *,
    now: dt.datetime | None = None,
) -> float | None:
    """Seconds until playable minigames refill, or ``0.0`` if that already passed.

    ``None`` means no timed wake is needed — daily uses are not marked spent.
    """
    now = now or _utc_now()
    if not any(record.entry(game).exhausted for game in PLAYABLE_MINIGAMES):
        return None
    refill_at = parse_iso(record.refill_at)
    if refill_at is None:
        return None
    remaining = (refill_at - now).total_seconds()
    return max(0.0, remaining)


def should_skip_playable_minigames(
    record: MinigameDailyRecord,
    *,
    now: dt.datetime | None = None,
) -> bool:
    """True when ``$oh`` / ``$oc`` / ``$oq`` are all spent until refill."""
    now = now or _utc_now()
    record = refresh_minigames_if_refill_passed(record, now=now)
    return all(should_skip_game(record, game, now=now) for game in PLAYABLE_MINIGAMES)


def availability_from_record(record: MinigameDailyRecord) -> dict[str, int]:
    """Cached ``$ohu`` left/stored/total, defaulting missing games to 0."""
    result: dict[str, int] = {}
    for game_id in MINIGAME_IDS:
        entry = record.games.get(game_id) or MinigameDailyEntry()
        left = int(entry.left or 0)
        stored = int(entry.stored or 0)
        total = entry.total
        if total is None:
            total = left + stored
        result[f"{game_id}_left"] = left
        result[f"{game_id}_stored"] = stored
        result[f"{game_id}_total"] = max(0, int(total))
    return result


def update_record_from_ohu(
    record: MinigameDailyRecord,
    fields: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> MinigameDailyRecord:
    """Merge a fresh ``$ohu`` / ``$ohu8`` header into persisted minigame state."""
    now = now or _utc_now()
    stamp = _iso(now)
    record.updated_at = stamp
    refill_minutes = _coerce_int(
        fields.get("perk8_refill_minutes") or fields.get("refill_minutes")
    )
    if refill_minutes is not None:
        record.last_refill_minutes = refill_minutes
        _set_refill_deadline(record, now, refill_minutes=refill_minutes)

    for game_id in MINIGAME_IDS:
        left = _coerce_int(fields.get(f"{game_id}_left"))
        stored = _coerce_int(fields.get(f"{game_id}_stored"))
        total = _coerce_int(fields.get(f"{game_id}_total"))
        if total is None and left is not None:
            total = int(left) + int(stored or 0)
        entry = record.entry(game_id)
        entry.left = left
        entry.stored = stored
        entry.total = total
        entry.updated_at = stamp
        entry.exhausted = total is not None and int(total) <= 0

    if all(
        record.entry(game_id).exhausted for game_id in PLAYABLE_MINIGAMES
    ) and refill_minutes is None:
        _set_refill_deadline(record, now)
    return record


def mark_game_exhausted(
    record: MinigameDailyRecord,
    game: str,
    *,
    now: dt.datetime | None = None,
    refill_minutes: int | None = None,
) -> MinigameDailyRecord:
    """Mark one game spent (exhausted reply, or play-all finished its uses)."""
    now = now or _utc_now()
    entry = record.entry(game)
    entry.exhausted = True
    entry.left = 0
    entry.total = 0
    entry.updated_at = _iso(now)
    record.updated_at = entry.updated_at
    minutes = refill_minutes if refill_minutes is not None else record.last_refill_minutes
    _set_refill_deadline(record, now, refill_minutes=minutes)
    return record
