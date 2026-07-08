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
