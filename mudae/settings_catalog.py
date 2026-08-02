"""Catalog and display helpers for Mudae ``$settings`` fields (GUI + presets)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mudae.parsers.settings_normalize import normalize_settings_fields

_TOGGLEBUTTON_LABELS = {
    0: "for public wishes only",
    1: "never automatically added",
    2: "for all your rolls",
}

_GAMEMODE_LABELS = {
    0: "mode 0",
    1: "default (mode 1)",
    2: "mode 2",
    3: "mode 3",
}

_SNIPE_MODE_LABELS = {
    0: "no restriction",
    1: "partial (wishlist 8s)",
    2: "full (8s lock)",
    3: "wish restriction 1",
    4: "wish restriction 2",
    5: "combined restriction 1",
    6: "combined restriction 2",
}


@dataclass(frozen=True)
class CatalogEntry:
    field: str
    label: str
    command: str
    section: str
    editor: str  # int, bool, enum, snipe, servlimroul, percent, text, readonly
    options: tuple[dict[str, Any], ...] = ()
    min_value: int | None = None
    max_value: int | None = None
    apply_group: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "command": self.command,
            "section": self.section,
            "editor": self.editor,
            "options": [dict(opt) for opt in self.options],
            "min_value": self.min_value,
            "max_value": self.max_value,
            "apply_group": self.apply_group,
        }


def _bool_options() -> tuple[dict[str, Any], ...]:
    return (
        {"value": True, "label": "enabled"},
        {"value": False, "label": "disabled"},
    )


def _enum_options(mapping: dict[int, str]) -> tuple[dict[str, Any], ...]:
    return tuple({"value": k, "label": v} for k, v in sorted(mapping.items()))


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "server_premium",
        "Server Premium",
        "",
        "meta",
        "readonly",
    ),
    CatalogEntry("prefix", "Prefix", "$prefix", "general", "text"),
    CatalogEntry(
        "lang",
        "Lang",
        "$lang",
        "general",
        "enum",
        (
            {"value": "en", "label": "English"},
            {"value": "fr", "label": "French"},
            {"value": "pt-br", "label": "Portuguese (BR)"},
            {"value": "es", "label": "Spanish"},
        ),
    ),
    CatalogEntry(
        "setclaim",
        "Claim reset",
        "$setclaim",
        "rolls",
        "int",
        min_value=60,
        max_value=600,
        apply_group="rolls",
    ),
    CatalogEntry(
        "setinterval",
        "Exact minute of the reset",
        "$setinterval",
        "rolls",
        "int",
        min_value=0,
        max_value=59,
        apply_group="rolls",
    ),
    CatalogEntry("shifthour", "Reset shifted", "$shifthour", "rolls", "int", apply_group="rolls"),
    CatalogEntry(
        "setrolls",
        "Rolls per hour",
        "$setrolls",
        "rolls",
        "int",
        min_value=1,
        max_value=21,
        apply_group="rolls",
    ),
    CatalogEntry(
        "settimer",
        "Claim reaction expires",
        "$settimer",
        "rolls",
        "int",
        min_value=1,
        max_value=999,
        apply_group="rolls",
    ),
    CatalogEntry(
        "setrare",
        "Spawn rarity multiplier",
        "$setrare",
        "rolls",
        "int",
        min_value=1,
        max_value=9999,
        apply_group="rolls",
    ),
    CatalogEntry(
        "setkakerabonus",
        "% kakera bonus",
        "$setkakerabonus",
        "kakera",
        "percent",
        min_value=0,
        max_value=9999,
        apply_group="kakera",
    ),
    CatalogEntry(
        "setspherebonus",
        "% sphere bonus",
        "$setspherebonus",
        "spheres",
        "percent",
        min_value=0,
        max_value=9999,
        apply_group="spheres",
    ),
    CatalogEntry(
        "gamemode",
        "Game mode",
        "$gamemode",
        "rolls",
        "enum",
        _enum_options(_GAMEMODE_LABELS),
        apply_group="rolls",
    ),
    CatalogEntry(
        "servlimroul",
        "Server roll limits",
        "$servlimroul",
        "rolls",
        "servlimroul",
        apply_group="rolls",
    ),
    CatalogEntry("channelinstance", "Channel instance", "$channelinstance", "general", "int"),
    CatalogEntry(
        "toggleslash",
        "Slash commands",
        "$toggleslash",
        "general",
        "bool",
        _bool_options(),
    ),
    CatalogEntry(
        "toggleclaimrank",
        "Ranking (claims)",
        "$toggleclaimrank",
        "ranking",
        "bool",
        _bool_options(),
        apply_group="ranking",
    ),
    CatalogEntry(
        "togglelikerank",
        "Ranking (likes)",
        "$togglelikerank",
        "ranking",
        "bool",
        _bool_options(),
        apply_group="ranking",
    ),
    CatalogEntry(
        "toggleclaimrolls",
        "Roll display: claims",
        "$toggleclaimrolls",
        "ranking",
        "bool",
        _bool_options(),
        apply_group="ranking",
    ),
    CatalogEntry(
        "togglelikerolls",
        "Roll display: likes",
        "$togglelikerolls",
        "ranking",
        "bool",
        _bool_options(),
        apply_group="ranking",
    ),
    CatalogEntry(
        "togglensfw",
        "NSFW series",
        "$togglensfw",
        "content",
        "bool",
        _bool_options(),
        apply_group="content",
    ),
    CatalogEntry(
        "toggledisturbing",
        "Disturbing imagery",
        "$toggledisturbing",
        "content",
        "bool",
        _bool_options(),
        apply_group="content",
    ),
    CatalogEntry(
        "togglechildtag",
        "Child characters",
        "$togglechildtag",
        "content",
        "bool",
        _bool_options(),
        apply_group="content",
    ),
    CatalogEntry(
        "togglesnipe",
        "Rolls sniping",
        "$togglesnipe",
        "snipe",
        "snipe",
        _enum_options(_SNIPE_MODE_LABELS),
        apply_group="snipe",
    ),
    CatalogEntry(
        "togglekakerasnipe",
        "Kakera sniping",
        "$togglekakerasnipe",
        "snipe",
        "snipe",
        _enum_options(_SNIPE_MODE_LABELS),
        apply_group="snipe",
    ),
    CatalogEntry("haremlimit", "Collection limit", "$haremlimit", "general", "int"),
    CatalogEntry(
        "removecopylimit",
        "Copy limits",
        "$removecopylimit",
        "general",
        "bool",
        _bool_options(),
    ),
    CatalogEntry(
        "togglebutton",
        "Claim buttons",
        "$togglebutton",
        "claims",
        "enum",
        _enum_options(_TOGGLEBUTTON_LABELS),
        apply_group="claims",
    ),
    CatalogEntry(
        "togglekakeratrade",
        "Kakera trading",
        "$togglekakeratrade",
        "kakera",
        "bool",
        _bool_options(),
        apply_group="kakera",
    ),
    CatalogEntry(
        "togglekakeraclaim",
        "Kakera calc: claims",
        "$togglekakeraclaim",
        "kakera",
        "bool",
        _bool_options(),
        apply_group="kakera",
    ),
    CatalogEntry(
        "togglekakeralike",
        "Kakera calc: likes",
        "$togglekakeralike",
        "kakera",
        "bool",
        _bool_options(),
        apply_group="kakera",
    ),
    CatalogEntry(
        "togglekakerarolls",
        "Kakera value on rolls",
        "$togglekakerarolls",
        "kakera",
        "bool",
        _bool_options(),
        apply_group="kakera",
    ),
    CatalogEntry(
        "togglewishprotect",
        "Wishprotect",
        "$togglewishprotect",
        "kakera",
        "bool",
        _bool_options(),
        apply_group="kakera",
    ),
    CatalogEntry(
        "togglewishfree",
        "Freewish",
        "$togglewishfree",
        "kakera",
        "bool",
        _bool_options(),
        apply_group="kakera",
    ),
    CatalogEntry(
        "togglespheretrade",
        "Spheres trading",
        "$togglespheretrade",
        "spheres",
        "bool",
        _bool_options(),
        apply_group="spheres",
    ),
)

CATALOG_BY_FIELD: dict[str, CatalogEntry] = {entry.field: entry for entry in CATALOG}

SECTION_TITLES = {
    "meta": "Server",
    "general": "General",
    "rolls": "Rolls & timing",
    "ranking": "Ranking & roll display",
    "content": "Content filters",
    "snipe": "Sniping",
    "claims": "Claims & buttons",
    "kakera": "Kakera",
    "spheres": "Spheres",
}

SECTION_ORDER = (
    "meta",
    "general",
    "rolls",
    "ranking",
    "content",
    "snipe",
    "claims",
    "kakera",
    "spheres",
)


def _format_bool(value: Any) -> str:
    if value is None:
        return "—"
    return "enabled" if bool(value) else "disabled"


def _format_int_commas(num: int) -> str:
    return f"{num:,}"


def format_field_value(field: str, value: Any) -> str:
    if value is None:
        return "—"
    if field == "server_premium":
        tier = int(value)
        stars = "🌟" * tier if tier else ""
        return f"{stars} Server Premium {tier} {stars}".strip()
    if field == "prefix":
        return str(value)
    if field == "lang":
        return str(value)
    if field == "setclaim":
        return f"every {int(value)} min."
    if field == "setinterval":
        return f"xx:{int(value):02d}"
    if field == "shifthour":
        return f"by +{int(value)} min."
    if field == "settimer":
        return f"{int(value)} sec."
    if field in {"setkakerabonus", "setspherebonus"}:
        return f"+{int(value)}"
    if field == "togglebutton":
        return _TOGGLEBUTTON_LABELS.get(int(value), str(value))
    if field == "gamemode":
        return _GAMEMODE_LABELS.get(int(value), str(value))
    if field == "servlimroul" and isinstance(value, dict):
        return (
            f"{_format_int_commas(int(value['wa']))} $wa, "
            f"{_format_int_commas(int(value['ha']))} $ha, "
            f"{_format_int_commas(int(value['wg']))} $wg, "
            f"{_format_int_commas(int(value['hg']))} $hg"
        )
    if field in {"togglesnipe", "togglekakerasnipe"}:
        if isinstance(value, dict):
            mode = int(value.get("mode", 0))
            seconds = value.get("seconds")
            label = _SNIPE_MODE_LABELS.get(mode, str(mode))
            if seconds is not None:
                return f"{mode} ({label}, {seconds}s)"
            return f"{mode} ({label})"
        return str(value)
    if field == "haremlimit":
        return _format_int_commas(int(value))
    if isinstance(value, bool):
        return _format_bool(value)
    return str(value)


def format_settings_line(field: str, value: Any) -> str:
    entry = CATALOG_BY_FIELD.get(field)
    label = entry.label if entry else field
    display = format_field_value(field, value)
    cmd = entry.command if entry else f"${field}"
    suffix = f" ({cmd})" if cmd else ""
    if field == "servlimroul":
        return f"· {cmd} = {display}" if display != "—" else f"· {label}: —"
    return f"· {label}: {display}{suffix}"


def catalog_to_client_dict() -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    by_section: dict[str, list[dict[str, Any]]] = {}
    for entry in CATALOG:
        by_section.setdefault(entry.section, []).append(entry.to_dict())
    for section in SECTION_ORDER:
        rows = by_section.get(section)
        if rows:
            sections.append({"id": section, "title": SECTION_TITLES.get(section, section), "rows": rows})
    return {"sections": sections}


def fields_to_display_dict(fields: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_settings_fields(dict(fields or {}))
    sections: list[dict[str, Any]] = []
    by_section: dict[str, list[dict[str, Any]]] = {}
    for entry in CATALOG:
        value = normalized.get(entry.field)
        row = {
            "field": entry.field,
            "label": entry.label,
            "command": entry.command,
            "display": format_field_value(entry.field, value),
            "line": format_settings_line(entry.field, value),
            "has_value": value is not None,
            "value": value,
            "editor": entry.editor,
            "options": [dict(opt) for opt in entry.options],
            "min_value": entry.min_value,
            "max_value": entry.max_value,
            "apply_group": entry.apply_group,
        }
        by_section.setdefault(entry.section, []).append(row)
    for section in SECTION_ORDER:
        rows = by_section.get(section)
        if rows:
            sections.append({"id": section, "title": SECTION_TITLES.get(section, section), "rows": rows})
    return {"sections": sections, "field_count": len(normalized)}


def coerce_editor_value(field: str, raw: Any) -> Any:
    entry = CATALOG_BY_FIELD.get(field)
    if entry is None:
        return raw
    if raw is None:
        return None
    if entry.editor == "bool":
        if isinstance(raw, bool):
            return raw
        text = str(raw).lower()
        if text in {"enabled", "true", "yes", "1"}:
            return True
        if text in {"disabled", "false", "no", "0"}:
            return False
        return bool(raw)
    if entry.editor == "int":
        return int(raw)
    if entry.editor == "percent":
        return int(raw)
    if entry.editor == "enum":
        if entry.field == "lang":
            return str(raw)
        return int(raw)
    if entry.editor == "snipe":
        if isinstance(raw, dict):
            mode = int(raw.get("mode", 0))
            seconds = raw.get("seconds")
            return {"mode": mode, "seconds": float(seconds) if seconds is not None else None}
        return {"mode": int(raw), "seconds": None}
    if entry.editor == "servlimroul":
        if isinstance(raw, dict):
            return {
                "wa": int(raw["wa"]),
                "ha": int(raw["ha"]),
                "wg": int(raw["wg"]),
                "hg": int(raw["hg"]),
            }
        return raw
    if entry.editor == "text":
        return str(raw)
    return raw


def merge_preset_fields(
    base: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    out = normalize_settings_fields(dict(base))
    normalized_patch = normalize_settings_fields(dict(patch))
    for key, value in normalized_patch.items():
        if value is not None and key in CATALOG_BY_FIELD:
            out[key] = value
    return out
