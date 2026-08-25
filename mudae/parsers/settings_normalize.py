"""Normalize raw ``$settings`` parser output into typed values for diff/apply."""

from __future__ import annotations

import re
from typing import Any

_SERVLIM_LIMITS_RE = re.compile(
    r"([\d,]+)\s*\$wa.*?([\d,]+)\s*\$ha.*?([\d,]+)\s*\$wg.*?([\d,]+)\s*\$hg",
    re.IGNORECASE,
)
_DIGITS_ONLY_RE = re.compile(r"[^\d]")
_LONE_DIGIT_RE = re.compile(r"\d+")

_TOGGLEBUTTON_MAP = {
    "for public wishes only": 0,
    "public wishes only": 0,
    "never automatically added": 1,
    "buttons are never": 1,
    "for all your rolls": 2,
    "all your rolls": 2,
    "everyone": 2,
}


def _parse_int(text: str) -> int:
    return int(_DIGITS_ONLY_RE.sub("", text))


def parse_servlimroul(raw: Any) -> dict[str, int] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        keys = ("wa", "ha", "wg", "hg")
        if all(k in raw for k in keys):
            return {k: int(raw[k]) for k in keys}
        return None
    text = str(raw)
    match = _SERVLIM_LIMITS_RE.search(text)
    if not match:
        return None
    return {
        "wa": _parse_int(match.group(1)),
        "ha": _parse_int(match.group(2)),
        "wg": _parse_int(match.group(3)),
        "hg": _parse_int(match.group(4)),
    }


def parse_togglebutton(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int) and raw in (0, 1, 2):
        return raw
    lower = str(raw).lower()
    for needle, value in _TOGGLEBUTTON_MAP.items():
        if needle in lower:
            return value
    lone = _LONE_DIGIT_RE.fullmatch(str(raw).strip())
    if lone:
        num = int(lone.group(0))
        if num in (0, 1, 2):
            return num
    return None


def parse_kakera_calc_flag(raw: Any) -> bool | None:
    """``$togglekakeraclaim`` / ``$togglekakeralike`` print a mode sentence, not yes/no."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    lower = str(raw).lower().strip()
    if lower in {"enabled", "yes", "true"}:
        return True
    if lower in {"disabled", "no", "false"}:
        return False
    if "claim" in lower or "like" in lower or "rank" in lower:
        return True
    return None


def parse_togglerolls_display(raw: Any) -> tuple[bool | None, bool | None]:
    """Return ``(claim_rolls_display, like_rolls_display)`` from the aggregate label."""
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return raw, raw
    lower = str(raw).lower().strip()
    if lower in {"none", "no", "no ranks", "disabled"}:
        return False, False
    if "like ranks only" in lower:
        return False, True
    if "claim ranks only" in lower or lower == "claims only":
        return True, False
    if "claims and likes" in lower or "claim and like" in lower:
        return True, True
    return None, None


def parse_snipe_value(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict) and "mode" in raw:
        return {"mode": int(raw["mode"]), "seconds": raw.get("seconds")}
    if isinstance(raw, int):
        return {"mode": raw, "seconds": None}
    text = str(raw).strip()
    parts = text.split()
    mode = int(parts[0]) if parts else 0
    seconds = float(parts[1]) if len(parts) > 1 else None
    return {"mode": mode, "seconds": seconds}


def normalize_settings_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``fields`` with normalized types for apply/diff."""
    out = dict(fields)

    servlim = parse_servlimroul(out.get("servlimroul"))
    if servlim is not None:
        out["servlimroul"] = servlim

    btn = parse_togglebutton(out.get("togglebutton"))
    if btn is not None:
        out["togglebutton"] = btn

    claim_disp, like_disp = parse_togglerolls_display(out.get("togglerolls"))
    if claim_disp is not None and out.get("toggleclaimrolls") is None:
        out["toggleclaimrolls"] = claim_disp
    if like_disp is not None and out.get("togglelikerolls") is None:
        out["togglelikerolls"] = like_disp

    for snipe_key in ("togglesnipe", "togglekakerasnipe"):
        parsed = parse_snipe_value(out.get(snipe_key))
        if parsed is not None:
            out[snipe_key] = parsed

    for bool_key in (
        "toggleslash",
        "toggleclaimrank",
        "togglelikerank",
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
        "claimreact",
        "kakerabutton",
        "spherebutton",
        "toggleclaimrolls",
        "togglelikerolls",
    ):
        val = out.get(bool_key)
        if bool_key in {"togglekakeraclaim", "togglekakeralike"}:
            parsed_flag = parse_kakera_calc_flag(val)
            if parsed_flag is not None:
                out[bool_key] = parsed_flag
            continue
        if isinstance(val, str):
            lower = val.lower()
            if lower in {"enabled", "yes", "true"}:
                out[bool_key] = True
            elif lower in {"disabled", "no", "false"}:
                out[bool_key] = False

    return out
