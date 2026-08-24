"""Sample macro state for scripts/ui_preview.py --demo.

A fresh checkout has an empty activity log and no $tu reading, so every Run
design renders as a grid of em-dashes. Seeding the bridge with the numbers from
the mockups makes the gauges, tones and feed styling reviewable offscreen.

This is only ever imported by the preview tool; the app never touches it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import gui.bridge
from macro.activity_log import ActivityLogEntry
from macro.state import MacroPhase

FEED: list[tuple[str, str]] = [
    ("info", "Sent $wa ×10 · interval 1.8s ±0.4"),
    ("skip", "Makima — Chainsaw Man · 1,411 ka · below 2,000"),
    ("click", "Reacted purple · +312 ka · power 74% → 68%"),
    ("skip", "Ryuk — Death Note · 640 ka · below 2,000"),
    ("claim", "Claimed Yor Forger — Spy × Family · 2,180 ka"),
    ("click", "Reacted rainbow · +540 ka"),
    ("error", "Reaction failed · message deleted before click"),
    ("info", "Levi Ackerman — Attack on Titan · 1,905 ka"),
    ("skip", "Nezuko — Demon Slayer · 1,120 ka · below 2,000"),
    ("click", "Reacted cyan · +198 ka"),
    ("info", "Sent $tu · 14 rolls · reset 47m"),
    ("info", "Sleeping until next roll window"),
    ("skip", "Next roll window in 44m 51s"),
]


def apply(bridge: Any) -> None:
    """Fill the bridge with the mockup's readings, in place.

    Must be called before the QML loads, since it swaps out the summary builder
    the ``runSummaryJson`` property reads through.
    """
    state = bridge._macro_state
    state.phase = MacroPhase.ROLLING
    state.rolls_left = 14
    state.rolls_us_bonus = 3
    state.us_stacked = 2
    state.claim_available = True
    state.claim_cooldown_minutes = None
    state.next_claim_reset_minutes = 192
    state.rolls_reset_minutes = 47
    state.power_percent = 68.0
    state.dk_stock = 3
    state.dk_next_minutes = 26

    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=len(FEED))
    state.activity_log[:] = [
        ActivityLogEntry(
            text=text,
            severity=severity,
            ts=(start + dt.timedelta(minutes=index)).isoformat(),
        )
        for index, (severity, text) in enumerate(FEED)
    ]

    summary = {
        "session": {
            "started_at": (
                dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2, minutes=14)
            ).isoformat(),
            "kakera": 18420,
            "spheres": 24,
            "keys": 3,
            "claims": 6,
        },
        "today": {
            "kakera": 24980,
            "perk8_used": 12,
            "perk8_max": 40,
            "perk8_mode": "active",
            "perk9_used": 6,
            "perk9_max": 20,
            "perk9_spheres": 6,
        },
        "last_claim": {
            "character": "Yor Forger",
            "detail": "Spy × Family · 2,180 ka",
            "time": "22:14:19",
        },
    }

    # runSummaryJson recomputes from the earning logs on every read. Those live
    # in the user's real data directory, so the builder is stubbed instead.
    gui.bridge.build_run_summary = lambda *_args, **_kwargs: summary
    bridge._connected = True
