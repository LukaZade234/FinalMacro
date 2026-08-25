"""Reaction-power and perk-9 caps from stored ``$bonus`` / ``$shop`` sheets.

Fall back to the Mudae defaults when a channel has never fetched the sheet.
"""

from __future__ import annotations

from typing import Any

from macro.perk9_daily import PERK9_CLICK_MAX_DEFAULT
from macro.reaction_power import DEFAULT_MAX_REACTION_POWER


def power_max_from_bonus(bonus: dict[str, Any] | None) -> float:
    """``kakera_max_power`` from ``$bonus``, or the 155 default."""
    raw = (bonus or {}).get("kakera_max_power")
    if raw is None:
        return DEFAULT_MAX_REACTION_POWER
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_REACTION_POWER
    if value <= 0:
        return DEFAULT_MAX_REACTION_POWER
    return value


def _positive_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def rolls_max_from_sheets(
    bonus: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> int | None:
    """Hourly roll pool: ``$bonus`` net, else ``$setrolls``.

    ``$settings`` ``setrolls`` is the server base (often 21). ``$bonus``
    ``rolls_per_hour.net`` is what ``$tu`` reports as the hour's total.
    """
    rolls = (bonus or {}).get("rolls_per_hour")
    if isinstance(rolls, dict):
        net = _positive_int(rolls.get("net"))
        if net is not None:
            return net
    return _positive_int((settings or {}).get("setrolls"))


def perk9_max_from_shop(shop: dict[str, Any] | None) -> int:
    """``perk9_click_max`` from ``$shop`` (10 + OP9 extra), or 20."""
    raw = (shop or {}).get("perk9_click_max")
    if raw is None:
        return PERK9_CLICK_MAX_DEFAULT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return PERK9_CLICK_MAX_DEFAULT
    if value <= 0:
        return PERK9_CLICK_MAX_DEFAULT
    return value


def apply_sheet_caps(
    state: Any,
    *,
    bonus: dict[str, Any] | None = None,
    shop: dict[str, Any] | None = None,
) -> None:
    """Write sheet caps onto runtime state; clamp current power if the max dropped."""
    max_power = power_max_from_bonus(bonus)
    state.power_max_percent = max_power
    current = getattr(state, "power_percent", None)
    if current is not None and float(current) > max_power:
        state.power_percent = max_power
    state.perk9_click_max = perk9_max_from_shop(shop)
