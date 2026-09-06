"""Display catalog for a stored ``$limroul`` sheet.

Four roulettes, three things known about each: the player's own limit, the
server's ceiling, and how far down the popularity ranking that limit reaches
locally and globally. Laid out one roulette per row rather than one *field* per
row, because a reader compares `$wa` against `$wg`, never one roulette's limit
against another's rank.
"""

from __future__ import annotations

from typing import Any

from mudae.parsers.limroul import ROULETTE_LABELS, ROULETTES, limits_agree

LIMROUL_FIELD_KEYS: tuple[str, ...] = (
    "limits",
    "server_max",
    "tops",
    "limits_agree",
)


def pool_size(limits: dict[str, Any] | None, roulette: str) -> int | None:
    """One roulette's pool size, or ``None`` when it was not reported."""
    value = (limits or {}).get(str(roulette or "").lower())
    return None if value is None else int(value)


def _fmt(value: Any) -> str:
    return "—" if value is None else f"{int(value):,}"


def fields_to_limroul_display_dict(fields: dict[str, Any]) -> dict[str, Any]:
    """GUI rows for a stored ``$limroul`` sheet (same shape as the other sheets)."""
    data = dict(fields or {})
    limits = data.get("limits") or {}
    server_max = data.get("server_max") or {}
    tops = data.get("tops") or {}

    rows: list[dict[str, Any]] = []
    for roulette in ROULETTES:
        limit = limits.get(roulette)
        top = tops.get(roulette) or {}
        detail = ""
        if top.get("global_rank") is not None:
            # The gap is the server's own disable list: reaching local #2,000 at
            # global #3,405 means 1,405 more popular characters are off here.
            detail = f"down to global #{int(top['global_rank']):,}"
        if server_max.get(roulette) is not None:
            ceiling = f"cap {_fmt(server_max[roulette])}"
            detail = f"{detail} · {ceiling}" if detail else ceiling
        rows.append({
            "field": roulette,
            "label": ROULETTE_LABELS.get(roulette, f"${roulette}"),
            "command": f"${roulette}",
            "display": _fmt(limit),
            "detail": detail,
            "has_value": limit is not None,
            "value": None if limit is None else int(limit),
        })

    same = data.get("limits_agree")
    if same is None:
        same = limits_agree(limits)
    filled = sum(1 for row in rows if row["has_value"])
    return {
        "sections": [{"id": "pools", "title": "Characters per roulette", "rows": rows}],
        "field_count": filled,
        "limits_agree": same,
        "roulettes": list(ROULETTES),
    }
