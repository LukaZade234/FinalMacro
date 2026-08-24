# TODO

Open work. Game rules: [`MUDAE_LOGIC.md`](MUDAE_LOGIC.md). Code map: [`ARCHITECTURE.md`](ARCHITECTURE.md).

Follow **Unlock path** unless you specifically want a quick win or a single high-impact slice. Skip list is at the bottom of **Colblitz tools**. New holes from a full-app pass: **Found in audit**.

---

## By ease

Cheapest first. “Easy” means a sitting or two and little new machinery.

1. **Empty states** — copy.
2. **Compile leftover parser regexes** — mechanical.
3. **Humanized delays** — jitter existing sleeps.
4. **Reaction power max on the account page** — move a hardcoded `155`.
5. **Timezones** — pick UTC (Mudae dailies), fix QML “today”.
6. **`$p` / `$daily`** — send at the right time; parsers exist.
7. **Chaos parser** — tighten an existing parse, do not invent a feature.
8. **`$dl` / `$adl` / `$wl` one-click** — GUI + send; no optimizer.
9. **Save power for perk 8** / **`$us` scheduling** — rules on top of engines that already run.
10. **Sphere tracking audit** (+ perk-9 colour, `$oc` from `$oh`) — investigation, then a log field.
11. **`$oc` leftover-click lookahead** — solver only; keep the geometric model.
12. **`$oh` histogram → DP** / **auto investor** / **app-only wishlist** — new modules, known shape.
13. **EventLog + JSONL** then **shared stats model** — medium, but one design kills five GUI bugs.
14. **Perk 9 threshold** / **`$bw` advisory** — easy arithmetic, blocked on bonus + data.
15. **`$ot` Phase 2** / **`$settings` / `$bonus` audit** / **full daily autonomy** / **Phase D** — real projects.
16. Last: split `bridge.py`, achievements, GUI polish. Do not hoist `uniqueSources` / cache `filteredEntries` if the shared model is next — they die with it.

---

## By importance

Highest first. What makes an overnight run correct and complete.

1. **`$settings` / `$bonus` audit** — nothing server-driven is trusted until this lands (claim-via-emoji, perk 9 DP, `$bw`, any rule from parsed settings).
2. **Full daily autonomy** — the product: one connect covers rolls, reacts, minigames, `$p`/`$daily`, and skips what is already exhausted.
3. **Sphere tracking + EventLog / shared stats** — totals are wrong and the GUI rebuilds 3 MB per event. Every later report and solver frequency sits on this.
4. **Phase D (multi account / server)** — only this high if alts or a second server are why the app exists; otherwise it waits.
5. **Unused or mis-spent daily budget** — `$ot` (parsed, not played), perk 9 static filter, perk 8 power not saved for refill.
6. **Reconnect / overlap holes** — `macro_active` cleared mid-run; hourly Start allowed during `$oh`. Overnight sessions mis-attribute `$tu` and can collide with a minigame.
7. **Timezones** — “today” and daily series lie across UTC midnight.
8. **Overnight completeness** — chaos parser, `$p`/`$daily`, `$us` on a clock.
9. **More SP from games we already play** — `$oh` DP / `$oc` lookahead. `$oq` stays MIXED (95.6% / 344.8, matches Colblitz MIXED; leave the DP chase).
10. **App-only wishlist** then **`$bw` advisory** — planning, not a session blocker.
11. **`$dl` switch**, humanized delays, empty states, reaction-power max, shell Run parity.
12. Last: achievements, split `bridge.py`, leftover regexes, GUI polish.

---

## Unlock path

Do this order. Early waves make later ones cheaper; items in the same wave can run in parallel.

**Wave 1 — cheap data, harness, and stop-the-bleeding**

- ~~ParseLab must not persist the live token on keystroke~~ — Debug uses the Run/Accounts token and no longer has a token field.
- ~~Soulmate rows: write `account_id` / `account_name` from Mudae `owner` (lukazade234).~~ QML fallback is `"Unknown"` only if a row still has no name.
- ~~After `force_reconnect`, restore `macro_active` if it was set.~~ `startMacro` refuses while a minigame is running.
- ~~`$oq` MIXED hunt.~~ Replay harness in `macro/oq_replay.py` (`scripts/oq_bakeoff.py`). Opening is Colblitz `(1,1)` (index 6). Finding 3 purples auto-reveals the 4th as a clickable red — we claim it, we do not search hidden cells. Two-purple hunt uses expectimax. Full replay MIXED **95.6% red / 344.8 avg** (Colblitz 95.4% / 342.7).
- Timezones. Every later “today”, daily report, and perk-8/minigame skip uses this clock.
- Sphere tracking audit: colour on `sphere_click`, `$oc` granted from `$oh`. Unblocks perk 9 frequencies and the `$oh` DP. `$oh` dark `turns into` + `(Free)` tracker lines are parsed (session log shows `spD → spP`). Minigame boards: `data/minigame_log.json` / Statistics → Minigames.
- Chaos parser in the same key/sphere pass.
- Empty states + reaction-power max while the GUI is open (stop lying).

**Wave 2 — two foundations (do not skip)**

- `$settings` / `$bonus` audit. Unblocks perk 9 DP, `$bw`, claim-via-emoji, and any rule driven by the server. Do not change claim / kakera / roll behaviour until this is done.
- One `EventLog` + append-only JSONL, then the shared stats / filter model. Unblocks daily report, session row, achievements. Kills the O(n²) `uniqueSources` and the four copy-pasted views.

**Wave 3 — close the daily loop on one account**

- `$p` / `$daily`, perk 8 power save, `$us` clock, humanized delays.
- Extend `daily_resets` (already used for perk 8) to `$oh` / `$oc` / `$oq` / `$ot` and sphere stock — this *is* most of “full daily autonomy”.
- `$dl` / `$adl` / `$wl` one-click if you want a GUI win in the same stretch.
- Shared Run action gating (pending + minigame flags) on Haul / Console / Boxed; put the update banner where every layout can see it. `$us` stop options only exist on Classic today.

**Wave 4 — spend the daily budget better**

- Perk 9 adaptive threshold (needs wave 1 colour + wave 2 `$bonus`).
- `$ot` play + Phase 2 enumerator (`$ohu` already counts it; wave 3 skip logic should already know the id).
- `$oc` leftover-click lookahead; `$oh` DP only if the wave 1 histogram is stable. `$oq` MIXED matches Colblitz — leave it.

**Wave 5 — after one account is boringly reliable**

- App-only wishlist → `$bw` advisory (needs wave 2 bonus). Never auto-send `$bw`.
- Auto sphere / kakera investor (needs wave 3 stock tracking).
- Phase D.
- Daily report / session row / achievements (need wave 2 logs).
- Split `bridge.py`, leftover regexes, GUI polish.

Optional / when asked: `$ov` parser. Skip unless someone wants them: disablelist optimizer, `spcalc`, YOGRTBot, klcalc.

---

## Parsers and server rules

- **`$settings` / `$bonus` audit** — capture `$bonus` the same way as `$settings`; fix both parsers field-by-field (`docs/archive/MUDAE_SETTINGS_COMMANDS.md`); then use parsed fields in macro decisions. 16 commands are **direct toggles** (bare send flips the live server) — capture tooling must skip or auto-revert them. Claim-via-emoji stays blocked until this lands.
- **Chaos parser** — chaos-kakera bonus rolls (1–15+ extra) are not logged; `$us` spends them but overnight runs cannot show when they appeared. Tighten key / chaos-kakera parse while here.
- **Optional `$ov` parser** — parse when we need it; do not send it unless asked.
- **Sphere tracking audit** — totals / sources look wrong. Check roll clicks vs `$oh` / `$oc` / `$oq` rewards, invested-sphere bonuses, and perk 9. `$oh` hidden clicks that show ``spU`` in chat now grant ``$oc`` (play-all spends them like bonus `$oq`). While here, log perk-9 button **colour** (not just SP amount) so the Colblitz p9 threshold can use our own frequencies.
- **`$p` / `$daily`** — send and record the daily poke / `$daily` at the right time.

Do not change per-server claim / kakera / roll rules until the settings audit (steps above) is done.

---

## Daily loop and scheduling

- **Full daily autonomy** — one connect should cover rolls, reacts, minigames, `$p`/`$daily`, and skip anything already exhausted until refill. Perk 8 skip exists (`macro/perk8_daily.py`); extend `daily_resets` the same way for `$oh` / `$oc` / `$oq` / `$ot` and sphere stock.
- **Save power for perk 8 refresh** — stop paid kakera reacts near the daily refill so the bar is full when perk 8 comes back. Purple stays free.
- **Auto sphere / kakera investor** — spend stock into `$oh` / kakera invest without a manual click.
- **`$ot` solver** — play `$ot` (parsed in `$ohu`, not played). Method notes in **Colblitz tools** below.
- **`$us` scheduling** — start / stop `$us` on a clock (not only a manual button), including the reset-margin so a reset does not wipe the stack.
- **Humanized delays** — jitter command / click timing so the session is less metronomic.

---

## Accounts and servers

- **Multi account / server runtime (Phase D)** — config already has accounts, channels, presets, and `targets[]`. Runtime is still one Discord connection. Coordinator must resolve `(account, channel) → preset` per target (never “first preset on the account”). Covers alt accounts and a multi-server setup UI. See Phase D in `ARCHITECTURE.md`.
- **App-only wishlist** — wishlist the macro claims from, separate from Mudae’s `$wish`.
- **`$dl` / `$adl` / `$wl` one-click switch** — swap those lists from the GUI without typing the commands. Not the same as Colblitz’s disablelist *optimizer* (needs a bundle database we do not have).

---

## Statistics and GUI

Do the shared model first; the copy-paste and most of the slowness go away with it.

- **Stats payload is rebuilt from scratch on every event** — `kakeraJson` / `spheresJson` / `keysJson` enrich every row, `build_stats` over the whole log, then `json.dumps` into QML. Measured ~64 ms / 3 MB at 8k events, and it runs on each notify while the tab is open. Split totals/series (incremental) from the row list (`QAbstractListModel`).
- **Four stats views are the same file** — `filteredEntries`, `uniqueAccounts`, `uniqueServers`, `serverKey`, `filteredTotals` copied across Kakera / Spheres / Keys / Soulmates. One shared filter model (Python if the payload moves there). **Share filter state** too — “account: X” on Kakera should still be X on Spheres.
- **`uniqueSources()` is O(n²)** — `SpheresView.sourceBreakdown` / `KeysView` call it inside the inner loop (and it walks all entries each time). Hoist if the shared model is not next; otherwise it dies with the shared model.
- **`filteredEntries()` is a function in bindings** — every re-eval re-filters; `sourceBreakdown` / series / totals each call it again. Cache as a property if views stay in QML.
- **Four log modules are one class** — `kakera_log` / `sphere_log` / `key_log` share load/save/account helpers; `soulmate_log` still writes the whole file synchronously. One `EventLog` + four small record functions. While there: **append-only JSONL** instead of rewriting the pretty JSON list on every flush (`DebouncedJsonLog` still `json.dumps` the full list).
- **Timezones** — log `date_key` is UTC; QML “today” / week / month use local `Date`. Crossing midnight UTC vs local makes “today” and daily series lie. Pick one clock (Mudae dailies are 00:00 UTC) and use it in both layers.
- **Reaction power max is hardcoded `155`** — `DEFAULT_MAX_REACTION_POWER` / `AccountState.power_max_percent`. Badge-dependent; belongs on the account page. Efficiency math is wrong when it is stale.
- **Empty states** — “No spheres logged yet” should say the macro has to be connected and running for anything to record.
- **Session row on Statistics** — one line per connect/disconnect with kakera + spheres + keys + claims. Today each log is filtered alone (`gui/run_summary.py` already does a session haul on Run).
- **Daily report** — end-of-day kakera / sphere breakdown for invest / perk-8 planning.
- **GUI polish** — leftover layout / copy / empty-page work after the items above.

---

## Later (not blocking)

- **Split `gui/bridge.py`** — ~2.7k lines, 90+ slots. Logical groups already exist (run, config, stats, mudae settings, updates). Separate context properties once the stats payload is off the JSON string. Leave `macro/roll_cycle.py` alone; it is long because the domain is.
- **Compile leftover parser regexes** — many `mudae/parsers/` patterns are still built inside functions. Move to module constants on the hot path.
- ~~**`$oq` opening move**~~ — Colblitz overlay `(1,1)` (0-based, index 6). Short-circuits on a blank board. Hunt is MIXED; leave the Bellman DP.
- **Achievements** — soulmate / chaos-key / rainbow milestones. After the logs are one `EventLog`.

---

## Found in audit

Pass over the running app after the rankings above. Items already listed earlier are not repeated.

### Bugs

- ~~**ParseLab writes the live token on every keystroke**~~ — Debug no longer edits the token; Connect/Disconnect sync on load.
- ~~**Hourly Start is allowed during a minigame**~~ — `startMacro` uses the same busy check as `$us` / minigame buttons.
- ~~**`force_reconnect` clears `macro_active` and never puts it back**~~ — flag is restored when it was set before the reconnect.
- ~~**Hardcoded `lukazade234` display fallback**~~ — soulmate rows get `account_name` from `owner`; missing name shows `"Unknown"`. The duplicate GUI profile still named Default is leftover config, not a display hack.
- **`CLAIM_INTERVAL` is parsed and then ignored** — pipeline classifies “once per interval” rejections; `wait_for_claim` only accepts `CLAIM` / `MARRIAGE`, so the attempt times out, `claim_available` stays true, and the macro may retry into the same wall.
- **Unknown reaction power is treated as infinite** — `can_afford_reaction` returns true when `power_percent is None`. After a skipped `$tu` or a partial restore, paid kakera fire until Mudae denies. `$us` stop-on-power does the opposite (returns false when unknown) and also assumes a chaos key when computing min cost, so it stops too late without one.
- ~~**`$oh` dark “turns into” was dropped**~~ — Mudae writes `<:spD:…> turns into <:spP:…>` (no `**+**` on that line) then `<:spP:…> (Free) **+N**`. Parser now reads transform + `(Free)` lines; dark stays a **paid** click and the session log shows `spD → spP`. Hidden clicks log `hidden → spY` (etc.) instead of just `hidden`. Stats rows: `data/minigame_log.json` and Statistics → Minigames — not `data/session_logs/`.

### Robustness (not wrong today, fail overnight)

- **`$oc` / `$oq` have no click retry** — `$oh` resends on ack timeout; the other two abort the batch. Play-all then stops the whole chain, so remaining `$oc`/`$oq` uses from `$ohu` are left unspent.
- **`$us` slow-path add does not use the reconnect wrapper**; a single 503 fails the add. Reconnect retries once, then aborts.
- **Perk-6 queue drain does not match parent character** — late spawns are serviced (good) but a stale “Akame spawned by POWER” can attach to the next `Rem` roll (bad for session records). The wait path already requires `parent_character`.
- **Perk-8 budget: `rule_eval` vs `KakeraReactor`** — rule_eval still returns perk-8 kakera when the daily budget is 0; the reactor then skips the whole roll if any paid candidate remains. Integration-test the reactor, not only `rule_eval`.
- **`SphereReactor` is fire-and-forget** — HTTP click success is logged as a sphere; no wait for the `(used/max)` line, no megasphere-exhausted handling. `$ohu` already prints `No :spM: left today` and `N/15 buttons clicked` and we ignore both.
- **Resume holes** — `macro_runtime` snapshot omits perk-8 click counts; claim cooldown restore subtracts wall-clock minutes instead of using the claim-reset instant; legacy flat `daily_resets` is dropped with no migration.
- **Quit is fire-and-forget** — `shutdown()` persists and disconnects without waiting for the reader thread or an in-flight minigame.

### GUI (shells drifted)

Classic Run (`RunView` + `MacroControlBar`) and Haul/Console/Boxed (`RunModel` + `*RunPage`) are two products:

- `$us` stop-on-power / stop-after-N only on Classic.
- Update banner only on Classic; tray text says “see the Run tab”.
- Session haul / last claim / perk 8·9 chips only on the new shells; Classic never reads `runSummaryJson`.
- `RunModel.dkNextMinutes` and `TargetModel.warning` are computed and not shown.
- Notification-standby banner only on Classic.
- No confirm on delete account/server/preset, live `$settings` Apply, or legacy import.
- Changing Run target while connected silently stops the macro.
- Mudae “Apply to server” channel pickers do not follow the Run target.
- Compact Run preset combo shows preset **ids**, not names.
- Dead: `PhaseStepper.qml`, `ServerChannelSelectors.qml`, `App.mudaeSettingsCatalogJson`, `App.macroActivityLog` (plain-text duplicate).

### Ideas that fit this app

- **Shared `RunControls`** — one gating/loading implementation; Classic migrates onto `RunModel`.
- **Update banner in `Main.qml` / Settings** — pull + restart on every layout.
- **Confirm + command preview before live `$settings` Apply.**
- **Tray: notify on wish/claim** (tray already exists; menu is Show + Quit only). Optional Connect / Start / Stop.
- **Claim-interval hold** — on `CLAIM_INTERVAL`, set cooldown from `next_interval_minutes` instead of timing out.
- **Sphere daily-cap advisor** — parse `$ohu` button/megasphere lines; disable the sphere reactor when the roll-button cap is hit.
- **`$oc`/`$oq` retry + play-all continues after one failed batch.**
- **Stats CSV/JSON export** of the filtered rows (local file).
- **Minigame resume checkpoint** — persist grid signature after each ack so a disconnect does not forfeit the `$ohu` use.
- **ParseLab sandbox token** — debug connection isolated from the Accounts store.

Not bugs: `min_kakera` is labelled “instant trigger” in Presets and is *not* an end-of-batch floor — `claim_best` picking the highest remaining ka is the intended fallback.

---

## Colblitz tools vs this app

Compared [colblitz.com/mudae](https://colblitz.com/mudae/) and [`docs/archive/mudae-tools-dev-guide.md`](archive/mudae-tools-dev-guide.md) (Claude’s rebuild spec) against our solvers. Their site is a **browser helper + hosted Discord bot**. We already auto-play `$oh` / `$oc` / `$oq`. Do not rebuild their website or YOGRTBot. Steal algorithms that raise our SP; skip tools that need datasets or a second UI we would never keep current.

Full section-by-section build notes: [`docs/archive/mudae-tools-dev-guide.md`](archive/mudae-tools-dev-guide.md). Index: [`docs/archive/README.md`](archive/README.md).

The guide is a fair transcription of their published “How it works” pages. Several things it marks UNVERIFIED we already settled in code (dark `$oh` pays immediately; purple from dark shows on the **reward tracker**, not the grid). Fold any port into `macro/*_solver.py` — do not start a parallel `mudae-tools/` tree.

### Solvers — room to improve

- **`$oq` — MIXED is live; leave it.** Hunt scores `α·P(purple) + β·Gini` (α=1 β=0.1). Opening is Colblitz overlay `(1,1)` (0-based, index 6). Mudae auto-reveals the 4th purple as a clickable red (or rainbow) once 3 are found — the live loop waits for that grid edit instead of probing hidden cells. When 2 purples are already found, hunt expectimax treats the third as a free click that unlocks the auto-red. Full replay (`scripts/oq_bakeoff.py`, all 12,650 worlds, our base SP): MIXED **95.6% red / 344.8 avg**, entropy **92.2% / 337.8**. Colblitz MIXED 95.4% / 342.7; their Bellman DP is 98.1% / 356.3. Remaining MIXED losses never find 3 purples. Do not chase hunt-wide expectimax / full DP unless we specifically want those ~11 SP. Boards log to `data/minigame_log.json` (Statistics → Minigames).

- **`$oh` — medium, blocked on frequencies.** They run a Bellman DP over *counts* `(clicks left, covered, blue, teal, dark, top flats)` — position does not matter. We never click revealed blue/teal and otherwise take the highest revealed paid sphere, else a random `spU` (`macro/sphere_game.py`). That static skip is wrong with 1–2 clicks left (a teal at 20, or a blue that unveils 3 cells, can beat a face-down). **Action:** log colour / value of each `$oh` reveal (including `$oc` procs — see sphere-tracking audit) until the reveal table is stable; then add `oh_solver.py` and keep greedy as fallback. Do not ship a DP on guessed priors.

- **`$oc` — medium.** They weight each of the 24 reds equally, then do a 5-click Bellman DP over colour outcomes (max total SP, not “find red”). We already treat candidate reds as equally likely. We do **not** enumerate full boards — geometric filters from [mudaehelper](https://mudaehelper.pages.dev) (`macro/oc_solver.py`) — because the published 2-orange / 3-yellow / 4-green generator is inconsistent for some reds (their page and the guide both admit this). Hunt is 1-ply information gain + opening `(4,2)`; collect is red → orange → yellow → green. **Action:** keep the geometric model (it survives a wrong generator). Add shallow lookahead on leftover clicks once red is known, and on hunt when ≤3 clicks remain. Optional later: fit `P(colour at cell | red)` from logged full boards; that is the only way their exact DP becomes better than our constraints. Do not guess the generator.

- **`$ot` — hard, already on the daily-loop list.** Battleship on a 5×5: ships are free, 4 blue clicks, Extra Chance until 5 ship hits. They enumerate placements with a bitmask DFS, then a two-phase policy. Phase 1 (Extra Chance on) uses a **learned** scorer they do not publish. Phase 2 is simple: click every cell with `P(blue)=0`, then gamble on EV vs ending the run. Their solver is labelled BETA. **Action:** port the game loop from `$oc`/`$oq`; implement the enumerator + Phase 2 first (that is most of a perfect game). Hand-tune Phase 1 against a simulator — we will not match their policy table. Rare-ship SP is 76 / 104 / 150 / 500 (Light / Dark / Red / Rainbow), not a flat ~90.

### Calculators — new features, not solver ports

- **Perk 9 click/skip DP — medium, highest daily value of the calculators.** [p9calc](https://colblitz.com/mudae/p9calc): `EV(colour) = (base × (1 + double) + flat) × (1 + SP9×0.10)`, daily cap `10 + SP9`, then `V(rolls left, clicks left)` so the threshold **falls** as the day runs out. We have a static `SphereReactionRules.types_allowed` and no remaining-budget awareness. **Action:** after the `$bonus` audit, compute the threshold table and use it in `passes_sphere_reaction` (click if `EV ≥ V[r-1][c] − V[r-1][c-1]`). Seed frequencies from our `sphere_click` log; label them provisional until the sample is large. A standalone “how many OP9 chars to skip teal” page is optional — the live advisor is the part that belongs in this app.

- **`$bw` / key EV — medium, advisory only.** [bwcalc](https://colblitz.com/mudae/bwcalc): sweep `$bw` for keys/hour (wishlist / starwish / per-character). Formulas are published; **absolute** keys/hr are community guesses — the *peak* is what to trust. **Action:** a Settings/Utilities paste of `$bonus` + `$wlsz+z!` after the bonus audit and the app-only wishlist. Never auto-send `$bw`. Depends on those two items.

- **Disablelist optimizer — skip for now.** [dlcalc](https://colblitz.com/mudae/dlcalc) is set-cover + pool caps. The ILP is a day; the **bundle↔character dump** is the real product and goes stale. Keep the one-click `$dl`/`$adl`/`$wl` switch. Revisit only if we ingest a refreshable dump ([MudaeDB](https://github.com/LilJamJam/MudaeDB) / [DL-Builds](https://github.com/PRCSakura/Mudae-DL-Builds)).

- **Sphere upgrade planner (`spcalc`) — skip.** [spcalc](https://colblitz.com/mudae/spcalc) is the heaviest tool (OP9/OP5/OP8/OP10/SP2/SP5/SP10 income + discounted upgrade order). Needs `$shop` and `$mmsz=z!` parsers we do not have. Users can keep using the site. If we ever want it, it is a multi-day transcription, not a macro feature.

### Skip entirely

- **YOGRTBot live solver** — a bot you invite so a browser overlay updates on message edit. We already parse the 5×5 from component rows and click. A recommend-only Discord bot is a different product (and a different ToS surface).
- **klcalc** — they unlisted it from the index (2026-08-20). Ignore.
- **Heatmaps / click-history / harvest explainer** — web-solver chrome. Our log line (`format_solver_stats`) is enough.
- **Their hosted stats tables** — games *their* bot saw, not ours.

Solver/calculator pickup order is the **Unlock path** waves 1 and 4 (and `$bw` in wave 5). Do not start perk 9 or `$bw` before the `$bonus` audit.

Public Python references if a port stalls: [Svessinn/Mudae](https://github.com/Svessinn/Mudae) (all four games + sims), [GAP22/oq-solver](https://github.com/GAP22/oq-solver), [mudae-sphere-solver](https://github.com/ShrimpandGGrits/mudae-sphere-solver). Colblitz itself is server-side — no client JS to read.
