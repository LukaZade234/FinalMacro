"""Parse Mudae $bonus plain-text responses (often split across two messages)."""

from __future__ import annotations

import re
from typing import Any

from mudae.channel_cache import get_channel_settings, get_setrolls
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

_ROLLS_PER_HOUR_RE = re.compile(r"rolls per hour\s*:", re.IGNORECASE)
_BONUS_SUM_RE = re.compile(r"rolls per hour\s*:\s*\+(\d+)", re.IGNORECASE)
_PENALTY_RE = re.compile(r"-\s*(\d+)\s*\(\$([^)]+)\)")

# Strip custom emoji tokens; lines are bullet rows.
_EMOJI_RE = re.compile(r"<:\w+:\d+>\s*")
_LINE_RE = re.compile(r"^[·•]\s*(.+)$", re.MULTILINE)
_CMD_SUFFIX_RE = re.compile(r"\(\$([^)]+)\)\s*(?:\((?P<extra>[^)]+)\))?\s*$")
_ALT_CMD_RE = re.compile(r"\((\d+)\s+\$(\w+)\)\s*$")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_COMPONENT_RE = re.compile(
    r"(?:\$)?(\w+(?:\s+\w+)?)\s*=\s*\*\*([^*]+)\*\*",
    re.IGNORECASE,
)
_SLUGIFY_RE = re.compile(r"[^a-z0-9]+")
_RANGE_RE = re.compile(r"\d+-\d+")
_PERCENT_RE = re.compile(r"\+?(\d+(?:\.\d+)?)%")
_INTERVAL_PCT_RE = re.compile(r"([\d.]+%)")


def _normalize_content(content: str) -> str:
    text = _EMOJI_RE.sub("", content)
    return text.replace("\r\n", "\n")


def _command_keys(suffix: str) -> list[str]:
    keys: list[str] = []
    for part in suffix.split("/"):
        key = part.strip().lstrip("$").split()[0]
        if key:
            keys.append(key)
    return keys


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
    if text.startswith("+") and text[1:].replace(".", "", 1).isdigit():
        return float(text[1:]) if "." in text else int(text[1:])
    if text.replace(".", "", 1).isdigit():
        return float(text) if "." in text else int(text)
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


def _parse_rolls_per_hour_line(line: str, base_setrolls: int | None) -> dict[str, Any]:
    """Parse rolls-per-hour bonus line with ($bw)/($bk) penalties.

    rolls_per_hour = setrolls_base + bonus_sum - sum(penalties)
    """
    plain = strip_markdown(line)
    if not _ROLLS_PER_HOUR_RE.search(plain):
        return {}

    bonus_match = _BONUS_SUM_RE.search(plain)
    if not bonus_match:
        return {}

    bonus_sum = int(bonus_match.group(1))
    parsed: dict[str, Any] = {"rolls_per_hour_bonus_sum": bonus_sum}

    for match in _PENALTY_RE.finditer(plain):
        cmd = match.group(2).strip().lstrip("$").split()[0].lower()
        parsed[cmd] = int(match.group(1))

    penalty_total = sum(
        value for key, value in parsed.items() if key not in {"rolls_per_hour_bonus_sum"}
    )

    if base_setrolls is not None:
        parsed["setrolls_base"] = base_setrolls
        parsed["rolls_per_hour"] = base_setrolls + bonus_sum - penalty_total
    else:
        parsed["rolls_per_hour_unresolved"] = bonus_sum - penalty_total

    return parsed


def _parse_line(
    line: str,
    used: set[str],
    *,
    base_setrolls: int | None = None,
) -> dict[str, Any]:
    body = line.strip()
    if _ROLLS_PER_HOUR_RE.search(body):
        parsed = _parse_rolls_per_hour_line(body, base_setrolls)
        for key in parsed:
            used.add(key)
        return parsed

    parsed: dict[str, Any] = {}
    extras: list[str] = []
    commands: list[str] = []

    cmd_match = _CMD_SUFFIX_RE.search(body)
    if cmd_match:
        commands = _command_keys(cmd_match.group(1))
        if cmd_match.group("extra"):
            extras.append(cmd_match.group("extra").strip())
        body = body[: cmd_match.start()].strip()

    alt = _ALT_CMD_RE.search(body)
    if alt:
        commands = commands or [alt.group(2).lower()]
        extras.append(f"rolls_{alt.group(1)}")
        body = body[: alt.start()].strip()

    label, value_text = _label_and_value(body)
    if commands and commands[0] not in used:
        base_key = commands[0]
    else:
        base_key = _slugify(label)

    components: dict[str, Any] = {}
    for match in _COMPONENT_RE.finditer(body):
        comp = match.group(1).strip().lower().replace(" ", "_")
        components[comp] = _coerce_value(match.group(2))

    if components:
        for comp, val in components.items():
            key = _unique_key(f"{base_key}_{comp}", used)
            parsed[key] = val
        return parsed

    bold_values = [_coerce_value(v) for v in _BOLD_RE.findall(body)]
    if not bold_values:
        plain = strip_markdown(value_text)
        if plain:
            bold_values = [_coerce_value(plain)]

    if len(bold_values) == 1:
        parsed[_unique_key(base_key, used)] = bold_values[0]
    elif bold_values:
        names = ["primary", "secondary", "tertiary"]
        for index, val in enumerate(bold_values):
            suffix = names[index] if index < len(names) else str(index + 1)
            parsed[_unique_key(f"{base_key}_{suffix}", used)] = val

    if extras:
        for extra in extras:
            if "interval" in extra.lower():
                match = _INTERVAL_PCT_RE.search(extra)
                if match:
                    parsed[_unique_key(f"{base_key}_interval", used)] = _coerce_value(
                        match.group(1)
                    )
            elif extra.startswith("rolls_"):
                parsed[_unique_key(f"{base_key}_{extra}", used)] = int(extra.split("_", 1)[1])

    return parsed


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
        if body and body not in seen:
            seen.add(body)
            lines.append(body)
    for raw in normalized.split("\n"):
        body = strip_markdown(_EMOJI_RE.sub("", raw)).strip().lstrip("·•").strip()
        if not body or body in seen:
            continue
        if _ROLLS_PER_HOUR_RE.search(body):
            seen.add(body)
            lines.append(body)
    return lines


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
        row = _parse_line(body, used, base_setrolls=base_setrolls)
        if not row:
            continue
        line_count += 1
        for key, value in row.items():
            if key in fields and fields[key] != value:
                warnings.append(f"Duplicate bonus field {key!r}; keeping first")
                continue
            fields[key] = value

    if base_setrolls is None and any(
        key in fields for key in ("rolls_per_hour_bonus_sum", "rolls_per_hour_unresolved")
    ):
        warnings.append(
            "No cached $settings for this channel — run $settings first "
            "(setrolls is saved automatically after parsing)"
        )

    fields["line_count"] = line_count
    if line_count == 0:
        warnings.append("No bonus lines matched")

    summary = _build_summary(fields)
    return ParseResult(
        kind=MessageKind.BONUS,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def _build_summary(fields: dict[str, Any]) -> str:
    count = fields.get("line_count", 0)
    if not count:
        return "$bonus"
    highlights: list[str] = []
    if "rolls_per_hour" in fields:
        highlights.append(f"rolls/h {fields['rolls_per_hour']}")
    for key in ("bk", "sw", "bw", "kl"):
        if key in fields:
            val = fields[key]
            suffix = "%" if isinstance(val, (int, float)) and key in {"bk", "sw", "kl"} else ""
            highlights.append(f"{key} {val}{suffix}")
    tail = f"{count} lines"
    if highlights:
        return f"$bonus · {', '.join(highlights[:3])} · {tail}"
    return f"$bonus · {tail}"
