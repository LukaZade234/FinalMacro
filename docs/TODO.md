# TODO / reminders

Items to revisit later (not scheduled work).

## Mudae `$settings` and `$bonus` parsing audit

**Context:** Server rules vary widely. Example from recent debugging: some servers show **claim buttons** on roll embeds; others disable buttons and require **claiming by reacting with an emoji** instead. The macro currently only supports button-based claims (`can_claim` / claim button on embed).

**Task:** Go through the **entire** `$settings` and `$bonus` parser output and wire important fields into the app so presets and runtime behavior match each channel/server correctly. Likely areas:

- Claim mode (buttons vs emoji reaction) — **do not implement yet**; note for when claim logic is extended
- Kakera / sphere reaction toggles and limits
- Roll limits, timers, floors, wishlist behavior
- Anything else in `$settings` / `$bonus` that affects macro decisions but is ignored or only partially stored today

**Related code:** `mudae/parsers/` (settings, bonus), `gui/bridge.py` (profile/settings fetch), `macro/config.py`, channel profile storage in `gui/server_profiles.py` / `docs/MULTI_ACCOUNT.md`.

**Reminder trigger:** Before changing claim, kakera, or roll rules per-server, complete this audit first.

## Achievement system (idea)

**Concept:** Track fun milestones during macro sessions and surface them in the UI — e.g. first 1,000 chaos keys on a character, hitting soulmate (10 chaos keys), rolling a wish, clearing a `$us` stack milestone, first kakera rainbow of the day, etc.

**Why it could be nice:**

- Celebrates long-term grind moments (like Reze/Lucy crossing 1k keys) instead of only logging skips and errors
- Gives passive feedback that the macro noticed something meaningful, not just “roll → skip → roll”
- Could tie into existing logs (`key_log`, `kakera_log`, `soulmate_log`, session logs) rather than starting from scratch

**Rough shape (when/if built):**

- Define achievements with triggers (parser fields, log events, thresholds)
- Persist unlocked achievements per account (or per account + character)
- Toast / activity-log banner / small Achievements panel in the GUI
- Optional: sound or subtle animation on unlock — keep it lightweight

**Related code:** `mudae/key_log.py`, `mudae/parsers/roll.py`, `macro/activity_log.py`, `gui/bridge.py`, session logs under `data/session_logs/`.

**Status:** Idea only — not scheduled. Good candidate after core macro stability and the settings/bonus audit.
