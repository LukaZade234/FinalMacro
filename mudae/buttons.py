"""Classify Mudae message buttons (claim reacts, kakera, spheres, etc.)."""

from __future__ import annotations

import re
from typing import Any

from mudae.constants import CLAIM_EMOJIS, KAKERA_EMOJIS, SPHERE_EMOJI_PREFIX

_SPHERE_CUSTOM_ID_RE = re.compile(r"\d+s\d+$")
_CLAIM_CUSTOM_ID_RE = re.compile(r"\d+p\d+p\d+$", re.IGNORECASE)


def classify_button_kind(
    *,
    emoji: str = "",
    label: str = "",
    custom_id: str = "",
) -> str:
    """Return ``claim``, ``kakera``, ``sphere``, or ``other`` for a component button."""
    emoji_key = (emoji or "").strip()
    cid = (custom_id or "").strip()

    if cid and _CLAIM_CUSTOM_ID_RE.search(cid):
        return "claim"
    if cid and _SPHERE_CUSTOM_ID_RE.search(cid):
        return "sphere"
    if emoji_key == SPHERE_EMOJI_PREFIX:
        return "sphere"
    if (
        emoji_key.startswith(SPHERE_EMOJI_PREFIX)
        and len(emoji_key) >= 3
        and emoji_key[2].isalpha()
    ):
        return "sphere"

    if emoji_key in CLAIM_EMOJIS:
        return "claim"
    if emoji_key in KAKERA_EMOJIS or emoji_key.startswith("kakera"):
        return "kakera"

    lower_label = (label or "").lower()
    if "claim" in lower_label or "marry" in lower_label or "casar" in lower_label:
        return "claim"
    return "other"


_STYLE_BY_VALUE = {
    1: "primary",
    2: "secondary",
    3: "success",
    4: "danger",
}


def normalize_button_style(raw: object) -> str:
    """Discord button colour: ``primary`` is the blurple pressed-cell highlight."""
    if raw is None or raw == "":
        return ""
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, int):
        return _STYLE_BY_VALUE.get(raw, str(raw))
    name = getattr(raw, "name", None)
    value = getattr(raw, "value", None)
    if name:
        text = str(name).strip().lower()
        if text in {"primary", "blurple"}:
            return "primary"
        return text
    if value is not None:
        try:
            return _STYLE_BY_VALUE.get(int(value), str(value))
        except (TypeError, ValueError):
            pass
    text = str(raw).strip().lower()
    if text in {"1", "primary", "blurple"}:
        return "primary"
    if text.isdigit():
        try:
            return _STYLE_BY_VALUE.get(int(text), text)
        except ValueError:
            return text
    return text


def is_pressed_grid_style(button: dict[str, Any] | None) -> bool:
    if not button:
        return False
    return normalize_button_style(button.get("style")) == "primary"


def button_styles_from_raw(components: Any) -> dict[str, str]:
    """Map ``custom_id`` → Discord style from the raw component payload."""
    styles: dict[str, str] = {}

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return
        try:
            kind = int(node.get("type") or 0)
        except (TypeError, ValueError):
            kind = 0
        if kind == 2:
            custom_id = str(node.get("custom_id") or "")
            if custom_id:
                styles[custom_id] = normalize_button_style(node.get("style"))
        for key in ("components", "items"):
            child = node.get(key)
            if child is not None:
                walk(child)

    walk(components)
    return styles


def is_claim_button(btn: dict[str, Any]) -> bool:
    if btn.get("kind") == "claim":
        return True
    return (
        classify_button_kind(
            emoji=btn.get("emoji") or "",
            label=btn.get("label") or "",
            custom_id=btn.get("custom_id") or "",
        )
        == "claim"
    )


def is_kakera_button(btn: dict[str, Any]) -> bool:
    if btn.get("kind") == "kakera":
        return True
    return (
        classify_button_kind(
            emoji=btn.get("emoji") or "",
            label=btn.get("label") or "",
            custom_id=btn.get("custom_id") or "",
        )
        == "kakera"
    )


def is_sphere_button(btn: dict[str, Any]) -> bool:
    if btn.get("kind") == "sphere":
        return True
    return (
        classify_button_kind(
            emoji=btn.get("emoji") or "",
            label=btn.get("label") or "",
            custom_id=btn.get("custom_id") or "",
        )
        == "sphere"
    )


def format_button(btn: dict[str, Any]) -> dict[str, Any]:
    """Normalize button metadata for parsers and future macro clickers."""
    emoji = btn.get("emoji") or ""
    label = btn.get("label") or ""
    custom_id = btn.get("custom_id") or None
    kind = classify_button_kind(
        emoji=emoji,
        label=label,
        custom_id=custom_id or "",
    )
    disabled = bool(btn.get("disabled", False))
    style = normalize_button_style(btn.get("style"))

    return {
        "label": label or None,
        "emoji": emoji or None,
        "kind": kind,
        "is_claim": kind == "claim",
        "is_kakera": kind == "kakera",
        "is_sphere": kind == "sphere",
        "custom_id": custom_id,
        "disabled": disabled,
        "style": style,
        "interaction": "click",
    }
