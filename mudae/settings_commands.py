"""Build Mudae ``$settings`` commands from desired field values and diff against current."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from mudae.parsers.settings_normalize import normalize_settings_fields

# v1 essential fields (phased scope from plan).
ESSENTIAL_APPLY_FIELDS: frozenset[str] = frozenset({
    "setclaim",
    "setinterval",
    "setrolls",
    "settimer",
    "setrare",
    "gamemode",
    "servlimroul",
    "togglebutton",
    "togglesnipe",
    "togglekakerasnipe",
    "togglensfw",
    "toggledisturbing",
    "togglechildtag",
    "setkakerabonus",
    "setspherebonus",
    "togglekakeratrade",
    "togglekakeraclaim",
    "togglekakeralike",
    "togglekakerarolls",
    "togglewishprotect",
    "togglewishfree",
    "togglespheretrade",
    "toggleclaimrank",
    "togglelikerank",
    "toggleclaimrolls",
    "togglelikerolls",
})

DIRECT_TOGGLE_FIELDS: frozenset[str] = frozenset({
    "toggleslash",
    "toggleclaimrank",
    "togglelikerank",
    "toggleclaimrolls",
    "togglelikerolls",
    "togglensfw",
    "toggledisturbing",
    "togglechildtag",
    "removecopylimit",
    "togglekakeratrade",
    "togglekakeraclaim",
    "togglekakeralike",
    "togglekakerarolls",
    "togglewishprotect",
    "togglewishfree",
    "togglespheretrade",
})

FIELD_GROUPS: dict[str, str] = {
    "setclaim": "rolls",
    "setinterval": "rolls",
    "setrolls": "rolls",
    "settimer": "rolls",
    "setrare": "rolls",
    "gamemode": "rolls",
    "servlimroul": "rolls",
    "togglebutton": "claims",
    "togglesnipe": "snipe",
    "togglekakerasnipe": "snipe",
    "togglensfw": "content",
    "toggledisturbing": "content",
    "togglechildtag": "content",
    "setkakerabonus": "kakera",
    "togglekakeratrade": "kakera",
    "togglekakeraclaim": "kakera",
    "togglekakeralike": "kakera",
    "togglekakerarolls": "kakera",
    "togglewishprotect": "kakera",
    "togglewishfree": "kakera",
    "setspherebonus": "spheres",
    "togglespheretrade": "spheres",
    "toggleclaimrank": "ranking",
    "togglelikerank": "ranking",
    "toggleclaimrolls": "ranking",
    "togglelikerolls": "ranking",
}

SETROLLS_MAX_BY_PREMIUM = {0: 8, 1: 13, 2: 16, 3: 21}


class ApplyKind(str, Enum):
    SETTER = "setter"
    ENUM = "enum"
    TOGGLE = "toggle"
    MULTI_ARG = "multi_arg"
    UNSUPPORTED = "unsupported"


@dataclass
class SettingsDiffItem:
    field: str
    group: str
    current: Any
    desired: Any
    command: str | None
    skipped_reason: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "group": self.group,
            "current": self.current,
            "desired": self.desired,
            "command": self.command,
            "skipped_reason": self.skipped_reason,
            "warning": self.warning,
        }


def _values_equal(current: Any, desired: Any) -> bool:
    if current is None and desired is None:
        return True
    if isinstance(current, dict) and isinstance(desired, dict):
        return current == desired
    return current == desired


def _build_setter(field: str, value: Any) -> str:
    return f"${field} {value}"


def _build_togglebutton(value: int) -> str:
    return f"$togglebutton {int(value)}"


def _build_servlimroul(limits: dict[str, int]) -> str:
    return (
        f"$servlimroul {limits['wa']} {limits['ha']} {limits['wg']} {limits['hg']}"
    )


def _build_snipe(field: str, value: dict[str, Any]) -> str:
    mode = int(value["mode"])
    seconds = value.get("seconds")
    if seconds is not None:
        return f"${field} {mode} {seconds}"
    return f"${field} {mode}"


def _build_toggle(field: str, current: Any, desired: bool) -> str | None:
    if current is None:
        return None
    cur_bool = bool(current)
    des_bool = bool(desired)
    if cur_bool == des_bool:
        return None
    return f"${field}"


def build_command_for_field(
    field: str,
    *,
    current: Any,
    desired: Any,
) -> tuple[str | None, str | None]:
    """Return ``(command, skip_reason)``."""
    if field not in ESSENTIAL_APPLY_FIELDS:
        return None, "not in v1 apply set"

    if _values_equal(current, desired):
        return None, "already matches"

    if field in DIRECT_TOGGLE_FIELDS:
        if current is None:
            return None, "current value unknown — fetch $settings first"
        cmd = _build_toggle(field, current, bool(desired))
        return cmd, None if cmd else "already matches"

    if field == "togglebutton":
        return _build_togglebutton(int(desired)), None

    if field == "servlimroul":
        if not isinstance(desired, dict):
            return None, "invalid servlimroul desired value"
        return _build_servlimroul(desired), None

    if field in {"togglesnipe", "togglekakerasnipe"}:
        if not isinstance(desired, dict):
            desired = {"mode": int(desired), "seconds": None}
        return _build_snipe(field, desired), None

    if isinstance(desired, bool):
        return _build_toggle(field, current, desired), None

    if isinstance(desired, (int, float, str)):
        return _build_setter(field, desired), None

    return None, f"unsupported desired type for {field}"


def diff_settings(
    current: dict[str, Any],
    desired: dict[str, Any],
    *,
    fields: frozenset[str] | None = None,
    groups: frozenset[str] | None = None,
) -> list[SettingsDiffItem]:
    cur = normalize_settings_fields(current)
    des = normalize_settings_fields(desired)
    target_fields = fields or ESSENTIAL_APPLY_FIELDS
    items: list[SettingsDiffItem] = []

    for field in sorted(target_fields):
        group = FIELD_GROUPS.get(field, "other")
        if groups is not None and group not in groups:
            continue
        current_val = cur.get(field)
        desired_val = des.get(field)
        if desired_val is None:
            continue
        command, skip = build_command_for_field(
            field,
            current=current_val,
            desired=desired_val,
        )
        skipped_reason = skip
        if command is None and skip is None:
            skipped_reason = "already matches"
        items.append(
            SettingsDiffItem(
                field=field,
                group=group,
                current=current_val,
                desired=desired_val,
                command=command,
                skipped_reason=skipped_reason,
            )
        )
    return items


def commands_from_diff(items: list[SettingsDiffItem]) -> list[str]:
    return [item.command for item in items if item.command]


def validate_preset_for_premium(
    fields: dict[str, Any],
    *,
    server_premium: int | None,
) -> list[str]:
    """Return human-readable blocking warnings."""
    warnings: list[str] = []
    premium = int(server_premium or 0)
    rolls = fields.get("setrolls")
    if rolls is not None:
        max_rolls = SETROLLS_MAX_BY_PREMIUM.get(premium, 8)
        if int(rolls) > max_rolls:
            warnings.append(
                f"setrolls {rolls} exceeds max {max_rolls} for server premium {premium}"
            )
    return warnings


def compliance_status(
    current: dict[str, Any],
    desired: dict[str, Any],
    *,
    fields: frozenset[str] | None = None,
) -> str:
    """Return ``match``, ``partial``, or ``drift``."""
    items = diff_settings(current, desired, fields=fields)
    comparable = [i for i in items if i.desired is not None]
    if not comparable:
        return "partial"
    mismatches = [i for i in comparable if not _values_equal(i.current, i.desired)]
    if not mismatches:
        return "match"
    unknown = [i for i in mismatches if i.current is None]
    if unknown and len(unknown) == len(mismatches):
        return "partial"
    return "drift"
