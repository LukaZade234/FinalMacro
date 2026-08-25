"""Visible text on a Discord message, including Components V2 bodies.

discord.py-self 2.1 only understands action-row components (types 1–4).
Mudae ``$shop`` (and similar sheets) use Components V2: Container / Section /
TextDisplay / Thumbnail. Those have empty ``content`` and empty classic
embeds; the library drops the unknown types, so we keep the raw payload and
flatten ``content`` fields ourselves.
"""

from __future__ import annotations

from typing import Any

# Discord component types that carry nested children.
_NEST_KEYS = ("components", "items", "accessory")


def flatten_component_text(components: Any) -> str:
    """Join every ``content`` string found in a Components V2 payload."""
    parts: list[str] = []
    _walk(components, parts)
    return "\n".join(part for part in parts if part)


def _walk(node: Any, parts: list[str]) -> None:
    if node is None:
        return
    if isinstance(node, str):
        return
    if isinstance(node, list):
        for child in node:
            _walk(child, parts)
        return
    if not isinstance(node, dict):
        return
    content = node.get("content")
    if isinstance(content, str) and content.strip():
        parts.append(content.strip())
    for key in _NEST_KEYS:
        child = node.get(key)
        if child is not None:
            _walk(child, parts)


def snapshot_visible_text(snapshot: Any) -> str:
    """Plain content + embed fields + flattened Components V2 text."""
    parts: list[str] = [getattr(snapshot, "content", None) or ""]
    for embed in getattr(snapshot, "embeds", None) or []:
        if not isinstance(embed, dict):
            continue
        for key in ("description", "title", "footer", "author"):
            value = embed.get(key) or ""
            if value:
                parts.append(str(value))
    extra = flatten_component_text(getattr(snapshot, "components", None))
    if extra:
        parts.append(extra)
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        text = str(part).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return "\n".join(unique)
