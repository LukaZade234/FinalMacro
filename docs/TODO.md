# TODO

Open work. Game rules: [`MUDAE_LOGIC.md`](MUDAE_LOGIC.md). Code map: [`ARCHITECTURE.md`](ARCHITECTURE.md). Unused parsed fields: [`PARSED_FIELDS.md`](PARSED_FIELDS.md).

Follow **Unlock path** unless you specifically want a quick win or a single high-impact slice. Skip list is at the bottom of **Colblitz tools**. Completed work is kept as short history — full forensic detail for anything struck through lives in git history, the referenced modules, and `MUDAE_LOGIC.md`, not here.

---

## Next up

Per **By ease**, the cheapest open item is the **`$dl`/`$adl`/`$wl` one-click switch** (GUI + send, no optimizer — still greenfield: no alias, parser, or stored list contents, and the current lists are never read back from Mudae). Per **By importance**, the two things actually worth doing are wiring *behavioural* rules off the already-parsed `$settings`/`$bonus` fields, and **full daily autonomy** (one connect covers rolls, reacts, minigames, dailies, and skips minigames already exhausted). The **auto sphere/kakera investor** is now unblocked (stock tracking shipped) and is the next real feature in Wave 5. Phase D and achievements only matter if multi-account or a leaderboard is actually wanted.

---

## By ease

Cheapest first. “Easy” means a sitting or two and little new machinery.

1. ~~**Empty states**~~ — `gui/emptyStates.js`: disconnected vs nothing recorded vs filters.
2. ~~**Compile leftover parser regexes**~~ — module-level `_…_RE` across `mudae/parsers/`.
3. ~~**Humanized delays**~~ — opt-in roll jitter on the Presets Rolls tab.
4. ~~**Reaction power max on the account page**~~ — wired from the run channel's `$bonus` (`macro/sheet_caps.py`).
5. ~~**Timezones**~~ — UTC for Mudae dailies / stats “today”; live feed stays local.
6. ~~**`$p` / `$daily`**~~ — account-global, designated channel, priority over rolls.
7. ~~**Chaos parser**~~ — `mudae/parsers/chaos.py`: extra rolls spent, free kakera/wish acted on, power discount applied, omega keys logged.
8. **`$dl` / `$adl` / `$wl` one-click** — GUI + send; no optimizer. Note the scopes differ — `$dl`/`$adl` are server rule lists, `$wl` is the account wishlist.
9. ~~**Perk 8 power save / `$us` control**~~ — perk-8 reserve in `macro/perk8_power.py`; `$us` drain/schedule on the preset. Run page is only the Roll `$us` button.
10. ~~**Sphere tracking audit**~~ — perk-9 colour on `sphere_click`, `$oc` from `$oh` not double-counted, no overlap between SP sources; Statistics “today” matches hand tally.
11. ~~**`$oc` leftover-click lookahead**~~ — remaining-need-aware EV + widened hunt threshold. +1.25 SP/board on 100 real boards, not significant; blocked on sample size, not ideas.
12. ~~**`$oh` histogram → DP**~~ (confirms the shipped heuristic) and ~~**app-only wishlist**~~ (shipped) — both done. **Auto investor** — new module, known shape, still open.
13. ~~**EventLog + JSONL**~~ then ~~**daily cube + paged stats**~~ — shared filter state across tabs and a Qt list model can wait.
14. ~~**Perk 9 threshold**~~ / ~~**`$bw` advisory**~~ — both wired (`macro/perk9_threshold.py`, `macro/bw_calc.py`).
15. ~~**`$ot` full pipeline**~~ — solver, harness, Extra Chance, and auto-play all shipped (`PLAYABLE_MINIGAMES`); the manual **Play $ot** button stays. / **use parsed `$settings`/`$bonus` in decisions** / **full daily autonomy** / **Phase D** — real projects, still open.
16. Last: split `bridge.py`, achievements, GUI polish.

---

## By importance

Highest first. What makes an overnight run correct and complete.

1. **Use parsed `$settings` / `$bonus` in decisions** — parse-and-store is done; perk 9 DP and the `$bw` sweep read those fields, but any *behavioural* rule from them still waits. Field-by-field survey of what is wired vs. sitting unused: [`PARSED_FIELDS.md`](PARSED_FIELDS.md). ~~Claim-via-emoji~~ shipped, but deliberately reads the roll's own components instead — the server and account can disagree, and only the roll shows the live combination.
2. **Full daily autonomy** — the product: one connect covers rolls, reacts, minigames, `$p`/`$daily`, and skips what is already exhausted.
3. ~~**Sphere tracking + EventLog / shared stats**~~ — daily cube + paged stats tables; totals/charts no longer walk every event in QML.
4. **Phase D (multi account / server)** — only this high if alts or a second server are why the app exists; otherwise it waits.
5. ~~**Unused or mis-spent daily budget**~~ — `$ot` Extra Chance (+168.9 SP, t=3.72, 100.2% of ceiling, 7/27 boards cleared outright) and the perk-9 adaptive threshold both shipped.
6. ~~**Reconnect / overlap holes**~~ — `mudae/macro_activity.py`'s owner **depth count** replaced the save/restore idiom, closing a stale-true bug, a reconnect window, and a real minigame/hourly-refill collision.
7. ~~**Timezones**~~ — UTC `date_key` + UTC stats buckets; live feed local.
8. ~~**Overnight completeness**~~ — chaos parser + follow-up wired end to end.
9. ~~**More SP from games we already play**~~ — `$oh` DP confirms the shipped heuristic, `$oc` lookahead measured (+1.25 SP/board, n.s.), `$oq` MIXED matches Colblitz. Nothing obvious left in this line.
10. ~~**App-only wishlist**~~ and ~~**`$bw` advisory**~~ both shipped, including the base pool — no longer a guessed input, it now comes from `$limroul`.
11. **`$dl` switch**, shell Run parity.
12. Last: achievements, split `bridge.py`, leftover regexes, GUI polish.

---

## Unlock path

Do this order. Early waves make later ones cheaper; items in the same wave can run in parallel.

**Waves 1–4 are complete.** Rolls, claims, minigames (`$oh`/`$oc`/`$oq`/`$ot`), dailies, perk 8/9 budgets, `$us`, the `$settings`/`$bonus`/`$shop`/`$limroul`/`$ov` parsers, EventLog + daily-cube stats, and the perk-9/`$bw` calculators are all shipped — see **By ease**, **By importance**, and **Found in audit** above for what each one fixed, and `MUDAE_LOGIC.md` for the mechanics themselves.

**Wave 5 — after one account is boringly reliable**

- ~~App-only wishlist → `$bw` advisory~~ — both shipped. Never auto-send `$bw`; the page prints the command.
- **Auto sphere / kakera investor** — spend stock into `$oh` / kakera invest without a manual click. Wave-3 stock tracking (its prerequisite) is done, so this is now open to start.
- **Phase D**.
- **Daily report / session row / achievements** — daily report shipped (`Statistics › Report`); session row and achievements still open.
- Split `bridge.py`, GUI polish. (Leftover regexes done.)

~~Optional / when asked: `$ov` parser~~ — shipped; also feeds the `$bw` sweep's `$persrare` N. Skip unless someone wants them: disablelist optimizer, spcalc, YOGRTBot, klcalc.

---

## Parsers and server rules

- ~~**`$settings` / `$bonus` parse audit**~~ — parsers trusted for storage (`tests/mudae_sheet_fixtures.py`, `mudae/parsers/bonus_catalog.py`); capture skips the 16 direct toggles, `$bonus` dump is read-only. **Open follow-up:** driving `CharacterClaimRules` / kakera / sphere reacts from these fields — claim-via-emoji deliberately reads the roll instead.
- ~~**`$shop` parser**~~ — ouroperk sheet (OP1–OP10, perk-9 extra clicks + SP%, megasphere rewards); `perk9_click_max` drives the daily click cap. p9calc/spcalc-style planners still wait. Do not send `$shoprefund`.
- ~~**Chaos parser**~~ — `mudae/parsers/chaos.py` + `macro/chaos_followup.py`. Extra hourly rolls are spent, not left for `$tu`/refill; free kakera and wish spawns are clicked/claimed; `$kl` and stored minigames are logged only.
- ~~**`$limroul` parser**~~ — feeds the `$bw` sweep's base pool directly and flat (the wishlist is part of the pool, not subtracted out); the page asks which roulette you roll only when the four disagree, rather than averaging.
- ~~**`$ov` parser**~~ — feeds the `$bw` sweep's `$persrare` N (a multiplier, not a reroll count); fetched only by the scope bar, never sent on its own.
- ~~**Sphere tracking audit**~~ — see Wave 1; perk-9 colour, `$oh`→`$oc` accounting, and perk-10/perk-9/kakera overlap all verified against hand tally.
- ~~**`$p` / `$daily`**~~ — account-global; one designated channel per account; sequential if several accounts have a channel set.

Do not change per-server claim / kakera / roll rules until a slice *uses* the parsed settings / bonus fields.

---

## Daily loop and scheduling

- **Full daily autonomy** — one connect covers rolls, reacts, minigames, `$p`/`$daily`, and skips minigames already exhausted until refill.
- ~~**Save power for perk 8 refresh**~~ — `macro/perk8_power.py`, horizon `min(N hours, time until UTC midnight)`, default 4h. Purple stays free.
- **Auto sphere / kakera investor** — spend stock into `$oh` / kakera invest without a manual click.
- ~~**`$ot` solver + auto-play**~~ — in `PLAYABLE_MINIGAMES`, same as `$oh`/`$oc`/`$oq`; the **Play $ot** button stays for an on-demand single play.
- ~~**`$us` control**~~ — drain / optional local schedule on the preset; session roll cap and window end are hard stops.
- ~~**Humanized delays**~~ — opt-in roll jitter.

---

## Accounts and servers

- **Multi account / server runtime (Phase D)** — config already has accounts, channels, presets, and `targets[]`. Runtime is still one Discord connection. Coordinator must resolve `(account, channel) → preset` per target (never “first preset on the account”). See Phase D in `ARCHITECTURE.md`.
- **`$dl` / `$adl` / `$wl` one-click switch** — swap those lists from the GUI without typing the commands. Not the same as Colblitz's disablelist *optimizer* (needs a bundle database we do not have).

---

## New sections (Mudae / Spheres / Advisor)

A dozen planned features shared one problem: they all read off — or advise on —
one `(account, server)` pair, and had nowhere to live. Agreed shape: **three hubs**
(Mudae / Spheres / Advisor), each a pill bar over a `Loader`, each carrying a
`ScopeBar` that starts on the Run target and can then move without disturbing a
live run.

- ~~**Account-scope the sheets**~~, ~~**fetch buttons with temporary connections**~~ (`gui/scope_fetch.py`), ~~**one `MudaeSheetPanel`**~~ — all shipped.
- ~~**Mudae hub**~~ — `$settings` (parsed sheet only; the drift/copy editor is unmounted, see `ARCHITECTURE.md`) / `$ov` / `$bonus`.
- ~~**Statistics › Report**~~ — `DailyReportView.qml`: KPI row vs a trailing 7-day baseline, 14-day trend, per-kind breakdowns, and a **daily budgets** panel (today-only and scoped-only by design, since perk-8/9 budgets are live daily state per (account, server)).
- ~~**Spheres hub**~~ — Stock & shop / Upgrades / Characters.
  - Stock and shop balance are **one pool**, confirmed by the account owner — the bridge publishes one resolved `stock.spheres` + `stock.spheres_source`; Upgrades prices affordability off the same figure so the two pages cannot disagree.
  - Upgrade cost is `(level + 1) × level_cost_step`, not a flat per-upgrade amount.
  - `macro/sphere_upgrades.py` prices perk 9 only. **Open:** wire OP1's perk-1 spawn-bonus value through the `$bw` sweep now that the `$wl` capture supplies each character's roster and bonus.
  - Invest stays blocked — no kakera balance, and the invest command's syntax/reply are undocumented.
- ~~**Advisor hub**~~ — `$bw` / Key EV / Wishlist / Lists / Formatter.
  - `$bw` is deliberately **not** converted to kakera — the log has no marginal kakera-per-roll figure, only a meaningless average (499 ka/roll on the live account). The page shows rolls lost and stops.
  - Only chaos keys are priced (power saved → extra clicks). Claim-key *count* per wish spawn is modelled via perk 4; their *value* still abstains, since perk 4 says how many keys arrive, never what one unlocks.
  - ~~`$bw` optimum~~ — unblocked by the `$wl` capture. Two findings folded into `MUDAE_LOGIC.md`: the `+N%` on a `$wl` row is the perk-1 spawn bonus (it wraps around the wishlist), and `starwish_spawn_bonus_pct` is the extra on top of wish, not the total.

---

## Statistics and GUI

- **Four stats views still copy filter chrome** — share filter state across Kakera/Spheres/Keys/Soulmates so “account: X” carries over between tabs.
- ~~Stats payload rebuilt from scratch~~, ~~`uniqueSources()` O(n²)~~, ~~`filteredEntries()` walked the full log in QML~~ — all fixed by the daily cube + `App.statsQuery` paging. A `QAbstractListModel` can still replace JSON paging later.
- ~~One EventLog + JSONL~~ — `data/events.jsonl`; old `data/*_log.json` arrays imported once, left on disk.
- ~~Timezones~~, ~~reaction power max hardcoded `155`~~, ~~empty states~~ — done.
- **Session row on Statistics** — one line per connect/disconnect with kakera + spheres + keys + claims (`gui/run_summary.py` already does a session haul on Run).
- ~~**Daily report**~~ — `Statistics › Report`, a mosaic tuned to what each metric can honestly claim: kakera colour is measured over clicks only (payouts carry no type); the perk-8 tape is a labelled approximation (nothing records which click consumed a perk-8 slot); minigame rates are per-*use*, only over days that recorded use counts; perk 8/9 refuse to generalise across accounts/servers and require the scope bar.
- **GUI polish** — leftover layout/copy/empty-page work.

---

## Later (not blocking)

- **Split `gui/bridge.py`** — ~2.7k lines, 90+ slots. Logical groups already exist (run, config, stats, mudae settings, updates). Leave `macro/roll_cycle.py` alone; it is long because the domain is.
- ~~Compile leftover parser regexes~~ — done.
- ~~**`$oq` opening move**~~ — Colblitz overlay `(1,1)`, short-circuits on a blank board. Hunt is MIXED; leave the Bellman DP.
- **Achievements** — soulmate / chaos-key / rainbow milestones. The logs are one `EventLog` now, so this is open to start.

---

## Found in audit

Pass over the running app after the rankings above.

### Bugs (all fixed)

- ~~ParseLab wrote the live token on every keystroke~~ — Debug no longer edits the token.
- ~~Hourly Start was allowed during a minigame~~ — the busy check is now re-verified on the loop thread, not just the Qt thread.
- ~~`force_reconnect` cleared `macro_active` and never restored it~~ — the gateway no longer owns the flag.
- ~~Hardcoded `lukazade234` display fallback~~ — soulmate rows get `account_name` from Mudae's `owner`.
- ~~`$us` alternated `$tu` → one roll → `$tu` mid-bonus~~ — the bonus batch now rolls first in both paths (lost 7 rolls across 8 `$tu` polls on 2026-08-30).
- ~~Mudae's 2,200 keys/h limit was invisible~~ — now parsed, shown on the feed, with an optional pause (`us_stop_on_key_limit`).
- ~~`CLAIM_INTERVAL` was parsed and then ignored~~ — `wait_for_claim` now matches it and syncs `claim_available` immediately.
- ~~Rolls without claim buttons were treated as unclaimable~~ — claim mode (button vs. react) is now read per-roll rather than from `$settings`, since the two can disagree.
- ~~A multiplied `$oh` banked only 1 of 4 `$oc` uses~~ — the reward line's own count is read now, not the line count.
- ~~Mudae maintenance replies were parsed as valid sheets~~ — recognised first (`MessageKind.MAINTENANCE`) and waited out on a 5/10/30-minute ladder.
- ~~Unknown reaction power treated as infinite~~ — **judged correct as-is**: a wrong guess self-corrects on the very next denial and costs at most one click, while guessing "no power" would wrongly skip real, affordable clicks every session.
- ~~`$oh` dark "turns into" / light "breaks down into" lines were dropped~~ — both parsed and logged now.
- ~~Roll-button dark clicks were logged as their payout colour~~ — `sphere_type` now reads the transform, not the result. **Not backfilled:** rows written before this fix still over-count red/rainbow, and the 500-sample threshold for frequency estimation has never actually been reached.
- ~~Perk-9 budget expired unspent because the static colour filter ran before the budget gate~~ — budget mode now ignores `types_allowed` entirely (greyed out in Presets to say so). One day threw away 22 live spawns with 5 clicks unspent.
- ~~…and `spawns_left` never decayed~~ — replaced the "pool minus rolled" ceiling with a per-account urn-forecast hazard rate (`$us` rolls excluded from learning); 82 → 13 clicks expired unspent across 7 replayed days.
- ~~Daily reset left `rolled_today` stale, and `$ohu8` suppressed the `$ohu9` re-query~~ — rollover now zeroes the counter; `rolled_synced_at` tracks the roll line separately from `$ohu8`'s reply timestamp. Caught live 2026-09-02 00:01 UTC.
- ~~`$bonus`/`$shop` were stored once per channel, so two accounts on one channel overwrote each other~~ — now keyed by account id; a legacy blob is read for the main account only and flagged `inferred`.
- ~~A hand-played minigame board printed itself into the feed as a claim~~ — grids are recognised first (`MessageKind.MINIGAME_BOARD`), ahead of the claim heuristic.
- ~~…and so did other Mudae prose (upgrade panels, `$kakeracopy` syntax)~~ — the real fix: a message is mirrored only when it names the connected account; edits are never mirrored; roll cards are logged by the roller directly instead.
- ~~`is_connected` stayed True forever~~ — no `on_disconnect` handler existed; now consults `on_resumed`/`client.is_closed()`, and `$ot` reconnects after a silent gateway stall.
- ~~Button clicks swallowed every error~~ — clicks now retry, refetch, reconnect, and log the reason (429/rate-limit/timeout/500 now treated as transient).
- ~~Minigames auto-played on every hourly cycle/wake instead of only at start and reset~~ — gated on a per-day flag; on-demand Run-page buttons unaffected.

### Robustness (not wrong today, fail overnight)

- **`$oc` / `$oq` have no click retry** — `$oh` resends on ack timeout; the other two abort the batch. Transport retry now covers all four; the game loops themselves still `break` on a refusal, deliberately, since every click there is paid.
- **Minigames do not wait out a maintenance window themselves** — the outage is seen, but only the roll loops act on it. Cosmetic ordering today; worth closing if maintenance ever lands mid-grid.
- **`$us` slow-path add does not use the reconnect wrapper** — a single 503 fails the add.
- **Perk-6 queue drain does not match parent character** — a stale entry can attach to the next roll.
- **`SphereReactor` is fire-and-forget** — no wait for the `(used/max)` line; `$ohu` count is persisted for the Run counter instead.
- **Resume holes** — `macro_runtime` snapshot omits perk-8 click counts; claim cooldown restore uses wall-clock minutes instead of the claim-reset instant; legacy flat `daily_resets` has no migration.
- **Quit is fire-and-forget** — `shutdown()` doesn't wait for the reader thread or an in-flight minigame.

### GUI (shells drifted)

Classic Run and Haul/Console/Boxed (`RunModel` + `*RunPage`) are two products:

- ~~`$us` stop-on-power / stop-after-N only on Classic~~ — drain/schedule policy moved to the preset.
- ~~Update banner only on Classic~~ — compact notice on every layout now; changelog/Update live on Settings.
- Session haul / last claim / perk 8·9 chips only on the new shells; Classic never reads `runSummaryJson`.
- `RunModel.dkNextMinutes` and `TargetModel.warning` are computed and not shown.
- Notification-standby banner only on Classic.
- No confirm on delete account/server/preset, live `$settings` Apply, or legacy import.
- Changing Run target while connected silently stops the macro.
- Mudae "Apply to server" channel pickers don't follow the Run target, and still hard-require the target channel to *be* the connected Run target — deliberately not fixed yet, since Apply also has no confirm/preview and a batch of live edits to an unwatched server is a worse failure than a stale sheet.
- Compact Run preset combo shows preset **ids**, not names.
- Dead: `PhaseStepper.qml`, `ServerChannelSelectors.qml`, `App.mudaeSettingsCatalogJson`, `App.macroActivityLog`.

### Ideas that fit this app

- **Shared `RunControls`** — one gating/loading implementation; Classic migrates onto `RunModel`.
- ~~Update banner in `Main.qml` / Settings~~ — done.
- **Confirm + command preview before live `$settings` Apply.**
- **Tray: notify on wish/claim** (menu is currently Show + Quit only).
- **Claim-interval hold** — on `CLAIM_INTERVAL`, set cooldown from `next_interval_minutes` instead of timing out.
- **Sphere daily-cap advisor** — parse `$ohu` button/megasphere lines; disable the sphere reactor when the roll-button cap is hit.
- **`$oc`/`$oq` retry + play-all continues after one failed batch.**
- **Stats CSV/JSON export** of the filtered rows.
- **Minigame resume checkpoint** — persist grid signature after each ack so a disconnect doesn't forfeit the `$ohu` use.
- **ParseLab sandbox token** — debug connection isolated from the Accounts store.
- **Custom claim-react emoji** — cosmetic polish, low priority.

Not bugs: `min_kakera` is labelled "instant trigger" in Presets and is *not* an end-of-batch floor — `claim_best` picking the highest remaining ka is the intended fallback.

---

## Colblitz tools vs this app

Compared [colblitz.com/mudae](https://colblitz.com/mudae/) and [`docs/archive/mudae-tools-dev-guide.md`](archive/mudae-tools-dev-guide.md) against our solvers. Their site is a browser helper + hosted Discord bot; we already auto-play `$oh`/`$oc`/`$oq`/`$ot`. Do not rebuild their website or YOGRTBot. Steal algorithms that raise our SP; skip tools that need datasets or a second UI we would never keep current.

Full section-by-section build notes: [`docs/archive/mudae-tools-dev-guide.md`](archive/mudae-tools-dev-guide.md). Index: [`docs/archive/README.md`](archive/README.md).

### Solvers — room to improve

- **`$oq`** — MIXED is live, leave it: hunt scores `α·P(purple) + β·Gini`, opening at Colblitz's `(1,1)`. Full replay over all 12,650 worlds: MIXED 95.6%/344.8 vs Colblitz's published 95.4%/342.7 (their Bellman DP: 98.1%/356.3 — not worth chasing for ~11 SP). World model validated exact against 64 real logged boards, pinned by tests. Fixed while validating: the auto-revealed 4th sphere is 12.5% rainbow, not always red (`avg_base_sp_rainbow_adjusted` reports the corrected figure); left the solver's flat internal valuation alone since correcting it was decision-neutral.
- ~~`$oh` DP~~ — done, and it **confirms** the shipped heuristic rather than beating it: a face-down click dominates a revealed blue/teal at every clicks-left level 1–10 (cross-checked by Monte Carlo and against 94 real boards — 0 boards change). Reveal table validated against 96 logged boards. Fixed one real bug: the old heuristic forfeited a click it should have taken. **Do not price `$oc` grants into the policy** — valuing the ~314 SP grant degenerates the search to "never claim a revealed sphere".
- **`$oc`** — done (medium); priors measured from 100 real fully-revealed boards (region table in `MUDAE_LOGIC.md`); the "generator is inconsistent" caveat did not reproduce and is retired. Hunt is 1-ply info-gain + `(4,2)` opening; collect scores by true remaining need per region. +1.25 SP/board (t=1.41, not significant, ~200 boards needed) — do not chase further without a much larger log.
- ~~`$ot`~~ — solver + game loop done, promoted to auto-play. We don't enumerate placements: fleet size comes from the message text, and a memoised DP counts the ~5,520 legal configurations directly (0.28s cold, ~0.002s warm). **Extra Chance is the whole game** — a blue only ends the board past the 4th-or-later blue with ≥5 ship cells clicked; below that it's free and repeatable. Two-phase policy (hunt blues while the board can't end, then harvest-and-probe with `risk = ev − λ·P(blue)`, λ=60) measures **+168.9 SP (t=3.72), 100.2% of ceiling, 7/27 real boards cleared outright**. Measured dead end: one-ply lookahead scoring a probe by what it unlocks loses in every tested setting — a stock/flow double-count, not a bug; do not re-derive. **Still open:** ~50 more real boards would pin λ properly; `OT_RARE_WEIGHTS` should be re-derived as the rare-slot sample grows past 26.

### Calculators — new features, not solver ports

- ~~Perk 9 click/skip DP~~ — `macro/perk9_threshold.py`, verified to ±0.04 SP against Colblitz's published EV column. +121%/+47%/+6%/+28% SP at 30/60/120/250 spawns vs a static filter tuned for 120.
- ~~`$bw` / key EV~~ — `macro/bw_calc.py` + Advisor pages. Tier tables confirmed against the live `$bonus`. Base pool now comes from `$limroul`, `$persrare` from `$ov` — no guessed inputs left. `$bw` is never auto-sent. Slash commands are modelled but not applied (the macro rolls with `$`).
- **Disablelist optimizer — skip for now.** The ILP is a day's work; the bundle↔character dump is the real product and goes stale. Revisit only with a refreshable dump ([MudaeDB](https://github.com/LilJamJam/MudaeDB) / [DL-Builds](https://github.com/PRCSakura/Mudae-DL-Builds)).
- **Sphere upgrade planner (spcalc) — skip.** Heaviest of their tools; `$mmsz=z!` isn't parsed. Multi-day transcription if ever wanted.

### Skip entirely

- **YOGRTBot live solver** — a different product and ToS surface; we already parse and click the 5×5 directly.
- **klcalc** — unlisted from Colblitz's own index. Ignore.
- **Heatmaps / click-history / harvest explainer** — web-solver chrome; our log line is enough.
- **Their hosted stats tables** — games *their* bot saw, not ours.

Solver/calculator pickup order is the **Unlock path** waves 1 and 4 (and `$bw` in wave 5) — done. Public Python references if a port ever stalls: [Svessinn/Mudae](https://github.com/Svessinn/Mudae), [GAP22/oq-solver](https://github.com/GAP22/oq-solver), [mudae-sphere-solver](https://github.com/ShrimpandGGrits/mudae-sphere-solver).

---

## Quiet shell (2026-09-07)

- ~~**Quiet design**~~ — `gui/shells/Quiet*.qml` + the `flatPanels` skin token, reaching every page through `components/PanelCard.qml`. Mockup: `docs/mockups/quiet-tabs.html`.
- ~~**Registering a shell touched three places and needed four**~~ — `tests/test_appearance.py` now fails if `skins.js`, `palettes.js`, `ShellSwitcher.qml`, `ui_preview.py`, and the bridge drift apart.
- ~~**`$settings` / `$bonus` shown in two places**~~ — the duplicate panels are off Servers; Mudae is the one place the sheets are read.
- **Still open on Quiet:** the Mudae `$settings` editor (drift/preset/diff/dry-run/apply) is unmounted and wants a deliberate home — it changes a live server, unlike everything else on that page. The perk-9 sphere row on the Run page hasn't been seen with live data; previews all run disconnected.

## `$rt` claim path (2026-09-07)

- ~~**Every `$rt` waited 12s for a reply Mudae never sends, then cancelled the
  claim**~~ — `$rt` is confirmed by a **tick reaction on the command message and
  nothing else** (confirmed by the account's owner). The macro waited for a
  reply message afterwards, so the wait could only ever time out, and a wished
  character plus a scarce daily reset were lost together. The reply waiter
  (`wait_for_rt_use` / `is_rt_use_parse_result`) is deleted; the tick is the
  confirmation, followed by a 1s settle (so the claim does not land in the same
  instant as the reset) and then the claim, with the existing 1/3/5s retry
  ladder behind it — a claim window is ~45s, so the up-front wait stays small
  and only a real failure pays for a longer one. A **lost tick** — the
  only remaining failure — falls through to a `$tu` check that asks whether the
  slot actually opened, rather than writing the reset off.

## Perk-8 stale count (2026-09-07)

- ~~**A wrong perk-8 count wedged the reactor for a night**~~ — `38/40` stored against Mudae's `40/40`. Fixed two ways: the hoard opens when the power bar is pinned, and `macro/perk8_recheck.py` re-sends `$ohu8` on Mudae's own last-click line, two hours without a perk-8 character, or ten minutes of pinned power.
- ~~**Run showed 21 rolls against a real pool of 83**~~ — `macroRollsMax` now goes through `account_sheet` instead of the pre-split channel blob.
- **Not diagnosed:** *why* the count drifted by two. Deliberately skipped: a plain time-based `$ohu8` re-query regardless of signal, to keep the command rare.
