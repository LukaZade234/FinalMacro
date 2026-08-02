# TODO / reminders

Items to revisit later (not scheduled work).

---

## Recently completed (Aug 2026)

Reference only — no action needed unless something regresses.

- **Preset UI** — tabbed sections (Rolling / Claims / Reactions / $us / Expert); wizard updated to match
- **App icon** — rainbow kakera; desktop launcher cache refresh in `install-desktop.sh`
- **Final hour** — strict equality only (`claim_reset == rolls_reset`); removed configurable margin
- **Macro: continue after interrupt claim** — normal hourly rolls resume when rolls remain
- **Macro: `$rt` then claim** — refresh roll snapshot before claiming; clearer skip logging
- **`$us` mode** — phantom bonus normal rolls no longer stop the macro; chaos-kakera-style bonus rolls get spent
- **Infobar** — roll count decrements locally as rolls are used
- **Tests** — `fast_macro_timers` fixture + `@pytest.mark.slow` for selective runs
- **`$settings` command reference** — `docs/MUDAE_SETTINGS_COMMANDS.md` (38 commands documented; raw capture in `data/settings_commands_capture.json`)
- **GUI UX (Jul 2026)** — Run-target dropdowns as single source of truth; activity log severity + filter chips; status bar split (connection vs phase)

---

## Mudae `$settings` and `$bonus` parsing audit

**Context:** Server rules vary widely. Example: some servers show **claim buttons** on roll embeds; others disable buttons and require **claiming by reacting with an emoji**. The macro currently only supports button-based claims (`can_claim` / claim button on embed).

**Progress:** `$settings` syntax/outcomes captured verbatim from a live server — see `docs/MUDAE_SETTINGS_COMMANDS.md`. Includes 4 commands not bracketed in `$settings` itself (`$toggleclaimrolls`, `$togglelikerolls`, `$servlimroul`, `$perstogglebutton`). **16 commands are direct toggles** that flip live server state when sent bare (no help text) — any scripted capture must skip or auto-revert them.

**Next steps (in order):**

1. **Document `$bonus`** — same capture pass as `$settings` (account `lukazade234`, Key Server 0); write `docs/MUDAE_BONUS_COMMANDS.md` or extend the existing doc
2. **Fix `$settings` parser** — go field-by-field against `docs/MUDAE_SETTINGS_COMMANDS.md`; handle aggregate bullets (`$togglerolls` → three independent flags), value lines (`$servlimroul`), and string values the parser currently mis-coerces
3. **Fix `$bonus` parser** — same audit once `$bonus` is documented
4. **Wire into runtime** — store parsed fields on channel profiles and use them in macro decisions (see likely areas below)
5. **Safe capture tooling** — update `scripts/document_settings_commands.py` to classify direct toggles and revert them automatically (learned the hard way during the first capture pass)

**Likely wiring areas (after parsers are fixed):**

- Claim mode (buttons vs emoji reaction) — **do not implement claim-via-emoji yet**; note for when claim logic is extended (`$togglebutton`, `$perstogglebutton`, `$claimreact`)
- Kakera / sphere reaction toggles and limits (`$togglekakeratrade`, snipe modes, button recognizability)
- Roll limits, timers, snipe windows, wishlist behavior (`$togglesnipe`, `$togglekakerasnipe`, `$settimer`, `$setrolls`)
- `$servlimroul` / `$gamemode` limits affecting which characters can roll
- Anything else in `$settings` / `$bonus` that affects macro decisions but is ignored or only partially stored today

**Related code:** `mudae/parsers/` (settings, bonus), `gui/bridge.py` (profile/settings fetch), `macro/config.py`, channel profile storage in `gui/server_profiles.py` / `docs/MULTI_ACCOUNT.md`.

**Reminder trigger:** Before changing claim, kakera, or roll rules per-server, complete steps 1–4 above.

---

## Daily reset / “done for today” skip logic

**Context:** Many Mudae mechanics reset on a timer (perk 8 clicks, `$oh`/`$oc`/`$oq`/`$ot` allowances, etc.). Once exhausted for the day on a server, the macro should skip re-checking until the refill time.

**Progress:** Perk 8 via `$ohu8` is implemented — persisted in `channel.daily_resets.perk8`, skip logic in `macro/perk8_daily.py`.

**Still to do:**

- **Inventory the rest** — `$ohu8` also reports `$oh`/`$oc`/`$oq`/`$ot` daily counts and sphere stock; decide which of these the macro should track and skip
- **Generalize the daily-reset store** — extend `daily_resets` on channel profiles beyond perk8 (same pattern: last-known state + `refill_at`, skip queries until refill)
- **Session resume** — confirm skip logic works across app restarts for all tracked daily items (perk8 does; others don't exist yet)

**Related code:** `macro/perk8_daily.py`, `macro/daily_store.py`, `mudae/parsers/ohu8.py`, `gui/server_profiles.py` (`daily_resets` field).

---

## Macro behavior improvements

- **Chaos kakera / random bonus rolls** — `$us` mode now spends stranded bonus normals, but random rewards (chaos kakera can grant 1–15+ extra rolls) are not logged or tracked anywhere. Add logging and optionally surface in activity log / session stats so overnight runs show when bonus rolls appeared and were consumed
- **Claim via emoji reaction** — blocked on settings audit + claim logic extension (see above)

---

## Multi-account runtime (Phase D)

**Context:** Config already supports multiple accounts; only one Discord connection runs at a time. See `docs/MULTI_ACCOUNT.md` for the full design.

**Task:** Implement coordinator / account manager so multiple `(account, channel, preset)` targets can run without preset collapse bugs.

**Related code:** `gui/run_target.py`, `mudae/discord_reader.py`, future `macro/coordinator.py`, `gui/bridge.py` (`deployAll()`).

---

## Achievement system (idea)

**Concept:** Track fun milestones during macro sessions and surface them in the UI — e.g. first 1,000 chaos keys on a character, hitting soulmate (10 chaos keys), rolling a wish, clearing a `$us` stack milestone, first kakera rainbow of the day, etc.

**Why it could be nice:**

- Celebrates long-term grind moments instead of only logging skips and errors
- Gives passive feedback that the macro noticed something meaningful
- Could tie into existing logs (`key_log`, `kakera_log`, `soulmate_log`, session logs) rather than starting from scratch

**Rough shape (when/if built):**

- Define achievements with triggers (parser fields, log events, thresholds)
- Persist unlocked achievements per account (or per account + character)
- Toast / activity-log banner / small Achievements panel in the GUI
- Optional: sound or subtle animation on unlock — keep it lightweight

**Related code:** `mudae/key_log.py`, `mudae/parsers/roll.py`, `macro/activity_log.py`, `gui/bridge.py`, session logs under `data/session_logs/`.

**Status:** Idea only — not scheduled. Good candidate after core macro stability and the settings/bonus audit.
