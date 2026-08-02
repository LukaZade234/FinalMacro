"""Parse Mudae $settings plain-text responses."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.settings_normalize import normalize_settings_fields
from mudae.types import MessageKind, ParseResult

_BULLET_RE = re.compile(r"^[·•]\s*(.+)$", re.MULTILINE)
_CMD_SUFFIX_RE = re.compile(r"\(\$([^)]+)\)\s*$")
_PREMIUM_RE = re.compile(r"server premium\s*(\d+)", re.IGNORECASE)
_SERVLIM_RE = re.compile(
    r"\$servlimroul\s*=\s*(.+)$",
    re.IGNORECASE,
)
_MARKDOWN_RE = re.compile(r"\*\*([^*]*)\*\*|__([^_]*)__")

# Known keys across game modes; missing lines stay null in output.
SETTINGS_FIELD_KEYS: tuple[str, ...] = (
    "server_premium",
    "prefix",
    "lang",
    "setclaim",
    "setinterval",
    "shifthour",
    "setrolls",
    "settimer",
    "setrare",
    "setkakerabonus",
    "setspherebonus",
    "gamemode",
    "servlimroul",
    "channelinstance",
    "toggleslash",
    "toggleclaimrank",
    "togglelikerank",
    "togglerolls",
    "toggleclaimrolls",
    "togglelikerolls",
    "togglensfw",
    "toggledisturbing",
    "togglechildtag",
    "togglesnipe",
    "togglekakerasnipe",
    "haremlimit",
    "removecopylimit",
    "togglebutton",
    "claimreact",
    "kakerabutton",
    "spherebutton",
    "togglekakeratrade",
    "togglekakeraclaim",
    "togglekakeralike",
    "togglekakerarolls",
    "togglewishprotect",
    "togglewishfree",
    "togglespheretrade",
)


def _empty_settings_fields() -> dict[str, Any]:
    return {key: None for key in SETTINGS_FIELD_KEYS}


def _command_keys(suffix: str) -> list[str]:
    keys: list[str] = []
    for part in suffix.split("/"):
        key = part.strip().lstrip("$").split()[0]
        if key:
            keys.append(key)
    return keys


def _strip_markdown(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return match.group(1) or match.group(2) or ""

    cleaned = _MARKDOWN_RE.sub(repl, text)
    return cleaned.replace("****", "").strip()


def _label_and_value(body: str) -> tuple[str, str]:
    body = body.strip()
    if ":" in body:
        label, value = body.split(":", 1)
        return label.strip(), _strip_markdown(value.strip())
    if "=" in body:
        label, value = body.split("=", 1)
        return label.strip(), _strip_markdown(value.strip())
    return body, _strip_markdown(body)


def _coerce_value(raw: str) -> Any:
    text = raw.strip()
    lower = text.lower()
    if lower == "enabled":
        return True
    if lower == "disabled":
        return False
    if lower in {"no", "yes"}:
        return lower == "yes"

    every_min = re.search(r"every\s+(\d[\d,]*)\s*min", lower)
    if every_min:
        return int(every_min.group(1).replace(",", ""))

    exact_min = re.search(r"xx:\s*(\d+)", lower)
    if exact_min:
        return int(exact_min.group(1))

    # "Reset shifted: by +N min. ($shifthour)" — despite the command name this is
    # MINUTES past the hour for the server's hourly reset, not an hour of the day.
    # Daily counters (perk 8, spheres) always reset at 00:00 UTC regardless.
    shifted = re.search(r"by\s*\+?\s*(\d+)\s*min", lower)
    if shifted:
        return int(shifted.group(1))

    sec = re.search(r"(\d[\d,]*)\s*sec", lower)
    if sec:
        return int(sec.group(1).replace(",", ""))

    plus_num = re.match(r"\+(\d[\d,]*)", text)
    if plus_num:
        return int(plus_num.group(1).replace(",", ""))

    plain_num = re.fullmatch(r"[\d,]+", text)
    if plain_num:
        return int(text.replace(",", ""))

    lone_int = re.fullmatch(r"\d+", text)
    if lone_int:
        return int(text)

    return text


def _parse_bullet_line(line: str) -> dict[str, Any]:
    cmd_match = _CMD_SUFFIX_RE.search(line)
    if cmd_match:
        keys = _command_keys(cmd_match.group(1))
        body = line[: cmd_match.start()].strip()
    else:
        servlim = _SERVLIM_RE.search(line)
        if servlim:
            return {"servlimroul": servlim.group(1).strip()}
        return {}

    _label, raw_value = _label_and_value(body)
    value = _coerce_value(raw_value)
    if not keys:
        return {}
    return {key: value for key in keys}


def parse_settings(content: str) -> ParseResult:
    warnings: list[str] = []
    fields = _empty_settings_fields()

    premium_match = _PREMIUM_RE.search(content)
    if premium_match:
        fields["server_premium"] = int(premium_match.group(1))

    parsed_lines = 0
    for match in _BULLET_RE.finditer(content):
        row = _parse_bullet_line(match.group(1))
        if not row:
            continue
        parsed_lines += 1
        for key, value in row.items():
            if key not in fields:
                fields[key] = value
                continue
            if fields[key] is not None and fields[key] != value:
                warnings.append(f"Duplicate setting {key!r}; keeping first value")
                continue
            fields[key] = value

    if parsed_lines == 0:
        warnings.append("No settings bullet lines matched")

    fields = normalize_settings_fields(fields)
    summary = _build_summary(fields)
    return ParseResult(
        kind=MessageKind.SETTINGS,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def _build_summary(fields: dict[str, Any]) -> str:
    parts: list[str] = ["$settings"]
    if fields.get("server_premium") is not None:
        parts.append(f"Premium {fields['server_premium']}")
    if fields.get("prefix") is not None:
        parts.append(f"prefix {fields['prefix']!r}")
    if fields.get("lang") is not None:
        parts.append(str(fields["lang"]))
    if fields.get("setclaim") is not None:
        parts.append(f"claim {fields['setclaim']}m")
    if fields.get("setrolls") is not None:
        parts.append(f"{fields['setrolls']} rolls/h")
    if fields.get("gamemode") is not None:
        parts.append(f"mode {fields['gamemode']}")
    return " · ".join(parts)
