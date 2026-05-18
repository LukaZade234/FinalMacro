"""Mudae bot constants."""

BOT_NAME = "Mudae"
# Official Mudae bot + common alternate application IDs (servers may differ).
TARGET_BOT_ID = 432618578496954900
MUDAE_BOT_IDS = frozenset({
    TARGET_BOT_ID,
    432610292342587392,
})

CLAIM_EMOJIS = frozenset({"💍", "💖", "💝"})

# Sphere button emoji names (sp + color letter, e.g. spY).
SPHERE_EMOJI_PREFIX = "sp"

KAKERA_EMOJIS = frozenset({
    "kakera",
    "kakeraT",
    "kakeraG",
    "kakeraY",
    "kakeraO",
    "kakeraR",
    "kakeraW",
    "kakeraL",
    "kakeraP",
})

KAKERA_INFO = {
    "kakera": {"emoji": "🟡", "label": "Yellow"},
    "kakeraT": {"emoji": "🔵", "label": "Blue"},
    "kakeraG": {"emoji": "🟢", "label": "Green"},
    "kakeraY": {"emoji": "🟡", "label": "Yellow"},
    "kakeraO": {"emoji": "🟠", "label": "Orange"},
    "kakeraR": {"emoji": "🔴", "label": "Red"},
    "kakeraW": {"emoji": "⚪", "label": "Rainbow"},
    "kakeraL": {"emoji": "🟣", "label": "Light"},
    "kakeraP": {"emoji": "🟣", "label": "Purple"},
}
