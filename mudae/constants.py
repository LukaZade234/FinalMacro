"""Mudae bot constants."""

from __future__ import annotations

import re

BOT_NAME = "Mudae"
# Official Mudae bot + common alternate application IDs (servers may differ).
TARGET_BOT_ID = 432618578496954900
MUDAE_BOT_IDS = frozenset({
    TARGET_BOT_ID,
    432610292342587392,
})

CLAIM_EMOJIS = frozenset({"💍", "💖", "💝", "\U0001f498"})

# Servers (or users) with claim buttons switched off claim by *reacting* to the
# roll instead. Mudae accepts any emoji there, so the macro uses the green tick
# it already knows — the same mark Mudae reacts with to acknowledge a command.
CLAIM_REACTION_EMOJI = "\u2705"

# Sphere button emoji names (sp + color letter, e.g. spY).
# Optional trailing digits are colour-blind variants (``spB2`` = blue with a
# letter in the corner). Same colour as the unsuffixed name.
SPHERE_EMOJI_PREFIX = "sp"
SPHERE_EMOJI_NAME_PATTERN = r"sp[A-Za-z]?\d*"
_COLORBLIND_SPHERE_RE = re.compile(r"^(sp)([A-Za-z])\d+$", re.IGNORECASE)
# Roll react buttons use bare ``:sp:`` when recognizable sphere buttons are off.
SPHERE_ROLL_DEFAULT_EMOJI = "sp"
# Filter ids that should match a bare ``:sp:`` roll react button.
SPHERE_ROLL_DEFAULT_FILTER_IDS = frozenset({"sp", "spR"})

# --- $oh sphere minigame ---------------------------------------------------
# Face-down (not yet revealed) grid button.
SPHERE_HIDDEN_EMOJI = "spU"
# Free to click — does not consume the daily $oh click allowance (includes
# purple revealed when a dark sphere transforms).
SPHERE_FREE_EMOJIS = frozenset({"spP"})
# Megasphere on normal roll react buttons — always click when present (free
# bonus; splits into many rewards like white kakera).
SPHERE_ROLL_FREE_EMOJIS = frozenset({"spM"})
# Blue/teal are the lowest paid values but never worth a $oh click — prefer
# face-down buttons instead. Once revealed they are skipped even though they
# would unveil more hidden spheres if clicked.
SPHERE_REVEAL_EMOJIS = frozenset({"spB", "spT"})
# Paid-sphere value ranking (higher = click first among revealed $oh spheres).
# Bare ``sp`` is red (Mudae's default sphere emoji in descriptions).
# Blue/teal ranks are for logging only — ``SPHERE_REVEAL_EMOJIS`` skips them
# in ``$oh``. Unknown ``sp*`` types default to rank 0.
SPHERE_VALUE_RANK = {
    "spB": 1,  # blue — lowest
    "spT": 2,  # teal
    "spG": 3,  # green
    "spY": 4,  # yellow
    "spD": 5,  # dark
    "spL": 6,  # light
    "spO": 7,  # orange
    "spR": 8,  # red
    "sp": 8,   # red (default emoji)
    "spW": 9,  # rainbow — highest
}

# Human-readable sphere categories (for docs / logging).
SPHERE_OH_TYPE_LABELS = {
    "spU": "Hidden (face-down)",
    "spP": "Purple (free $oh click)",
    "spM": "Megasphere (free roll bonus)",
    "spB": "Blue (skip in $oh — too low value)",
    "spT": "Teal (skip in $oh — too low value)",
    "spG": "Green",
    "spY": "Yellow",
    "spD": "Dark",
    "spL": "Light",
    "spO": "Orange",
    "spR": "Red",
    "sp": "Red (default emoji)",
    "spW": "Rainbow",
}

# Base SP with no bonuses. Minigame logs and the $oq bake-off use this, not
# the chat ``+N`` (perk 9, perk 10 invested spheres, and $bonus inflate that).
# Purple 5 / blue 10 are confirmed. Teal→orange follow the same ladder as
# $oq harvest-by-adjacency. Red 150 is the $oq/$oc jackpot.
# Rainbow 500 is the $ot rare-ship / $oq "or more" figure.
# Light has no fixed SP — it splits into other colours (sum those).
# Dark has no fixed SP — it becomes one other colour (use that colour's SP).
# Hidden ``spU`` on an $oh reward line is a bonus $oc use, not SP.
SPHERE_BASE_SP: dict[str, int] = {
    "spP": 5,
    "spB": 10,
    "spT": 20,
    "spG": 35,
    "spY": 55,
    "spO": 90,
    "spR": 150,
    "sp": 150,
    "spW": 500,
}

# Clicking one of these counts as winning the minigame (got the jackpot).
SPHERE_WIN_EMOJIS = frozenset({"sp", "spR", "spW"})

# Spend a click and pay out as *another* colour: dark becomes one sphere
# (``:spD: turns into :spW:``), light splits into several
# (``:spL: breaks down into :spB: + …``). Mudae then prints the payout under
# the result, so anything that reports "which sphere was clicked" has to take
# the source from the transform header rather than the payout line.
SPHERE_TRANSFORM_EMOJIS = frozenset({"spD", "spL"})


def canonical_sphere_emoji(emoji: str | None) -> str:
    """``spB2`` / ``spT2`` (colour-blind letter-in-corner) → ``spB`` / ``spT``.

    Mudae ships a second emoji set for colour-blind players. The name is the
    usual ``sp`` + colour letter plus a digit. Treat them as the base colour
    in logs, spawn rates, ``$oh`` skip rules, and perk-9 filters.
    """
    key = str(emoji or "").strip()
    match = _COLORBLIND_SPHERE_RE.match(key)
    if match:
        return "sp" + match.group(2).upper()
    return key


def sphere_base_sp(emoji: str | None) -> int:
    key = canonical_sphere_emoji(emoji)
    if key == "sp":
        key = "spR"
    return int(SPHERE_BASE_SP.get(key, 0))


KAKERA_EMOJIS = frozenset({
    "kakera",   # blue (default)
    "kakeraP",  # purple — free
    "kakeraT",  # teal
    "kakeraG",  # green
    "kakeraY",  # yellow
    "kakeraO",  # orange
    "kakeraR",  # red
    "kakeraW",  # rainbow
    "kakeraL",  # light
    "kakeraD",  # dark
    "kakeraC",  # chaos
})

# Each kakera type maps to its display label + a textual emoji fallback used in
# the activity log. The QML chip picker uses the PNG/WebP assets under
# ``gui/assets/kakera`` for richer rendering.
KAKERA_INFO = {
    "kakera":  {"emoji": "🔵", "label": "Blue"},
    "kakeraP": {"emoji": "🟣", "label": "Purple"},
    "kakeraT": {"emoji": "🩵", "label": "Teal"},
    "kakeraG": {"emoji": "🟢", "label": "Green"},
    "kakeraY": {"emoji": "🟡", "label": "Yellow"},
    "kakeraO": {"emoji": "🟠", "label": "Orange"},
    "kakeraR": {"emoji": "🔴", "label": "Red"},
    "kakeraW": {"emoji": "⚪", "label": "Rainbow"},
    "kakeraL": {"emoji": "💗", "label": "Light"},
    "kakeraD": {"emoji": "⚫", "label": "Dark"},
    "kakeraC": {"emoji": "✨", "label": "Chaos"},
}
