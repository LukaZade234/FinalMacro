"""Mudae bot constants."""

BOT_NAME = "Mudae"
# Official Mudae bot + common alternate application IDs (servers may differ).
TARGET_BOT_ID = 432618578496954900
MUDAE_BOT_IDS = frozenset({
    TARGET_BOT_ID,
    432610292342587392,
})

CLAIM_EMOJIS = frozenset({"💍", "💖", "💝", "\U0001f498"})

# Sphere button emoji names (sp + color letter, e.g. spY).
SPHERE_EMOJI_PREFIX = "sp"
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
