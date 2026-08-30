# TODO

Open work. Game rules: [`MUDAE_LOGIC.md`](MUDAE_LOGIC.md). Code map: [`ARCHITECTURE.md`](ARCHITECTURE.md).

Follow **Unlock path** unless you specifically want a quick win or a single high-impact slice. Skip list is at the bottom of **Colblitz tools**. New holes from a full-app pass: **Found in audit**.

---

## By ease

Cheapest first. “Easy” means a sitting or two and little new machinery.

1. ~~**Empty states** — copy.~~ `gui/emptyStates.js`: disconnected vs nothing recorded vs filters.
2. ~~**Compile leftover parser regexes** — mechanical.~~ Module-level `_…_RE` in `tu`, `roll`, `settings`, `claim`, `kakera`, `bonus`, `utils`, etc.
3. ~~**Humanized delays** — jitter existing sleeps.~~ Opt-in on the Rolls preset tab (`humanize_roll_delay` + adjustable `roll_delay_jitter_sec`).
4. ~~**Reaction power max on the account page** — `kakera_max_power` is parsed from `$bonus`; still not wired (hardcoded `155`).~~ Wired from the run channel's `$bonus` (`macro/sheet_caps.py`).
5. ~~**Timezones** — pick UTC (Mudae dailies), fix QML “today”.~~ Live feed is local; stats “today” is UTC.
6. ~~**`$p` / `$daily`** — send at the right time; parsers exist.~~ Account-global; designated channel on the Accounts tab; priority over rolls.
7. ~~**Chaos parser** — after `data/chaos_log.json` has documented cases; capture is in place.~~ Parser in `mudae/parsers/chaos.py`; extra rolls are spent this hour, free kakera / wish follow-ups are acted on, power discount applied on spend, omega keys logged. `$kl` / stored minigames are logged only.
8. **`$dl` / `$adl` / `$wl` one-click** — GUI + send; no optimizer.
9. ~~**Save power for perk 8** / **`$us` control**~~ — perk-8 reserve in `macro/perk8_power.py`; `$us` drain / schedule on the preset (`us_keep_draining`, local window, roll cap). Run page is only the Roll `$us` button.
10. ~~**Sphere tracking audit** (+ perk-9 colour, `$oc` from `$oh`) — investigation, then a log field.~~ Perk-9 colour on `sphere_click`, `$oc` from `$oh` not double-counted as SP, no overlap between `$oh` reward / perk 10 / kakera / perk 9; Statistics “today” matches hand tally. Optional `scripts/sphere_audit.py` deferred unless needed again.
11. ~~**`$oc` leftover-click lookahead**~~ — remaining-need-aware collect EV + widened hunt-endgame guess threshold, geometric model kept (`macro/oc_solver.py`). +1.25 SP/board on 100 real logged boards, not significant; further `$oc` tuning is blocked on sample size, not ideas.
12. **`$oh` histogram → DP** / **auto investor** / **app-only wishlist** — new modules, known shape.
13. ~~**EventLog + JSONL**~~ then ~~**daily cube + paged stats**~~ — tables no longer parse the full log; shared filter state across tabs and a Qt list model can wait.
14. ~~**Perk 9 threshold**~~ / **`$bw` advisory** — perk-9 EV + DP is wired (`macro/perk9_threshold.py`, opt-in `budget_aware`). `$bw` advisory still needs `rolls_per_hour["penalties"]["bw"]`.
15. **`$ot` Phase 2** / **use parsed `$settings`/`$bonus` in decisions** / **full daily autonomy** / **Phase D** — real projects.
16. Last: split `bridge.py`, achievements, GUI polish.

---

## By importance

Highest first. What makes an overnight run correct and complete.

1. **Use parsed `$settings` / `$bonus` in decisions** — parse-and-store is done; claim-via-emoji, perk 9 DP, `$bw`, and any rule from those fields still wait.
2. **Full daily autonomy** — the product: one connect covers rolls, reacts, minigames, `$p`/`$daily`, and skips what is already exhausted.
3. ~~**Sphere tracking + EventLog / shared stats**~~ — EventLog + daily cube + paged stats tables. Totals/charts no longer walk every event in QML.
4. **Phase D (multi account / server)** — only this high if alts or a second server are why the app exists; otherwise it waits.
5. **Unused or mis-spent daily budget** — `$ot` (parsed, not played). ~~Perk 9 static filter~~ — opt-in adaptive threshold spends the daily clicks by EV.
6. **Reconnect / overlap holes** — `macro_active` cleared mid-run; hourly Start allowed during `$oh`. Overnight sessions mis-attribute `$tu` and can collide with a minigame.
7. ~~**Timezones** — “today” and daily series lie across UTC midnight.~~ UTC `date_key` + UTC stats buckets; live feed local.
8. ~~**Overnight completeness** — chaos *parser* (capture is `data/chaos_log.json`).~~ Parser + follow-up in `KakeraReactor` / `chaos_followup.py`; raw windows still go to `data/chaos_log.json`.
9. **More SP from games we already play** — `$oh` DP. ~~`$oc` lookahead~~ — done and measured on real boards (+1.25 SP/board, not significant); `$oc` is at the ceiling of this approach, leave it. `$oq` stays MIXED (95.6% / 344.8, matches Colblitz MIXED; leave the DP chase).
10. **App-only wishlist** then **`$bw` advisory** — planning, not a session blocker.
11. **`$dl` switch**, shell Run parity.
12. Last: achievements, split `bridge.py`, leftover regexes, GUI polish.

---

## Unlock path

Do this order. Early waves make later ones cheaper; items in the same wave can run in parallel.

**Wave 1 — cheap data, harness, and stop-the-bleeding**

- ~~ParseLab must not persist the live token on keystroke~~ — Debug uses the Run/Accounts token and no longer has a token field.
- ~~Soulmate rows: write `account_id` / `account_name` from Mudae `owner` (lukazade234).~~ QML fallback is `"Unknown"` only if a row still has no name.
- ~~After `force_reconnect`, restore `macro_active` if it was set.~~ `startMacro` refuses while a minigame is running.
- ~~`$oq` MIXED hunt.~~ Replay harness in `macro/oq_replay.py` (`scripts/oq_bakeoff.py`). Opening is Colblitz `(1,1)` (index 6). Finding 3 purples auto-reveals the 4th as a clickable red — we claim it, we do not search hidden cells. Two-purple hunt uses expectimax. Full replay MIXED **95.6% red / 344.8 avg** (Colblitz 95.4% / 342.7).
- ~~Timezones.~~ Mudae dailies / `date_key` / stats “today” are UTC (`mudae/clock.py`, `gui/clock.js`). In-app live feed stays local time (Classic `ActivityLogPanel` + Haul `RunModel.timeOf`).
- ~~Sphere tracking audit~~ — colour on `sphere_click`, `$oc` granted from `$oh` (not SP), no double-count vs perk 10 / kakera / perk 9; Statistics “today” verified. First `$oh` invested-sphere line is **perk 10** (`$oq` / `$ot` / flat SP) — SP source `perk10`, extra `$oq`/`$ot` on the `$oh` minigame session. Unblocks perk 9 frequencies and the `$oh` DP. `$oh` dark `turns into` + `(Free)` and light `breaks down into` tracker lines are parsed. Minigame boards: `data/minigame_log.json` / Statistics → Minigames.
- ~~Chaos parser in the same key/sphere pass.~~ Capture: every Mudae message after a `kakeraC` click until the next commanded roll **or 8s of silence** goes to `data/chaos_log.json`. Parser + acting is the next bullet.
- ~~**Chaos parser wired**~~ — `mudae/parsers/chaos.py` on the `+$k` body (`+N rolls this hour`, stored `$oh`/`$oc`/`$oq`/`$ot`, `$kl`, `N%` power discount, omega `$ok`, owned free kakera, wish spawn). Shop 5 `(Shop 5) +1 $ot stored!` is separate (any kakera react). Extra rolls are added to `rolls_left` and spent before hourly refill. Free kakera clicked at 0 power; wish uses `claim_on_wish_ping` + `$rt` when that toggle is on. Discount applies when spending tracked power, not as a pre-click guess.
- ~~Reaction-power max is parsed (`kakera_max_power`) but not wired.~~ `kakera_max_power` from `$bonus` and `perk9_click_max` from `$shop` are applied to the run-channel state.

**Wave 2 — two foundations (do not skip)**

- ~~`$settings` / `$bonus` parse audit~~ — fixtures + meaning catalog + field-by-field tests; capture skips the 16 direct toggles; `$bonus` is read-only (source tags are not sent). Storage trusted; **do not** change claim / kakera / roll behaviour until a later slice wires the fields. Unblocks perk 9 DP / `$bw` / claim-via-emoji *work*, not those behaviours yet.
- ~~One `EventLog` + JSONL (`data/events.jsonl`; one-time import of the old JSON arrays, which stay on disk).~~
- ~~Daily cube + paged Statistics (`stats_index`; `App.statsQuery`).~~ Cards/charts sum daily cells; tables load 80 rows at a time. Shared filter state across Kakera/Spheres/Keys/Soulmates and a `QAbstractListModel` can wait.

**Wave 3 — close the daily loop on one account**

- ~~`$p` / `$daily`~~ — designated per-account channel; auto-send on cooldown with roll priority.
- ~~Extend `daily_resets` (already used for perk 8) to `$oh` / `$oc` / `$oq` / `$ot` and sphere stock~~ — `macro/minigame_daily.py` + `macro/perk9_daily.py`; play-all / hourly skip minigames until UTC refill. Perk 9 / megasphere counts persist for the Run tab; the reactor does not skip — Mudae stops spawning those buttons.
- ~~**Perk 8 power / `$dk` reserve**~~ — optional on the perk-8 budget panel (`perk_8_power_save`). Off = old click/`$dk` rules. On = pay remaining perk-8 first (they expire at UTC midnight); after 40/40 still take chaos kakera and hold `$dk` unless a new use is back by midnight. Usual `$dk` cooldown is **20h**.
- ~~**`$us` control**~~ — preset drain policy + optional **local** time window (`us_schedule_*`, not UTC). Manual / keep-draining / power stop / session roll cap live on Presets → `$us`. **Roll `$us`** starts immediately (ignores the window). The window is an automatic drain while connected, like `$p` / `$daily`; leftover `$us` stays on the stack at end time. Hourly waiting for a refill yields to the window, then resumes.

**Wave 4 — spend the daily budget better**

- ~~Perk 9 adaptive threshold~~ — `macro/perk9_threshold.py`: EV formula + `V(spawns, clicks)` DP, opt-in `SphereReactionRules.budget_aware`. Colours/rates editable per preset (Colblitz's 138,925-roll table as defaults). Spawns left come from `$ohu9`'s `(Perk 9) Rolled today`. Score with `scripts/perk9_bakeoff.py`.
- `$ot` play + Phase 2 enumerator (`$ohu` already counts it; wave 3 skip logic should already know the id).
- ~~`$oc` leftover-click lookahead~~ — shipped, then audited against **100 real logged boards** (`scripts/oc_bakeoff.py --from-log docs/minigames_to_use.jsonl`). `macro/oc_solver.py`: collect-phase EV tracks remaining need per region instead of a fixed weight per colour, and hunt widens its "guess red" threshold from `≤2` candidates to `≤clicks_left` once 3 or fewer clicks remain. **Measured: +1.25 SP/board (335.80 vs 334.55), t = 1.41 — not significant, changes only 2 boards in 100; ~200 boards needed to confirm.** Directionally positive, kept, but do not describe it as a win. A deeper recursive hunt lookahead was tried and reverted (it lost SP and, on a real screenshot-derived fixture, talked itself out of ever guessing red). `$oh` DP only if the wave 1 histogram is stable. `$oq` MIXED matches Colblitz — leave it.
- **`$oc` measured dead ends** — all replayed on the same 100 boards, none shippable. **MIXED hunt scoring** (`info_gain + β·EV`, mirroring `$oq`): +1.35 SP, t = 0.43, would need **~2,200 boards** to confirm; the synthetic benchmark rated it best at β≈0.3, and a 30-board sample rated it −8.83 SP, which flipped to +1.35 at 100 boards — it was noise both times. **Disjoint O/G regions**: 0.00 SP, and *disproven* — greens sit on orthogonally adjacent cells 22% of the time, so the region overlap is correct, not a bug. **Clicking the centre**: 0.00 SP. **Real `SPHERE_BASE_SP` values**: 0.00 SP (shipped anyway — it is the correct objective). Do not re-derive these without a much larger log.

**Wave 5 — after one account is boringly reliable**

- App-only wishlist → `$bw` advisory (needs wave 2 bonus). Never auto-send `$bw`.
- Auto sphere / kakera investor (needs wave 3 stock tracking).
- Phase D.
- Daily report / session row / achievements (need wave 2 logs).
- Split `bridge.py`, leftover regexes, GUI polish.

Optional / when asked: `$ov` parser. Skip unless someone wants them: disablelist optimizer, `spcalc`, YOGRTBot, klcalc.

---

## Parsers and server rules

- ~~**`$settings` / `$bonus` parse audit**~~ — parsers trusted for storage (`tests/mudae_sheet_fixtures.py`, `mudae/parsers/bonus_catalog.py`). Capture tool skips or reverts the 16 direct toggles; `$bonus` dump is read-only. **Follow-ups (not done):** claim-via-emoji, driving `CharacterClaimRules` / kakera / sphere reacts from settings. `kakera_max_power` and perk 9 click cap are wired from the run channel's sheets.
- ~~**`$shop` parser**~~ — ouroperk sheet (OP1–OP10, perk 9 extra clicks +
  SP%, megasphere rewards). Components V2 capture + parse-and-store on the
  channel profile (`App.fetchShop`). `perk9_click_max` drives the daily click
  cap. p9calc / spcalc still wait. Do not send `$shoprefund`.
- ~~**Chaos parser**~~ — `mudae/parsers/chaos.py` + `macro/chaos_followup.py`. Extra hourly rolls are spent (not left for `$tu` / refill). Free kakera / wish spawns are clicked / claimed. `$kl` and stored minigames are logged only. Raw windows still go to `data/chaos_log.json`.
- **Optional `$ov` parser** — parse when we need it; do not send it unless asked.
- **Sphere tracking audit** — totals / sources look wrong. Check roll clicks vs `$oh` / `$oc` / `$oq` rewards, perk 10 invested-sphere bonuses (`$oq` / `$ot` / flat SP on the first `$oh` of the day), and perk 9. `$oh` hidden clicks that show ``spU`` in chat now grant ``$oc`` (play-all spends them like bonus `$oq`). While here, log perk-9 button **colour** (not just SP amount) so the Colblitz p9 threshold can use our own frequencies.
- ~~**`$p` / `$daily`**~~ — account-global; one designated channel per account (Accounts tab); auto-send when ready, before rolls; sequential if several accounts have a channel set.

Do not change per-server claim / kakera / roll rules until a slice *uses* the parsed settings / bonus fields (parse-and-store is done; wiring is not).

---

## Daily loop and scheduling

- **Full daily autonomy** — one connect covers rolls, reacts, minigames, `$p`/`$daily`, and skips minigames already exhausted until refill. `$p`/`$daily` send on a designated channel; perk 8 / minigame skip live in `daily_resets`; `$us` keep-draining can pause/resume on the preset.
- ~~**Save power for perk 8 refresh**~~ — `macro/perk8_power.py` keeps bar + `$dk` payable for today's remaining perk-8 clicks (horizon `min(N hours, time until UTC midnight)`, default 4h). Today beats tomorrow: unused clicks die at reset. After 40/40, chaos kakera still click; `$dk` on those only if a replacement is back by midnight (typical cooldown **20h**). Purple stays free.
- **Auto sphere / kakera investor** — spend stock into `$oh` / kakera invest without a manual click.
- **`$ot` solver** — play `$ot` (parsed in `$ohu`, not played). Method notes in **Colblitz tools** below.
- ~~**`$us` control**~~ — drain / optional local schedule on the preset; session roll cap and window end are hard stops. Power stop is a separate toggle. Reset-margin already exists (`us_reset_margin_minutes`).
- ~~**Humanized delays** — jitter command / click timing so the session is less metronomic.~~ Opt-in roll jitter in preset Rolls settings.

---

## Accounts and servers

- **Multi account / server runtime (Phase D)** — config already has accounts, channels, presets, and `targets[]`. Runtime is still one Discord connection. Coordinator must resolve `(account, channel) → preset` per target (never “first preset on the account”). Covers alt accounts and a multi-server setup UI. See Phase D in `ARCHITECTURE.md`.
- **App-only wishlist** — wishlist the macro claims from, separate from Mudae’s `$wish`.
- **`$dl` / `$adl` / `$wl` one-click switch** — swap those lists from the GUI without typing the commands. Not the same as Colblitz’s disablelist *optimizer* (needs a bundle database we do not have).

---

## Statistics and GUI

Do the shared model first; the copy-paste and most of the slowness go away with it.

- ~~**Stats payload is rebuilt from scratch on every event**~~ — `stats_index` keeps a daily cube; QML gets summary fields plus 80 `recent` rows (`App.statsQuery`). A `QAbstractListModel` can still replace JSON paging later.
- **Four stats views still copy filter chrome** — account/server combos are per-tab. Share filter state so “account: X” on Kakera stays X on Spheres.
- ~~**`uniqueSources()` is O(n²)**~~ — breakdowns come from the cube.
- ~~**`filteredEntries()` walked the full log in QML**~~ — tables bind to `payload.recent`.
- **Wave 2 EventLog (storage):** one `data/events.jsonl` for kakera / spheres / keys / soulmates. Existing `data/*_log.json` arrays are imported once and left on disk.
- ~~**Timezones** — log `date_key` is UTC; QML “today” / week / month use local `Date`.~~ `mudae/clock.py` + `gui/clock.js`: UTC for `date_key` / stats “today”; live feed local.
- ~~**Reaction power max is hardcoded `155`**~~ — run-channel `$bonus.kakera_max_power` via `macro/sheet_caps.py`; 155 remains the fallback when `$bonus` has not been fetched.
- ~~**Empty states**~~ — disconnected vs nothing recorded vs filters (`gui/emptyStates.js`).
- **Session row on Statistics** — one line per connect/disconnect with kakera + spheres + keys + claims. Today each log is filtered alone (`gui/run_summary.py` already does a session haul on Run).
- **Daily report** — end-of-day kakera / sphere breakdown for invest / perk-8 planning.
- **GUI polish** — leftover layout / copy / empty-page work after the items above.

---

## Later (not blocking)

- **Split `gui/bridge.py`** — ~2.7k lines, 90+ slots. Logical groups already exist (run, config, stats, mudae settings, updates). Separate context properties once the stats payload is off the JSON string. Leave `macro/roll_cycle.py` alone; it is long because the domain is.
- ~~Compile leftover parser regexes~~ — hot-path patterns hoisted to module constants in `mudae/parsers/`.
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
- ~~**`$oh` dark “turns into” / light “breaks down into” were dropped**~~ — Dark: `<:spD:…> turns into <:spP:…>` then `(Free) **+N**`. Light: `:spL: breaks down into :spB: + … => +156` (fragments, not a single `**+**` on `spL`). Dark/light stay paid; session log shows `spD → spP` / `spL → spB+…`. Hidden clicks log `hidden → spY`. Stats: `data/minigame_log.json` / Statistics → Minigames.

### Robustness (not wrong today, fail overnight)

- **`$oc` / `$oq` have no click retry** — `$oh` resends on ack timeout; the other two abort the batch. Play-all then stops the whole chain, so remaining `$oc`/`$oq` uses from `$ohu` are left unspent.
- **`$us` slow-path add does not use the reconnect wrapper**; a single 503 fails the add. Reconnect retries once, then aborts.
- **Perk-6 queue drain does not match parent character** — late spawns are serviced (good) but a stale “Akame spawned by POWER” can attach to the next `Rem` roll (bad for session records). The wait path already requires `parent_character`.
- **`SphereReactor` is fire-and-forget** — HTTP click success is logged as a sphere; no wait for the `(used/max)` line. `$ohu` `N/15 buttons clicked` is persisted for the Run counter; the reactor does not skip at cap (Mudae stops spawning those buttons).
- **Resume holes** — `macro_runtime` snapshot omits perk-8 click counts; claim cooldown restore subtracts wall-clock minutes instead of using the claim-reset instant; legacy flat `daily_resets` is dropped with no migration.
- **Quit is fire-and-forget** — `shutdown()` persists and disconnects without waiting for the reader thread or an in-flight minigame.

### GUI (shells drifted)

Classic Run (`RunView` + `MacroControlBar`) and Haul/Console/Boxed (`RunModel` + `*RunPage`) are two products:

- ~~`$us` stop-on-power / stop-after-N only on Classic.~~ Drain / schedule policy on the preset (Presets → `$us`); Run page is the start button only.
- ~~Update banner only on Classic; tray text says “see the Run tab”.~~ Compact notice above every layout (`UpdateNotice` in `ShellSwitcher`); changelog + Update live on Settings. Tray points at Settings.
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
- ~~**Update banner in `Main.qml` / Settings**~~ — compact notice on all layouts; pull + restart on Settings.
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
  **Validated against 64 real logged boards:** every board has exactly 4 mines, every non-mine colour equals its adjacent-mine count (0 mismatches in 1,344 cells), every placement exists in the enumerated 12,650, and per-cell mine frequency is consistent with the uniform prior the solver assumes (χ²=16.7 vs 36.4 critical). The world model is exact — pinned by `tests/test_minigame_log_models.py`.
  **Fixed while validating:** the replay always painted the auto-revealed 4th sphere red (150 SP), but **12.5% of them are rainbow** (500 SP, 7 of 56 logged). `avg_base_sp` therefore understated real SP by ~38/game — harmless for A/B (a shared constant offset) but wrong as an absolute. `score_oq_policy` now also reports `avg_base_sp_rainbow_adjusted` (MIXED: 344.1 raw → **385.9 adjusted**, against 360.2 avg in live logs). `oq_solver` still values that cell at a flat 150 internally; correcting it to the true ~194 EV was measured **decision-neutral** (win rate identical, −0.11 SP over 2,530 worlds), so it was left alone.

- **`$oh` — medium, ~~blocked on frequencies~~ UNBLOCKED: the reveal table is now measured.** They run a Bellman DP over *counts* `(clicks left, covered, blue, teal, dark, top flats)` — position does not matter. We never click revealed blue/teal and otherwise take the highest revealed paid sphere, else a random `spU` (`macro/sphere_game.py`). That static skip is wrong with 1–2 clicks left (a teal at 20, or a blue that unveils 3 cells, can beat a face-down).
  The blocker was "log colour / value of each `$oh` reveal until the reveal table is stable". **Done** — 96 logged boards (2,317 revealed cells) reproduce the published spawn table to within ~1.7 points on every colour, and the rare tiers land almost exactly (white 0.04%, red 0.22%, purple 3.93%). The table and its `$oc`-spawn residual are in [`MUDAE_LOGIC.md`](MUDAE_LOGIC.md) and pinned by `tests/test_minigame_log_models.py`.
  **Harness shipped** (`macro/oh_replay.py`, `scripts/oh_bakeoff.py`): simulator + replay of real logged boards with paired t-stats, so a policy change can finally be scored. Replay gives 156.5 SP vs 153.4 live. The unveil mechanic is now measured, not assumed — blue→3, teal→1, targets **uniformly random not positional** (26.8% adjacent vs 24.0% by chance), which is what licenses a *counts* DP.
  **Fixed:** `$oh` ranked revealed spheres by the ordinal `SPHERE_VALUE_RANK`, which puts dark (5) below orange (7) although dark pays ~104 vs 90. Now ordered by real SP via an `$oh`-local `_OH_CLICK_VALUE` (the shared rank is untouched). Measured +0.04 SP on 94 boards, 1 board changed — strictly correct, not significant.
  **`oh_solver.py` (counts DP) is still open, but the expected payoff is small.** A prototype threshold search beats greedy by only **~1.5–2.5%**, and that margin is *flat* from 1 to 10 initial reveals — the reveal perk raises absolute score a lot (145 → 186 SP) but does not widen the solver's edge. Treat the DP as optional polish, and gate it on `--from-log` before shipping.
  **Do not price `$oc` spawns into the policy.** Clicking one grants a whole `$oc` game (~314 SP) but the cell is invisible even once unveiled, so it cannot be targeted; valued at 314 the search degenerates to "never claim a revealed sphere". `OC_GRANT_VALUE` defaults to 0 and the bakeoff prints both valuations.

- **`$oc` — done (medium), and the priors are now measured.** They weight each of the 24 reds equally, then do a 5-click Bellman DP over colour outcomes (max total SP, not “find red”). We already treat candidate reds as equally likely and still do **not** enumerate full boards — geometric filters from [mudaehelper](https://mudaehelper.pages.dev) (`macro/oc_solver.py`). **The "generator is inconsistent for some reds" caveat did not reproduce:** across 100 fully-revealed logged boards there are zero rule violations, the true red always survives the constraints, and every board is exactly 1/2/3/4 red/orange/yellow/green. The constraint layer is trustworthy; treat that caveat as retired.
  This item also asked to "fit `P(colour at cell | red)` from logged full boards", and that is now done — see the region table in [`MUDAE_LOGIC.md`](MUDAE_LOGIC.md) (ortho 63% orange / 22% green / 15% teal, EV 67.6 SP; diagonal 64/36, EV 42.4; row-col-only 68/32, EV 30.2; outside 97% blue, EV 11.0). Two surprises: **greens do sit on orthogonally adjacent cells** (so the orange/green regions genuinely overlap), and the **centre is an ordinary cell** (yellow 23%, green 16%, orange 8%) that the solver currently never clicks.
  Hunt is still 1-ply information gain + opening `(4,2)`; collect scores by true remaining need per region (`_region_click_ev`). Measured worth on real boards: **+1.25 SP/board, t = 1.41, not significant** (~200 boards needed). Their exact DP is still not obviously better than our constraints, and with the priors now measured the remaining gap is small — do not chase it without a far larger log. Do not guess the generator; replay it instead (`--from-log`).

- **`$ot` — hard, already on the daily-loop list.** Battleship on a 5×5: ships are free, 4 blue clicks, Extra Chance until 5 ship hits. They enumerate placements with a bitmask DFS, then a two-phase policy. Phase 1 (Extra Chance on) uses a **learned** scorer they do not publish. Phase 2 is simple: click every cell with `P(blue)=0`, then gamble on EV vs ending the run. Their solver is labelled BETA. **Action:** port the game loop from `$oc`/`$oq`; implement the enumerator + Phase 2 first (that is most of a perfect game). Hand-tune Phase 1 against a simulator — we will not match their policy table. Rare-ship SP is 76 / 104 / 150 / 500 (Light / Dark / Red / Rainbow), not a flat ~90.

### Calculators — new features, not solver ports

- ~~**Perk 9 click/skip DP**~~ — [p9calc](https://colblitz.com/mudae/p9calc)'s `EV = (base × (1 + double) + flat) × (1 + SP9×0.10)` and `V(spawns left, clicks left)` are implemented in `macro/perk9_threshold.py` and gate `passes_sphere_reaction` when the preset's **budget_aware** toggle is on (off = the old static `types_allowed`). Verified against Colblitz's published EV column to ±0.04 on all nine colours; their base SP for dark (104.5) and light (75.9) fill the gap in `SPHERE_BASE_SP`. Spawn rates and values are editable per colour in Presets since the sample is still being re-measured; `estimate_sphere_colour_frequency` shows our own logged mix beside them as advisory only. Against one static filter tuned for a 120-spawn day the DP is +121% at 30 spawns, +47% at 60, +6% at 120, +28% at 250 (`scripts/perk9_bakeoff.py --tuned-for 120`). A standalone “how many OP9 chars to skip teal” page is still optional.

- **`$bw` / key EV — medium, advisory only.** [bwcalc](https://colblitz.com/mudae/bwcalc): sweep `$bw` for keys/hour (wishlist / starwish / per-character). Formulas are published; **absolute** keys/hr are community guesses — the *peak* is what to trust. **Action:** a Settings/Utilities paste of `$bonus` + `$wlsz+z!` (rolls/hour + `$bw` penalty are already parsed) after the app-only wishlist. Never auto-send `$bw`.

- **Disablelist optimizer — skip for now.** [dlcalc](https://colblitz.com/mudae/dlcalc) is set-cover + pool caps. The ILP is a day; the **bundle↔character dump** is the real product and goes stale. Keep the one-click `$dl`/`$adl`/`$wl` switch. Revisit only if we ingest a refreshable dump ([MudaeDB](https://github.com/LilJamJam/MudaeDB) / [DL-Builds](https://github.com/PRCSakura/Mudae-DL-Builds)).

- **Sphere upgrade planner (`spcalc`) — skip.** [spcalc](https://colblitz.com/mudae/spcalc) is the heaviest tool (OP9/OP5/OP8/OP10/SP2/SP5/SP10 income + discounted upgrade order). `$shop` is parsed; `$mmsz=z!` is not. Users can keep using the site. If we ever want it, it is a multi-day transcription, not a macro feature.

### Skip entirely

- **YOGRTBot live solver** — a bot you invite so a browser overlay updates on message edit. We already parse the 5×5 from component rows and click. A recommend-only Discord bot is a different product (and a different ToS surface).
- **klcalc** — they unlisted it from the index (2026-08-20). Ignore.
- **Heatmaps / click-history / harvest explainer** — web-solver chrome. Our log line (`format_solver_stats`) is enough.
- **Their hosted stats tables** — games *their* bot saw, not ours.

Solver/calculator pickup order is the **Unlock path** waves 1 and 4 (and `$bw` in wave 5). Perk 9 / `$bw` can use stored `$bonus` fields; do not start them as a parser project.

Public Python references if a port stalls: [Svessinn/Mudae](https://github.com/Svessinn/Mudae) (all four games + sims), [GAP22/oq-solver](https://github.com/GAP22/oq-solver), [mudae-sphere-solver](https://github.com/ShrimpandGGrits/mudae-sphere-solver). Colblitz itself is server-side — no client JS to read.
