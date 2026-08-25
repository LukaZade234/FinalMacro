"""Parse Mudae ``$bonus`` plain-text responses (often split across two messages).

Field identity is a meaning key (see ``bonus_catalog.py``), not the trailing
``($kt)`` / ``($bk)`` source tag. One bullet becomes one field.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.channel_cache import get_channel_settings, get_setrolls
from mudae.parsers.bonus_catalog import BONUS_META_KEYS
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

_ROLLS_PER_HOUR_RE = re.compile(r"rolls per hour\s*:", re.IGNORECASE)
_BONUS_SUM_RE = re.compile(r"rolls per hour\s*:\s*\+?(\d+)", re.IGNORECASE)
_PENALTY_RE = re.compile(r"-\s*(\d+)\s*\(\$([^)]+)\)")
_SOURCE_PART_RE = re.compile(
    r"(\d[\d,]*)\s+(?:"
    r"\$([a-zA-Z]+)"
    r"|server\s+premium(?:\s+\d+)?"
    r"|premium"
    r"|slash"
    r"|tuto"
    r")",
    re.IGNORECASE,
)
_DOLLAR_CMD_RE = re.compile(r"\$([a-zA-Z]+)")
_INTERVAL_RE = re.compile(r"this interval:\s*([\d.]+%)", re.IGNORECASE)

_EMOJI_RE = re.compile(r"<:\w+:\d+>\s*")
_LINE_RE = re.compile(r"^[·•]\s*(.+)$", re.MULTILINE)
_CMD_SUFFIX_RE = re.compile(r"\(\$([^)]+)\)\s*(?:\((?P<extra>[^)]+)\))?\s*$")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_COMPONENT_RE = re.compile(
    r"(?:\$)?(\w+(?:\s+\w+)?)\s*=\s*\*\*([^*]+)\*\*",
    re.IGNORECASE,
)
_SLUGIFY_RE = re.compile(r"[^a-z0-9]+")
_RANGE_RE = re.compile(r"^\d+-\d+$")
_PERCENT_RE = re.compile(r"^\+?(-?\d+(?:\.\d+)?)%$")
_MULT_RE = re.compile(r"^(\d+(?:\.\d+)?)x$", re.IGNORECASE)


def _normalize_content(content: str) -> str:
    text = _EMOJI_RE.sub("", content)
    return text.replace("\r\n", "\n")


def _slugify(text: str) -> str:
    slug = _SLUGIFY_RE.sub("_", text.lower()).strip("_")
    return slug[:64] or "bonus_line"


def _coerce_value(raw: str) -> Any:
    text = raw.strip().replace(",", "")
    if _RANGE_RE.fullmatch(text):
        lo, hi = text.split("-", 1)
        return {"min": int(lo), "max": int(hi)}
    pct = _PERCENT_RE.fullmatch(text)
    if pct:
        number = pct.group(1)
        return float(number) if "." in number else int(number)
    mult = _MULT_RE.fullmatch(text)
    if mult:
        number = mult.group(1)
        return float(number) if "." in number else int(number)
    signed = text[1:] if text[:1] in "+-" else text
    if signed.replace(".", "", 1).isdigit():
        number = text[1:] if text.startswith("+") else text
        return float(number) if "." in number else int(number)
    return raw.strip()


def _unique_key(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    index = 2
    while f"{base}_{index}" in used:
        index += 1
    key = f"{base}_{index}"
    used.add(key)
    return key


def _tag(tags: dict[str, str], key: str, source: str | list[str] | None) -> None:
    if not source:
        return
    if isinstance(source, list):
        tags[key] = ", ".join(source)
    else:
        tags[key] = source


def _source_name(match: re.Match[str]) -> str:
    cmd = match.group(2)
    if cmd:
        return cmd.lower()
    blob = match.group(0).lower()
    if "server" in blob:
        return "server_premium"
    if "slash" in blob:
        return "slash"
    if "tuto" in blob:
        return "tuto"
    return "premium"


def _parse_sources(plain: str) -> dict[str, int]:
    sources: dict[str, int] = {}
    for match in _SOURCE_PART_RE.finditer(plain):
        amount = int(match.group(1).replace(",", ""))
        sources[_source_name(match)] = amount
    return sources


def _parse_penalties(plain: str) -> dict[str, int]:
    penalties: dict[str, int] = {}
    for match in _PENALTY_RE.finditer(plain):
        cmd = match.group(2).strip().lstrip("$").split()[0].lower()
        penalties[cmd] = int(match.group(1))
    return penalties


def _bolds(body: str) -> list[Any]:
    return [_coerce_value(v) for v in _BOLD_RE.findall(body)]


def _headline(body: str) -> Any:
    values = _bolds(body)
    if values:
        return values[0]
    _, value = _label_and_value(body)
    return _coerce_value(value) if value else None


def _line_source_tags(body: str) -> list[str]:
    tags = [m.group(1).lower() for m in _DOLLAR_CMD_RE.finditer(body)]
    plain = strip_markdown(body).lower()
    extras: list[str] = []
    if re.search(r"\bslash\b", plain):
        extras.append("slash")
    if re.search(r"\bpremium\b", plain) and "premium" not in tags:
        extras.append("premium")
    seen: list[str] = []
    for item in tags + extras:
        if item not in seen:
            seen.append(item)
    return seen


def _parse_rolls_per_hour_line(line: str, base_setrolls: int | None) -> dict[str, Any]:
    plain = strip_markdown(line)
    if not _ROLLS_PER_HOUR_RE.search(plain):
        return {}

    bonus_match = _BONUS_SUM_RE.search(plain)
    if not bonus_match:
        return {}

    bonus_sum = int(bonus_match.group(1))
    sources = _parse_sources(plain)
    penalties = _parse_penalties(plain)
    penalty_total = sum(penalties.values())
    rolls: dict[str, Any] = {
        "bonus": bonus_sum,
        "sources": sources,
        "penalties": penalties,
    }
    if base_setrolls is not None:
        rolls["base"] = base_setrolls
        rolls["net"] = base_setrolls + bonus_sum - penalty_total
    else:
        rolls["unresolved"] = bonus_sum - penalty_total

    tags: dict[str, str] = {}
    _tag(tags, "rolls_per_hour", list(penalties) or None)
    return {"rolls_per_hour": rolls, "_source_tags": tags}


def _label_and_value(body: str) -> tuple[str, str]:
    if ":" in body:
        label, value = body.split(":", 1)
        return label.strip(), strip_markdown(value.strip())
    return body.strip(), strip_markdown(body.strip())


def _iter_bonus_lines(normalized: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for match in _LINE_RE.finditer(normalized):
        body = match.group(1).strip()
        key = strip_markdown(body)
        if body and key not in seen:
            seen.add(key)
            lines.append(body)
    for raw in normalized.split("\n"):
        body = strip_markdown(_EMOJI_RE.sub("", raw)).strip().lstrip("·•").strip()
        if not body or body in seen:
            continue
        if _ROLLS_PER_HOUR_RE.search(body):
            seen.add(body)
            lines.append(body)
    return lines


def _low(text: str) -> str:
    return text.lower()


def _parse_catalog_line(body: str, extras: list[str]) -> dict[str, Any] | None:
    """Return meaning-keyed fields, or None if this line is not catalogued."""
    lowered = _low(body)
    parsed: dict[str, Any] = {}
    tags: dict[str, str] = {}
    headline = _headline(body)
    line_tags = _line_source_tags(body)

    if "additional bonus for kakera buttons on starwish" in lowered:
        parsed["kakera_button_starwish_bonus_pct"] = headline
        _tag(tags, "kakera_button_starwish_bonus_pct", line_tags or "sw")
        parsed["_source_tags"] = tags
        return parsed

    if "additional bonus for kakera buttons" in lowered:
        parsed["kakera_button_bonus_pct"] = headline
        _tag(tags, "kakera_button_bonus_pct", line_tags or "bk")
        parsed["_source_tags"] = tags
        return parsed

    if "random kakera per light kakera" in lowered:
        rng = headline if isinstance(headline, dict) else {"min": headline, "max": headline}
        parsed["random_kakera"] = rng
        _tag(tags, "random_kakera", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "final value of red" in lowered:
        parsed["kakera_red_rainbow_bonus"] = headline
        _tag(tags, "kakera_red_rainbow_bonus", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "rarity of each reward from chaos" in lowered:
        parsed["chaos_kakera_rarity_mult"] = headline
        _tag(tags, "chaos_kakera_rarity_mult", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "initial value of chaos" in lowered:
        parsed["kakera_chaos_bonus"] = headline
        _tag(tags, "kakera_chaos_bonus", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "complete" in lowered and "bku" in lowered:
        chance: dict[str, Any] = {"value": headline}
        interval_text = " ".join(extras)
        match = _INTERVAL_RE.search(body) or _INTERVAL_RE.search(interval_text)
        if match:
            chance["this_interval_pct"] = _coerce_value(match.group(1))
        parsed["bku_complete_chance_pct"] = chance
        _tag(tags, "bku_complete_chance_pct", line_tags or "kl")
        parsed["_source_tags"] = tags
        return parsed

    if "additional key on wish" in lowered:
        parsed["extra_key_wish_chance_pct"] = headline
        _tag(tags, "extra_key_wish_chance_pct", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "additional key" in lowered:
        parsed["extra_key_chance_pct"] = headline
        _tag(tags, "extra_key_chance_pct", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "additional sphere sources" in lowered:
        sources: dict[str, Any] = {}
        for match in _COMPONENT_RE.finditer(body):
            slug = match.group(1).strip().lower().replace(" ", "_")
            sources[slug] = _coerce_value(match.group(2))
        parsed["additional_sphere_sources"] = sources
        _tag(tags, "additional_sphere_sources", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "additional spheres" in lowered and "source" not in lowered:
        parsed["additional_spheres"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "oh daily bonus" in lowered or lowered.startswith("$oh daily"):
        bolds = _bolds(body)
        oh: dict[str, Any] = {}
        if len(bolds) >= 1:
            oh["spheres"] = bolds[0]
        if len(bolds) >= 2:
            oh["oq_pct"] = bolds[1]
        if len(bolds) >= 3:
            oh["ot_pct"] = bolds[2]
        parsed["oh_daily"] = oh
        _tag(tags, "oh_daily", line_tags)
        parsed["_source_tags"] = tags
        return parsed

    if "megasphere" in lowered:
        bolds = _bolds(body)
        mega: dict[str, Any] = {}
        if len(bolds) >= 1:
            mega["rewards"] = bolds[0]
        if len(bolds) >= 2:
            mega["free_pct"] = bolds[1]
        parsed["megaspheres"] = mega
        _tag(tags, "megaspheres", line_tags or "shop")
        parsed["_source_tags"] = tags
        return parsed

    if "twice the sphere button value" in lowered:
        parsed["sphere_double_chance_pct"] = headline
        _tag(tags, "sphere_double_chance_pct", line_tags)
        parsed["_source_tags"] = tags
        return parsed

    if "wishlist slot" in lowered:
        parsed["wishlist_slots"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "wishseries slot" in lowered or "wish series slot" in lowered:
        parsed["wishseries_slots"] = headline
        _tag(tags, "wishseries_slots", line_tags or "premium")
        parsed["_source_tags"] = tags
        return parsed

    if "spawn bonus for wish" in lowered and "starwish" not in lowered:
        parsed["wish_spawn_bonus_pct"] = headline
        _tag(tags, "wish_spawn_bonus_pct", line_tags)
        parsed["_source_tags"] = tags
        return parsed

    if "spawn bonus for $starwish" in lowered or "spawn bonus for starwish" in lowered:
        parsed["starwish_spawn_bonus_pct"] = headline
        _tag(tags, "starwish_spawn_bonus_pct", line_tags)
        parsed["_source_tags"] = tags
        return parsed

    if "starwish slot" in lowered:
        parsed["starwish_slots"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "wishprotect" in lowered:
        parsed["wishprotect_spawn_chance"] = headline
        _tag(tags, "wishprotect_spawn_chance", line_tags or "kl")
        parsed["_source_tags"] = tags
        return parsed

    if "cooldown for $rt" in lowered or "cooldown for rt" in lowered:
        parsed["rt_cooldown"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "limroul" in lowered and "animanga" in lowered:
        parsed["limroul_animanga"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "limroul" in lowered and "game" in lowered:
        parsed["limroul_game"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "limroul" in lowered:
        bolds = _bolds(body)
        if len(bolds) >= 1:
            parsed["limroul_animanga"] = bolds[0]
        if len(bolds) >= 2:
            parsed["limroul_game"] = bolds[1]
        parsed["_source_tags"] = tags
        return parsed

    if "bronze iv" in lowered and "kakera" in lowered:
        parsed["rank_kakera_bonus_pct"] = headline
        _tag(tags, "rank_kakera_bonus_pct", line_tags or "kt")
        parsed["_source_tags"] = tags
        return parsed

    if "kakera earned" in lowered:
        bolds = _bolds(body)
        if len(bolds) >= 2:
            parsed["kakera_earned_bonus_pct"] = {
                "premium_slash": bolds[0],
                "server_premium": bolds[1],
            }
        else:
            parsed["kakera_earned_bonus_pct"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "gold key" in lowered:
        parsed["kakera_gold_keys_bonus"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "cooldown for $dk" in lowered or "cooldown for dk" in lowered:
        parsed["dk_cooldown"] = headline
        parsed["_source_tags"] = tags
        return parsed

    if "mk per hour" in lowered:
        parsed["mk_per_hour"] = headline
        _tag(tags, "mk_per_hour", "mk")
        parsed["_source_tags"] = tags
        return parsed

    if "kakera max power" in lowered or "max power" in lowered:
        parsed["kakera_max_power"] = headline
        _tag(tags, "kakera_max_power", line_tags)
        parsed["_source_tags"] = tags
        return parsed

    if "power cost per kakera button" in lowered:
        parsed["power_cost_per_kakera_button"] = headline
        parsed["_source_tags"] = tags
        return parsed

    return None


def _parse_line(
    line: str,
    used: set[str],
    *,
    base_setrolls: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return (fields, catalogued). ``catalogued`` is False for generic fallback."""
    body = line.strip()
    extras: list[str] = []

    if _ROLLS_PER_HOUR_RE.search(body):
        row = _parse_rolls_per_hour_line(body, base_setrolls)
        for key in row:
            if key != "_source_tags":
                used.add(key)
        return row, True

    cmd_match = _CMD_SUFFIX_RE.search(body)
    if cmd_match and cmd_match.group("extra"):
        extras.append(cmd_match.group("extra").strip())

    catalogued = _parse_catalog_line(body, extras)
    if catalogued is not None:
        tags = catalogued.pop("_source_tags", {})
        for key in catalogued:
            used.add(key)
        if tags:
            catalogued["_source_tags"] = tags
        return catalogued, True

    label, value_text = _label_and_value(body)
    bold_values = _bolds(body)
    if not bold_values and value_text:
        bold_values = [_coerce_value(value_text)]

    parsed: dict[str, Any] = {}
    base_key = _slugify(label)
    if len(bold_values) == 1:
        parsed[_unique_key(base_key, used)] = bold_values[0]
    elif bold_values:
        parsed[_unique_key(base_key, used)] = bold_values
    return parsed, False


def merge_bonus_fields(*parts: dict[str, Any]) -> dict[str, Any]:
    """Merge 1/2 + 2/2 (or a stored sheet + a new part) by meaning key."""
    out: dict[str, Any] = {}
    source_tags: dict[str, str] = {}
    unparsed: list[str] = []
    line_count = 0
    for part in parts:
        if not part:
            continue
        for key, value in part.items():
            if key == "line_count":
                try:
                    line_count += int(value or 0)
                except (TypeError, ValueError):
                    pass
                continue
            if key in BONUS_META_KEYS and key not in {"source_tags", "unparsed_lines"}:
                continue
            if key == "source_tags" and isinstance(value, dict):
                source_tags.update(value)
                continue
            if key == "unparsed_lines" and isinstance(value, list):
                unparsed.extend(str(item) for item in value)
                continue
            out[key] = value
    if line_count:
        out["line_count"] = line_count
    if source_tags:
        out["source_tags"] = source_tags
    if unparsed:
        out["unparsed_lines"] = unparsed
    return out


def parse_bonus(
    content: str,
    *,
    part: int = 1,
    parts: int = 1,
    channel_id: int | None = None,
) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {"part": part, "parts": parts}
    used: set[str] = set()
    source_tags: dict[str, str] = {}
    unparsed_lines: list[str] = []
    line_count = 0
    base_setrolls: int | None = None
    if channel_id is not None:
        cached_settings = get_channel_settings(channel_id)
        if cached_settings:
            fields["cached_settings"] = True
            base_setrolls = get_setrolls(channel_id)
        else:
            fields["cached_settings"] = False

    normalized = _normalize_content(content)
    for body in _iter_bonus_lines(normalized):
        row, catalogued = _parse_line(body, used, base_setrolls=base_setrolls)
        if not row:
            warnings.append(f"Unparsed bonus line: {body[:120]}")
            unparsed_lines.append(body)
            continue
        line_count += 1
        tags = row.pop("_source_tags", {})
        if isinstance(tags, dict):
            source_tags.update(tags)
        if not catalogued:
            warnings.append(f"Unknown bonus line (stored under fallback key): {body[:120]}")
            unparsed_lines.append(body)
        for key, value in row.items():
            if key in fields and fields[key] != value:
                warnings.append(f"Duplicate bonus field {key!r}; keeping first")
                continue
            fields[key] = value

    if base_setrolls is None and isinstance(fields.get("rolls_per_hour"), dict):
        if "unresolved" in fields["rolls_per_hour"]:
            warnings.append(
                "No cached $settings for this channel — run $settings first "
                "(setrolls is saved automatically after parsing)"
            )

    fields["line_count"] = line_count
    if source_tags:
        fields["source_tags"] = source_tags
    if unparsed_lines:
        fields["unparsed_lines"] = unparsed_lines
    if line_count == 0:
        warnings.append("No bonus lines matched")

    summary = _build_summary(fields)
    return ParseResult(
        kind=MessageKind.BONUS,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def _rolls_net(fields: dict[str, Any]) -> Any:
    rolls = fields.get("rolls_per_hour")
    if isinstance(rolls, dict):
        return rolls.get("net", rolls.get("unresolved"))
    return rolls


def _build_summary(fields: dict[str, Any]) -> str:
    count = fields.get("line_count", 0)
    if not count:
        return "$bonus"
    highlights: list[str] = []
    net = _rolls_net(fields)
    if net is not None:
        highlights.append(f"rolls/h {net}")
    if "kakera_max_power" in fields:
        highlights.append(f"power {fields['kakera_max_power']}")
    if "kakera_button_bonus_pct" in fields:
        highlights.append(f"kakera btn {fields['kakera_button_bonus_pct']}%")
    elif "additional_spheres" in fields:
        highlights.append(f"SP +{fields['additional_spheres']}")
    tail = f"{count} lines"
    if highlights:
        return f"$bonus · {', '.join(highlights[:3])} · {tail}"
    return f"$bonus · {tail}"
