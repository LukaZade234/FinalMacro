# Architecture

How FinalMacro is put together. Game rules live in
[`MUDAE_LOGIC.md`](MUDAE_LOGIC.md) (kakera click order:
[Kakera reaction rules](MUDAE_LOGIC.md#kakera-reaction-rules)). Open work lives in [`TODO.md`](TODO.md).

---

## Shape

```
Discord channel  →  mudae/ (read, parse, send)
                         ↓
                   macro/  (decide, click, loop)
                         ↓
                   gui/    (PySide6 + QML, persist settings)
```

`run.py` starts `gui/app.py`: load fonts, single-instance lock, expose
`AppBridge` to QML as `App`, load `gui/Main.qml`. One window, one Discord
connection at a time. `$p`/`$daily` for other accounts temporarily switch
the token and restore the Run target.

---

## Repository map

```
FinalMacro/
├── run.py, launch.sh, install.sh, install-desktop.sh
├── requirements.txt, pytest.ini, pyrightconfig.json
├── README.md
├── docs/
│   ├── MUDAE_LOGIC.md          # game + how the macro uses it
│   ├── ARCHITECTURE.md         # this file
│   ├── TODO.md                 # open work
│   └── archive/                # reference mocks + superseded docs (see archive/README.md)
├── gui/                        # desktop UI + persisted stores
├── macro/                      # roll / claim / react / minigame engines
├── mudae/                      # Discord client + parsers + logs
├── tests/
├── scripts/                    # fonts, offscreen UI preview, $settings capture
├── assets/                     # app icon
└── data/                       # local only (gitignored): settings.json, logs
```

### `gui/`

| Path | Role |
|------|------|
| `app.py` | QApplication, engine, tray, single-instance |
| `bridge.py` | `AppBridge` — QML `App` object; owns stores, connect/start/stop |
| `Main.qml` | Window; binds `Theme` to `App.uiLayout` / `App.uiPalette` |
| `Theme.qml` | Singleton design tokens (colors from `palettes.js`, shape from `skins.js`) |
| `palettes.js` / `skins.js` / `clock.js` | Colour themes, layout shells, UTC stats buckets (QML `.pragma library`) |
| `qmldir` | Registers `Theme` and `SphereAssets` singletons |
| `accounts.py` / `presets.py` / `server_profiles.py` / `targets.py` | JSON stores inside `data/settings.json` |
| `sheet_store.py` | Per-account `$bonus` / `$shop` on a channel profile (`$settings` stays flat — it is the server's). Reads a pre-split sheet back for the main account only, flagged `inferred` |
| `run_target.py` | Resolve an account + channel + preset pair. `resolve_run_target()` reads the *active* selections (what Run would connect to); `resolve_scope_target()` resolves one explicit pair without touching them, which is what a detached `ScopeBar` fetch needs |
| `scope_fetch.py` | Which of four routes a sheet fetch takes — `send` / `hop` / `temporary` / `blocked` — as plain data, plus the command allowlist. See "Temporary connections" below |
| `settings.py` | Load/save `data/settings.json` |
| `import_legacy.py` | Import old MudaeBot `Account_info.json` / `presets.json` |
| `fonts.py` | Register Space Grotesk + IBM Plex Mono before QML loads |
| `shells/` | Classic / Haul / Console / Boxed chrome + per-design Run pages |
| `views/` | Shared pages (Settings, Accounts, Servers, Presets, Mudae, stats, …) |
| `views/AdvisorView.qml` | **Advisor hub** — `$bw` / Key EV / Wishlist / Lists / Formatter. Every sub-page states its evidence, and abstains rather than asserting where the data does not support an answer. `MudaeListsView` is still an empty `Item`; the rest are built |
| `views/BwAdvisoryView.qml` | **Advisor › `$bw`** — the rolls-against-wish-spawns sweep from `macro/bw_calc.py`. Ordered by what the page is for: the character picker and the **three optimal `$bw`** (whole wishlist / starwishes / selected character) lead, the sweep table sits beside its curve, and the inputs and evidence — both set once — sit at the bottom. The old headline tiles are reduced to one muted strip beside the picker, since they are context for the peaks rather than answers. Fetch buttons are in the body rather than the scope bar, because it reads four sheets and the bar has one slot. It never sends `$bw` |
| `components/CharacterPicker.qml` | Pick one wishlist character by typing. Filters a couple of hundred names as you type and shows each candidate's starwish flag, perk-1 bonus, perk-4 level and spheres — the numbers that move a character's own `$bw` optimum, so the choice is not made blind. Search state is held explicitly rather than read off the field's focus, which moves to the popup's scrollbar on a drag |
| `views/KeyEvView.qml` | **Advisor › Key EV** — keys per wish spawn as the sum `1 + $bonus extra-key chance + the character's own perk 4`, the per-type rate from the key log, and the chaos price. Claim keys report their rate and abstain on value: perk 4 says how many arrive, not what one unlocks |
| `components/BwSweepChart.qml` | The `$bw` curves, drawn tall and narrow beside the sweep table. Two `Canvas` series on **two** axes — the whole wishlist left, the selected character right — because a single character's EV is ~65x below the total and one shared scale flattens it onto the baseline; the axes are colour-matched to their curves. Vertical guides mark each optimum with their labels stacked, since the peaks cluster within a few `$bw`. Axis maxima come off a 1/2/2.5/5/10 step ladder so the curve uses the panel |
| `views/AppWishlistView.qml` | **Advisor › Wishlist** — the app-only character/series list the macro claims from, with the Global-vs-per-pair toggle. Two `components/WishlistSection.qml` columns; a match claims via the wish-ping path (`macro/wishlist.py`, `gui/wishlist_store.py`) |
| `views/SpheresHubView.qml` | **Spheres hub** — Stock & shop / Upgrades / Characters. Current state and decisions; sphere *history* stays on Statistics › Spheres |
| `views/MudaeView.qml` | **Mudae hub** — `ScopeBar` + pills over a `Loader`, same shape as `StatisticsView`. Sub-pages `MudaeSettingsSheetView` (`$settings` + drift + copy), `MudaeOvView` (stubbed, no parser), `MudaeBonusView` |
| `components/ScopeBar.qml` | Account + channel picker that starts on the Run target then detaches, so a page can read account B while account A rolls. Unlike `ServerChannelSelectors` it never moves the Run target. `fetchCommand` puts that page's fetch button on the right of the bar |
| `components/ScopeFetchButton.qml` | The fetch button in the scope bar. Never disabled for being disconnected — it takes the temporary route — only for the macro being busy, and it names which |
| `components/` | Themed controls used by Classic and the shared views |
| `components/MudaeSheetPanel.qml` | One parsed sheet (`$settings` / `$bonus` / `$shop`) as sectioned label/value rows; `sheetKind` picks the slot. Replaced three copy-pasted panels and reads `Theme` sizes rather than hardcoded pixels, so it takes each shell's shape |
| `assets/kakera/` | Kakera + sphere button artwork |

`ShellSwitcher` picks `gui/shells/<Design>Shell.qml` from `Theme.layoutId`.
Every shell hosts the same `PageHost` pages; only the Run page component
changes.

**Page order is an index contract.** `PageHost`'s `switch`, each shell's nav
array (`ClassicShell.pages`, `HaulShell.navItems`, `ConsoleShell.tabs`,
`BoxedShell.menuItems`), `ShellSwitcher.settingsPageIndex`,
`IconRail.settingsIndex` and `scripts/ui_preview.py`'s `PAGE_NAMES` all encode
the same integers. Inserting a page means updating all seven. Current order:
Run, Accounts, Servers, Presets, **Mudae**, **Spheres**, **Advisor**,
Statistics, Debug, Settings. (`Utilities` was absorbed into Advisor.) Boxed's `accel` is the underlined letter and must stay unique.

### `macro/`

| Path | Role |
|------|------|
| `roll_cycle.py` | Hourly loop and `$us` mode |
| `roll_context.py` | Per-account bag of config, state, actions, monitor |
| `config.py` | `MacroConfig` + claim / kakera / sphere / `$us` rule blocks |
| `rule_eval.py` | Pure decisions (claim / kakera / sphere) from parsed fields |
| `post_roll.py` / `kakera_reactor.py` / `sphere_reactor.py` | Apply those decisions. `post_roll` claims by clicking the button, or by reacting when the roll has none (buttons off for the server or account) |
| `chaos_followup.py` | Extra hourly rolls + discounted chaos-kakera power cost |
| `claim_window.py` | Final-hour test (claim reset == rolls reset) |
| `rt_manager.py` / `dk_manager.py` / `reaction_power.py` | `$rt`, `$dk`, power bar |
| `sheet_caps.py` | Run-channel `$bonus` power max + kakera click cost, `$shop` perk 9 cap |
| `account_dailies.py` / `account_daily_runtime.py` | Account-global `$p` / `$daily` timing and send |
| `roll_scheduler.py` / `roll_stop.py` / `roll_interrupts.py` | Sleep, stop, wish-claim interrupt |
| `us_stop.py` | `$us` drain policy and stop / pause options (roll cap, reaction power, Mudae's hourly key limit, local schedule) |
| `us_schedule.py` | Local-time window for automatic `$us` (separate from Roll `$us`) |
| `perk8_daily.py` / `perk8_runtime.py` | Daily perk-8 budget |
| `perk9_daily.py` | Daily perk-9 click counter; the per-account spawn rate learned from ordinary rolling (`$us` excluded), kept per day over a trailing 2 weeks |
| `advisor.py` | Assembles `$bonus` / `$settings` / `$shop` / `$wl` into the `$bw` sweep, reports per-sheet readiness so a page can offer the missing fetch, and prices keys (chaos only — it discounts reaction power; claim keys report their rate and abstain on value) |
| `bw_calc.py` | The `$bw` sweep itself, pure and sheet-free: the published tier tables, the spawn-weight model, `$persrare` rerolls, the 2,200/hour key cap, and the guards that abstain when `$bonus` and the tiers disagree. `derive_perk1_pct` re-derives a `$wl` row's `+N%` as a staleness check |
| `wishlist.py` / `wishlist_capture.py` | The app-only wishlist matcher (a hit claims via the wish-ping path) and the `$wl` listing capture — by DM (`$wlsz+z!`) or by clicking through the paged channel reply, per the Settings DM toggle |
| `sphere_upgrades.py` | What the next ouroperk level is worth. Prices perk 9 only — value % from logged perk-9 income, the extra click from the perk-9 DP — and **abstains with a reason** on every perk the app cannot price |
| `perk9_threshold.py` | Perk-9 adaptive click/skip EV + DP (opt-in `budget_aware`); forecasts spawns still to come from the learned rate, and forces the bar to 0 in the last hour before the reset |
| `perk9_runtime.py` | When to send `$ohu9`; local spawn/click tracking between syncs; measures the spawn rate across `$us`-free stretches of rolling |
| `minigame_daily.py` | Daily `$oh` / `$oc` / `$oq` / `$ot` skip |
| `minigames.py` | `$ohu` then `$oh` / `$oc` / `$oq` / `$ot` |
| `sphere_game.py` / `oc_game.py` / `oq_game.py` / `ot_game.py` | Individual minigames, all in `PLAYABLE_MINIGAMES` (play-all + after-refill auto-play). `$ot`'s Run-page button also still works for an on-demand single play. |
| `oh_replay.py` | `$oh` simulator + replay of real logged boards (no solver yet; greedy lives in `sphere_game.py`) |
| `oc_solver.py` / `oc_replay.py` | `$oc` geometric hunt + remaining-need-aware collect lookahead; replay of **real logged boards** (preferred) or calibrated synthetic ones |
| `oq_solver.py` / `oq_worlds.py` / `oq_replay.py` | `$oq` MIXED hunt, auto-revealed red, 12,650-world replay |
| `ot_solver.py` / `ot_replay.py` | `$ot` battleship: fleet inference by a **memoised counting DP** over 5,520 ship triples (never enumerating the millions of placements). Two-phase policy — hunt blues while **Extra Chance** holds the board open, then harvest-and-probe. Replay of the 27 real boards or generated ones. |
| `minigame_board.py` | 5×5 board / click helpers for the minigame log. ``normalize_sphere_emoji`` folds colour-blind ``spB2`` / ``spT2`` into ``spB`` / ``spT``. |
| `settings_apply.py` | Push a settings preset to the server |
| `state.py` | `AccountState`, `MacroPhase` |
| `activity_log.py` / `session_log.py` | In-app log + on-disk session |
| `runtime_store.py` / `daily_store.py` | Resume `$tu` / daily resets across restarts |
| `connection_recovery.py` | Reconnect after Discord blips |
| `maintenance.py` | Backoff ladder (5 / 10 / 30 min, then stop) while Mudae is rebooting |
| `actions.py` | Thin send/click helpers over the monitor; owns the account's `MaintenanceWatch` |

### `mudae/`

| Path | Role |
|------|------|
| `clock.py` | UTC `date_key` (Mudae dailies); local HH:MM:SS for the live feed |
| `discord_reader.py` | `ChannelMonitor` — user-token client, one channel. `is_connected` tracks `on_disconnect` / `on_resumed` and `client.is_closed()` (it used to be set once by `on_ready` and never cleared, so every reconnect guard was dead code); `ensure_connected()` waits for discord.py's own resume before forcing one, and `seconds_since_last_event()` exposes a silent gateway to callers that know they should have heard something. `send_command` and `click_button` both retry transient failures, reconnect when the gateway has dropped, and report the reason; a click also refetches the message between attempts, since a stale cached copy is the usual reason a button "vanishes". |
| `commands.py` | Command aliases and “is this a `$settings` reply?” detectors |
| `constants.py` | Bot ids, kakera / sphere emoji names, ranks, **base SP**. Colour-blind ``spB2`` / ``spT2`` collapse via ``canonical_sphere_emoji``. |
| `buttons.py` | Classify embed buttons (claim / kakera / sphere); decide button-vs-reaction claiming from a roll's components |
| `live_feed.py` | Text-only Discord/Mudae mirror for the Run live feed (`:kakeraO:` / `:spY:` / `:chaoskey:` tokens; QML `MudaeEmoji` draws the assets). Mirrors real channel text only — no macro-side summary fallback — and only lines that **name the connected account** (`account_context.username_matches_own`, the same test the statistics logs record on), because classification runs on loose heuristics that read Mudae's own prose as claims and sphere payouts. Message **edits** are never mirrored: a real follow-up is a new message, an edit is a panel or board being re-rendered. **Roll cards are not mirrored at all** — nobody is named on a roll, so it cannot be attributed; `format_roll_line` is called by `macro/roll_cycle.py` for each card it rolls itself, which is why a card in the feed always means the macro rolled it |
| `message_text.py` | Flatten Components V2 `content` (``$shop`` and similar) |
| `parsers/` | One module per message kind (`tu`, `roll`, `settings`, `shop`, `ohu8`, `chaos`, …) |
| `parsers/pipeline.py` | Classify + parse a snapshot. Recognises Mudae's "under maintenance" reply **first**, ahead of the step that pairs a reply with the command that was sent |
| `parsers/maintenance.py` | Mudae's reboot reply and its stated window |
| `parsers/minigame.py` | Recognise a sphere-game grid (`$oh` / `$oc` / `$oq` / `$ot`) **before** the claim heuristics — the board prose is all bold names, and Mudae re-edits the grid on every click |
| `types.py` | `MessageKind`, `ParseResult`, `MudaeMessageSnapshot` |
| `event_log.py` | Unified Statistics store (`data/events.jsonl`); one-time import of the old `*_log.json` arrays (those files are left on disk) |
| `stats_index.py` | In-memory daily cube + paged `recent` rows for Statistics (never dumps the full log to QML). `daily_report()` slices the same cells by **day** instead of by kind for Statistics › Report — totals, colour/method breakdowns with event counts, an **all-time** comparison over *active* days, plus hourly panels, the perk-8/perk-9 click tapes and the day's soulmates, which come from the raw events because the cube keeps neither the hour nor the order. The tapes are the one part that **cannot be generalised**: a perk-8/perk-9 daily allowance belongs to one (account, server) pairing, so they are drawn only when the report is scoped to both and otherwise return `TAPE_SCOPE_NOTE` — the payload's `scope` block says which it is |
| `account_context.py` | Which account a row belongs to. `username_matches_own` — is this Mudae line about the connected account? — lives here so the logs, the key tracker and the live feed all answer it the same way |
| `key_log.py` / `kakera_log.py` / `sphere_log.py` / `soulmate_log.py` | Record helpers on top of `event_log`. `soulmate_log` backfills `date_key` from the row's Discord `message_id` on load — snowflakes embed the moment they were minted, so historical soulmates that stored only a clock time are dateable without new capture |
| `minigame_stats.py` | Per-day minigame boards and spheres, benchmarked **only over days that have board counts**. Sphere events predate `data/minigame_log.json`, so dividing all sphere history by the shorter board history inflates every rate; the payload carries the window it actually covers |
| `minigame_log.py` / `chaos_capture.py` | Separate files: `data/minigame_log.json`, `data/chaos_log.json` |
| `settings_catalog.py` / `settings_commands.py` / `settings_preset.py` | GUI settings templates |
| `command_ack.py` / `command_context.py` / `claim_context.py` | Match replies to the command we just sent |
| `macro_activity.py` | Owner **depth count** behind `ChannelMonitor.macro_active`. The roll cycle and each minigame overlap (a manual `$oh` is allowed during the hourly refill wait), so the flag cannot be saved and restored per owner — it is true while any owner holds it. The gateway does not own it: reconnecting leaves it alone. |

### `tests/`

Pytest. `conftest.py` holds shared fixtures (`fast_macro_timers`, Discord
fakes). Mark slow tests with `@pytest.mark.slow`. Names follow the module
under test (`test_roll_cycle.py`, `test_parsers.py`, …).

### `scripts/`

| Script | Role |
|--------|------|
| `ui_preview.py` | Offscreen grab of a shell + page to a PNG |
| `build_fonts.py` | Static Space Grotesk weights from the variable font |
| `document_settings_commands.py` | Live `$settings` + read-only `$bonus` capture; skips 16 direct toggles unless `--include-toggles` (send+revert) |
| `oq_bakeoff.py` | Replay MIXED vs entropy on every `$oq` world |
| `oc_bakeoff.py` | A/B `$oc` policies. `--from-log` replays real logged boards and reports paired deltas with a t-statistic |
| `oh_bakeoff.py` | Score `$oh`. `--from-log` replays real boards; `--reveals` sweeps the initial-reveal perk |
| `perk9_bakeoff.py` | Score the perk-9 adaptive threshold vs static allow-lists. `--hazard-sweep` checks the learned-rate estimator across accounts unlike this one; `--from-logs` replays real logged days; `--with-us-burst` is the regression test for excluding `$us` rolls from the learned rate |
| `merge_event_logs.py` | Union diverged `events.jsonl` copies after a Syncthing outage |

---

## Runtime data flow

1. User picks account + channel + preset on Run. `resolve_run_target()`
   binds them (`gui/run_target.py`).
2. `App.connect()` starts `ChannelMonitor` with that token and channel
   snowflake.
3. Incoming Discord messages become `MudaeMessageSnapshot`s, then
   `ParseResult`s (`mudae/parsers/pipeline.py`).
4. `RollCycleEngine` (and minigame / settings helpers) send commands and
   click buttons through `DiscordActions` + the monitor.
5. Decisions use `MacroConfig` from the preset and `AccountState` updated
   from `$tu` and roll parses.
6. GUI properties on `AppBridge` notify QML (status, activity log, stats).

Nothing in `macro/` imports QML. The GUI owns persistence and the Discord
lifecycle; the macro is a library.

### Temporary connections (scope fetch)

Every sheet the app parses — `$settings`, `$bonus`, `$shop`, `$wl` — describes
one `(account, server)` pair, and can only be obtained by sending a command
*as that account, in that server*. The pages that read those sheets carry a
`ScopeBar` that detaches from the Run target, so the pair on screen is
routinely not the pair the macro is connected to. The fetch buttons used to
resolve that by refusing: the old ones on Servers were disabled unless the
channel *was* the Run target and the macro was connected.

Instead, `AppBridge.fetchForScope(command, account_id, channel_profile_id)`
goes where the scope points and puts the session back. `gui/scope_fetch.py`
picks the route:

| Route | When | What happens |
| --- | --- | --- |
| `send` | Already on this pair | Send, wait for the reply |
| `hop` | A session exists on a different pair | Move the monitor, send, move it back — the same manoeuvre `$p`/`$daily` performs hourly, sharing `_account_daily_lock` so the two can never interleave |
| `temporary` | No session at all | Stand one up for the length of the command, then take it down |
| `blocked` | The macro is mid-anything, or half a scope | Refuse, and say which |

The temporary session is deliberately **not** a Run session: its own thread,
loop and `ChannelMonitor`, no `RollCycleEngine`, no `$p`/`$daily` or `$us`
loops, and a narrow `_on_temporary_parsed` that only feeds the waiter and
files the sheet. Nothing it sees reaches the Run feed or the kakera / key /
sphere / minigame / chaos logs — a one-command connection is not a session and
must not leave one's footprints.

Attribution is the subtle part. `_on_parsed` stamps the owning account into
the payload at the moment the sheet arrives (`_sheet_account_id()`), rather
than letting `_deliver_profile_update` read `_run_account_id` back on the GUI
thread — by then the fetch may already have come home, and the sheet would be
filed under the wrong account. `_scope_fetch_account_id` is held only across
the send-and-wait, so a sheet the *home* account was already receiving cannot
be captured by the borrower.

A fetch never interrupts: a running macro, a minigame, a settings apply, a
pending run action or an in-flight `$p`/`$daily` all block it, because
borrowing the gateway is only safe when nothing else holds it.

---

## Persisted model

All of this is one file: `data/settings.json` (never commit it).

| Layer | Store | Role |
|-------|--------|------|
| Who | `accounts[]` | Token, name, enabled channels, `$p`/`$daily` channel + cooldowns |
| Where | `servers[]` / `channels[]` | Channel snowflakes, fetched `$settings` (flat) and `$bonus` / `$shop` (per account), `daily_resets` (per account) |
| How | `presets{}` | `MacroConfig` per preset id |
| Binding | `targets[]` | `{ account_id, channel_profile_id, preset_id }` |
| Wishlist | `wishlist` | App-only character/series names the macro claims on sight: `global` flag, the global lists, and `scopes{}` keyed `account_id|channel_profile_id` |
| Captured `$wl` | `mudae_wishlists` | Mudae's own wishlist per `account_id\|channel_profile_id`: sizes, and each character's spheres, perk-1 spawn bonus and ouroperk roster |
| `$bw` inputs | `bw_options` | Per `account_id\|channel_profile_id`: base pool, `$persrare` rerolls, claimed-character count, slash toggle, focus character — the sweep's inputs that no Mudae sheet answers (`gui/bw_options_store.py`) |

Resolution for a run: `gui/run_target.py` → `resolve_run_target()`. For a
fetch on a page's own scope bar: `resolve_scope_target()`, same file, which
takes the pair explicitly and leaves the active selections alone.

Also in that file: tray / update prefs, `allow_mudae_dms` (opt-in Mudae DM
reading, see `MUDAE_LOGIC.md`), `ui_layout`, `ui_palette`. Session
logs go under `data/session_logs/`. Kakera / key / sphere / soulmate events
are `data/events.jsonl` (append-only JSONL; the old `kakera_log.json` /
`sphere_log.json` / `key_log.json` / `soulmate_log.json` are a one-time
import backup and are not updated). Statistics cards/charts use an in-memory
daily cube (`mudae/stats_index.py`); QML only receives a page of `recent`
rows. Opening a Statistics tab (and a file watcher, same idea as
`settings.json`) re-reads `events.jsonl` when Syncthing updates it, unless
this process still has unflushed rows. Minigame boards stay in
`data/minigame_log.json`; chaos capture stays in `data/chaos_log.json`.
Syncthing on `data/` should sync `events.jsonl` for kakera/sphere/key stats;
turning the folder's filesystem watcher on helps.

---

## Appearance

Two independent axes, both persisted on `AppBridge`:

- **Layout** (`ui_layout`): `classic` / `haul` / `console` / `boxed` —
  which `gui/shells/*Shell.qml` to load. Shape tokens (radius, font,
  density) come from `gui/skins.js`.
- **Palette** (`ui_palette`): colour set from `gui/palettes.js`. Switching
  layout can follow that design's default palette until the user pins one.

`Theme` is a QML singleton. `Main.qml` binds it to `App` because singletons
cannot see context properties.

**Design reference:** archived static mock
[`docs/archive/finalmacro-gallery-v3.html`](archive/finalmacro-gallery-v3.html)
(four Run layouts and palette swatches). Shipped tokens live in
`gui/palettes.js` and `gui/skins.js`. For a new shell, compare the mock,
then add `gui/shells/<Name>Shell.qml` + Run page and register the layout id
in `skins.js` / Settings. Offscreen PNG previews: `scripts/ui_preview.py`.

**Solver / calculator reference:** archived
[`docs/archive/mudae-tools-dev-guide.md`](archive/mudae-tools-dev-guide.md)
(Colblitz rebuild spec). Pickup order and what to skip are in
[`TODO.md`](TODO.md) (**Colblitz tools vs this app**). Implement in
`macro/*_solver.py`, not a separate tools package.

---

## Multi-account runtime (Phase D)

Config already supports several accounts. Runtime still opens **one**
Discord connection. This is how to extend it without repeating the old
MudaeBot bug (one account using the wrong preset on every channel).

Rules:

1. **Never collapse presets per account.** Each running instance resolves
   `(account_id, channel_profile_id)` → `preset_id` via `TargetStore`.
2. **One monitor per connected account**, keyed by `account_id`. Do not
   share `AccountState` across accounts. `RollContext` is already
   per-account so a coordinator can hold several.
3. **Schedule work on targets**, not accounts alone: iterate `targets[]`,
   skip accounts on cooldown, round-robin channels then accounts.
4. **GUI:** Run can stay single-target for manual use; `deployAll()` would
   start every configured target.

Sketch:

```text
AccountManager
  clients: dict[account_id, ChannelMonitor]
  deploy(target) -> connect monitor to channel snowflake
  schedule() -> for each target: resolve preset, run RollCycleEngine
```

Files to extend: `mudae/discord_reader.py` (already one channel per
monitor), `macro/roll_cycle.py` (one engine per monitor), new
`macro/coordinator.py`, `gui/bridge.py` (`connect()` stays single-target).

Legacy MudaeBot `channel_presets` strings map to `targets[]` in
`gui/import_legacy.py`. Do not port “first preset per account”.

Original write-up: `docs/archive/MULTI_ACCOUNT.md`.

---

## Tests and local data

```bash
.venv/bin/python -m pytest
```

`data/` is gitignored. Friends get a clone without tokens. The `$settings`
verbatim capture (`docs/archive/MUDAE_SETTINGS_COMMANDS.md` and
`data/settings_commands_capture.json`) stays local — it is a parsing aid,
not a shipping doc. Sanitized dumps used by tests live in
`tests/mudae_sheet_fixtures.py`.
