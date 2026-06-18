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

# --- $oh sphere minigame ---------------------------------------------------
# Face-down (not yet revealed) grid button.
SPHERE_HIDDEN_EMOJI = "spU"
# Colors whose only role is to unveil more buttons (blue unveils 3, teal 1).
# Per strategy these are never clicked once revealed — we let them stay so the
# higher-value spheres they expose can be taken instead.
SPHERE_REVEAL_EMOJIS = frozenset({"spB", "spT"})
# Rough payout ranking used to pick between revealed value spheres (higher is
# better). Unknown revealed colors default to 0 but are still clickable.
SPHERE_VALUE_RANK = {
    "spG": 1,  # green
    "spY": 2,  # yellow
    "spO": 3,  # orange
    "spR": 4,  # red
    "spW": 5,  # rainbow
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
