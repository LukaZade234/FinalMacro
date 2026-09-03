"""Per-day minigame yield, rated per **use** over days that can be counted.

Three separate traps live in this data, and each one inflates a rate.

**The logs do not cover the same dates.** The spheres a board paid are events in
``data/events.jsonl`` under the ``minigame_<id>`` sources and reach back to the
first day the macro ran; the board counts live in ``data/minigame_log.json``,
which started much later. Dividing the full sphere history by the short board
history overstated ``$oh`` by 4.7x and ``$oc`` by 3.6x on the live data.

**A board is not a use.** One command can spend up to ten of the day's
allowance — ``$ot 5`` is a single board that cost five uses and pays roughly
five times what one use pays — so SP *per board* is inflated by whatever
multiplier the board was played at, and is not comparable between a play-all
batch and a hand-played single. The rate here is therefore **SP per use**, and
a day only enters it when every board that day recorded its ``uses``. Rows
written before that field existed are not guessed at: counting them as one use
each would read as fact and be wrong for every batched command.

**``base_sp`` is not comparable across games.** Transform spheres pay out
beyond the clicked emoji's base, and ``$oq`` and ``$ot`` record more clicks than
were paid. Awarded SP therefore always comes from the sphere events, never from
summing ``base_sp``.
"""

from __future__ import annotations

from typing import Any

from mudae.minigame_log import WIN_GAMES, game_label, get_minigame_events

MINIGAME_SOURCE_PREFIX = "minigame_"


def _day_of(entry: dict[str, Any]) -> str:
    return str(entry.get("date_key") or entry.get("recorded_at") or "")[:10]


def _matches(entry: dict[str, Any], *, account: str, server: str) -> bool:
    if account != "all" and str(entry.get("account_id") or "").strip() != account:
        return False
    if server != "all" and str(entry.get("guild_name") or "").strip() != server:
        return False
    return True


def _norm(value: str) -> str:
    text = str(value or "").strip()
    return text if text and text != "all" else "all"


def coverage(*, account: str = "all", server: str = "all") -> dict[str, Any]:
    """The days board counts exist for — the only days a rate can be formed over."""
    account, server = _norm(account), _norm(server)
    days = {
        _day_of(entry)
        for entry in get_minigame_events()
        if _day_of(entry) and _matches(entry, account=account, server=server)
    }
    ordered = sorted(days)
    return {
        "from": ordered[0] if ordered else "",
        "to": ordered[-1] if ordered else "",
        "days": len(ordered),
        "day_keys": ordered,
    }


def _boards_by_game_day(
    days: set[str],
    *,
    account: str,
    server: str,
) -> dict[str, dict[str, dict[str, int]]]:
    """``{game: {day: {boards, uses, unknown, won}}}``.

    ``unknown`` counts boards recorded before ``uses`` was written, which is
    what disqualifies a day from the per-use rate.
    """
    out: dict[str, dict[str, dict[str, int]]] = {}
    for entry in get_minigame_events():
        day = _day_of(entry)
        if day not in days or not _matches(entry, account=account, server=server):
            continue
        game = str(entry.get("game") or "").strip().lower()
        if not game:
            continue
        row = out.setdefault(game, {}).setdefault(
            day, {"boards": 0, "uses": 0, "unknown": 0, "won": 0}
        )
        row["boards"] += 1
        raw = entry.get("uses")
        if raw is None:
            row["unknown"] += 1
        else:
            try:
                row["uses"] += max(1, int(raw))
            except (TypeError, ValueError):
                row["unknown"] += 1
        if entry.get("won"):
            row["won"] += 1
    return out


def _sp_by_game_day(
    days: set[str],
    *,
    account: str,
    server: str,
) -> dict[str, dict[str, int]]:
    """``{game: {day: awarded sp}}`` from the sphere events, never ``base_sp``."""
    from mudae import event_log

    event_log.ensure_loaded()
    out: dict[str, dict[str, int]] = {}
    for entry in event_log.events("sphere"):
        day = _day_of(entry)
        if day not in days:
            continue
        source = str(entry.get("source") or "")
        if not source.startswith(MINIGAME_SOURCE_PREFIX):
            continue
        if not _matches(entry, account=account, server=server):
            continue
        game = source[len(MINIGAME_SOURCE_PREFIX):].strip().lower()
        try:
            amount = int(entry.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        per_day = out.setdefault(game, {})
        per_day[day] = per_day.get(day, 0) + amount
    return out


def _rate_per_use(
    by_day: dict[str, dict[str, int]],
    sp_by_day: dict[str, int],
) -> tuple[float | None, int, list[str]]:
    """SP per use over the days whose board rows all recorded their uses.

    Returns ``(rate, uses, days)``. A day with any unrecorded ``uses`` is left
    out of both halves rather than guessed at, so the numerator and denominator
    always cover the same days.
    """
    total_sp = 0
    total_uses = 0
    counted: list[str] = []
    for day, row in sorted(by_day.items()):
        if row["unknown"] or row["uses"] <= 0:
            continue
        total_sp += sp_by_day.get(day, 0)
        total_uses += row["uses"]
        counted.append(day)
    if total_uses <= 0:
        return None, 0, counted
    return total_sp / total_uses, total_uses, counted


def daily_yield(
    date_key: str,
    *,
    account: str = "all",
    server: str = "all",
) -> dict[str, Any]:
    """One day's boards, uses and spheres per game, against the per-use rate.

    ``benchmark_sp_per_use`` is ``None`` for a game with no countable uses in
    the window rather than 0 — "nothing to compare against" is not "it pays
    nothing". ``win_rate`` is ``None`` for ``$ot`` and ``$oh``, which have no
    win condition at all: a board only pays more or less, so a rate would be an
    invented statistic (see ``minigame_log.WIN_GAMES``).
    """
    account, server = _norm(account), _norm(server)
    day = str(date_key or "").strip()[:10]

    window = coverage(account=account, server=server)
    window_days = set(window["day_keys"])
    window_boards = _boards_by_game_day(window_days, account=account, server=server)
    window_sp = _sp_by_game_day(window_days, account=account, server=server)

    today_boards = (
        _boards_by_game_day({day}, account=account, server=server) if day else {}
    )
    today_sp = _sp_by_game_day({day}, account=account, server=server) if day else {}

    rated_days: set[str] = set()
    games: list[dict[str, Any]] = []
    for game in sorted(set(window_boards) | set(today_boards) | set(today_sp)):
        today_row = today_boards.get(game, {}).get(day, {})
        boards = today_row.get("boards", 0)
        uses = None if today_row.get("unknown") else today_row.get("uses", 0)
        won = today_row.get("won", 0)
        sp = today_sp.get(game, {}).get(day, 0)
        per_use = (sp / uses) if uses else None

        benchmark, benchmark_uses, counted = _rate_per_use(
            window_boards.get(game, {}), window_sp.get(game, {})
        )
        rated_days.update(counted)

        delta = None
        if per_use is not None and benchmark:
            delta = (per_use - benchmark) / benchmark * 100.0

        has_win = game in WIN_GAMES
        games.append({
            "game": game,
            "label": game_label(game),
            "boards": boards,
            "uses": uses,
            "sp": sp,
            "sp_per_use": per_use,
            "benchmark_sp_per_use": benchmark,
            "benchmark_uses": benchmark_uses,
            "delta_pct": delta,
            "has_win_state": has_win,
            "won": won if has_win else None,
            "win_rate": (won / boards * 100.0) if (has_win and boards) else None,
        })

    games.sort(key=lambda row: (-row["sp"], row["game"]))
    rated = sorted(rated_days)
    return {
        "date": day,
        "boards": sum(row["boards"] for row in games),
        "uses": (
            None
            if any(row["uses"] is None for row in games)
            else sum(row["uses"] for row in games)
        ),
        "sp": sum(row["sp"] for row in games),
        "games": games,
        "benchmark": {
            "from": rated[0] if rated else "",
            "to": rated[-1] if rated else "",
            "days": len(rated),
            "uses": sum(row["benchmark_uses"] for row in games),
            # Said plainly so the UI never labels this "all-time": a rate needs
            # a board count *and* a recorded use count, and the earliest logs
            # have neither.
            "note": (
                f"Per-use rates cover the {len(rated)} day(s) from {rated[0]} "
                f"where every board recorded its uses, not all history."
                if rated
                else "No days yet where every board recorded how many uses it spent."
            ),
        },
    }
