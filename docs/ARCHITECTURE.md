# Architecture

How FinalMacro is put together. Game rules live in
[`MUDAE_LOGIC.md`](MUDAE_LOGIC.md). Open work lives in [`TODO.md`](TODO.md).

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
| `run_target.py` | Resolve active account + channel + preset |
| `settings.py` | Load/save `data/settings.json` |
| `import_legacy.py` | Import old MudaeBot `Account_info.json` / `presets.json` |
| `fonts.py` | Register Space Grotesk + IBM Plex Mono before QML loads |
| `shells/` | Classic / Haul / Console / Boxed chrome + per-design Run pages |
| `views/` | Shared pages (Settings, Accounts, Servers, Presets, stats, …) |
| `components/` | Themed controls used by Classic and the shared views |
| `assets/kakera/` | Kakera + sphere button artwork |

`ShellSwitcher` picks `gui/shells/<Design>Shell.qml` from `Theme.layoutId`.
Every shell hosts the same `PageHost` pages; only the Run page component
changes.

### `macro/`

| Path | Role |
|------|------|
| `roll_cycle.py` | Hourly loop and `$us` mode |
| `roll_context.py` | Per-account bag of config, state, actions, monitor |
| `config.py` | `MacroConfig` + claim / kakera / sphere / `$us` rule blocks |
| `rule_eval.py` | Pure decisions (claim / kakera / sphere) from parsed fields |
| `post_roll.py` / `kakera_reactor.py` / `sphere_reactor.py` | Apply those decisions |
| `claim_window.py` | Final-hour test (claim reset == rolls reset) |
| `rt_manager.py` / `dk_manager.py` / `reaction_power.py` | `$rt`, `$dk`, power bar |
| `sheet_caps.py` | `$bonus` power max + `$shop` perk 9 cap on runtime state |
| `account_dailies.py` / `account_daily_runtime.py` | Account-global `$p` / `$daily` timing and send |
| `roll_scheduler.py` / `roll_stop.py` / `roll_interrupts.py` | Sleep, stop, wish-claim interrupt |
| `us_stop.py` | `$us` stop options |
| `perk8_daily.py` / `perk8_runtime.py` | Daily perk-8 budget |
| `minigames.py` | `$ohu` then `$oh` / `$oc` / `$oq` |
| `sphere_game.py` / `oc_game.py` / `oq_game.py` | Individual minigames |
| `oq_solver.py` / `oq_worlds.py` / `oq_replay.py` | `$oq` MIXED hunt, auto-revealed red, 12,650-world replay |
| `minigame_board.py` | 5×5 board / click helpers for the minigame log |
| `settings_apply.py` | Push a settings preset to the server |
| `state.py` | `AccountState`, `MacroPhase` |
| `activity_log.py` / `session_log.py` | In-app log + on-disk session |
| `runtime_store.py` / `daily_store.py` | Resume `$tu` / daily resets across restarts |
| `connection_recovery.py` | Reconnect after Discord blips |
| `actions.py` | Thin send/click helpers over the monitor |

### `mudae/`

| Path | Role |
|------|------|
| `clock.py` | UTC `date_key` (Mudae dailies); local HH:MM:SS for the live feed |
| `discord_reader.py` | `ChannelMonitor` — user-token client, one channel |
| `commands.py` | Command aliases and “is this a `$settings` reply?” detectors |
| `constants.py` | Bot ids, kakera / sphere emoji names, ranks, **base SP** |
| `buttons.py` | Classify embed buttons (claim / kakera / sphere) |
| `message_text.py` | Flatten Components V2 `content` (``$shop`` and similar) |
| `parsers/` | One module per message kind (`tu`, `roll`, `settings`, `shop`, `ohu8`, …) |
| `parsers/pipeline.py` | Classify + parse a snapshot |
| `types.py` | `MessageKind`, `ParseResult`, `MudaeMessageSnapshot` |
| `event_log.py` | Unified Statistics store (`data/events.jsonl`); one-time import of the old `*_log.json` arrays (those files are left on disk) |
| `stats_index.py` | In-memory daily cube + paged `recent` rows for Statistics (never dumps the full log to QML) |
| `key_log.py` / `kakera_log.py` / `sphere_log.py` / `soulmate_log.py` | Record helpers on top of `event_log` |
| `minigame_log.py` / `chaos_capture.py` | Separate files: `data/minigame_log.json`, `data/chaos_log.json` |
| `settings_catalog.py` / `settings_commands.py` / `settings_preset.py` | GUI settings templates |
| `command_ack.py` / `command_context.py` / `claim_context.py` | Match replies to the command we just sent |

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

---

## Persisted model

All of this is one file: `data/settings.json` (never commit it).

| Layer | Store | Role |
|-------|--------|------|
| Who | `accounts[]` | Token, name, enabled channels, `$p`/`$daily` channel + cooldowns |
| Where | `servers[]` / `channels[]` | Channel snowflakes, fetched `$settings` / `$bonus`, `daily_resets` |
| How | `presets{}` | `MacroConfig` per preset id |
| Binding | `targets[]` | `{ account_id, channel_profile_id, preset_id }` |

Resolution for a run: `gui/run_target.py` → `resolve_run_target()`.

Also in that file: tray / update prefs, `ui_layout`, `ui_palette`. Session
logs go under `data/session_logs/`. Kakera / key / sphere / soulmate events
are `data/events.jsonl`. Statistics cards/charts use an in-memory daily cube
(`mudae/stats_index.py`); QML only receives a page of `recent` rows.
On first launch after that file is missing, the old `data/*_log.json` arrays
are imported and then left untouched. Minigame boards stay in
`data/minigame_log.json`; chaos capture stays in `data/chaos_log.json`.

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
