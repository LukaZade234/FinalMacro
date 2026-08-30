# Mudae logic

How Mudae works, and how FinalMacro uses each mechanic. Code locations are
pointers only — the file map lives in `[ARCHITECTURE.md](ARCHITECTURE.md)`.

Source of truth for button names and ranks is `mudae/constants.py` (and
`gui/SphereAssets.qml` for artwork). If this doc and those files disagree,
trust the code.

---

## What Mudae is

Mudae is a Discord bot. Players roll character cards, claim them into a harem,
react to **kakera** (currency gems) and **spheres**, and play small minigames.
Servers set their own timers, roll counts, and button styles via `$settings`.

FinalMacro is a desktop client that connects as a **user account**, reads
Mudae's messages in one channel, and clicks buttons / sends commands according
to a preset. That violates Discord's Terms of Service. See the README
disclaimer.

The official Mudae application id is `432610292342587392` /
`432618578496954900` (`mudae.constants.MUDAE_BOT_IDS`). Commands below assume
the usual `$` prefix; servers can change it with `$prefix`.

---



## Rolls

A roll command (`$wa`, `$ha`, `$wg`, `$hg`, `$ma`, …) asks Mudae to spawn a
character embed. Short and long forms (`wa` / `waifu`, `h` / `husbando`) are
the same command. The preset stores which command to send
(`MacroConfig.roll_command`, default `wa`).

Each hour you have a limited pool of rolls (`$setrolls` on the server, often
around 10–21). `$tu` reports how many are left and when the pool resets.

**Macro:** `RollCycleEngine` sends `$tu`, then the configured roll command
until the pool is empty or a stop rule fires. Delay between rolls is at least
0.6s. If no embed arrives it retries, then reconnects.

---



## `$tu` — the status snapshot

`$tu` is the account's current state on that server. The parser in
`mudae/parsers/tu.py` pulls:


| Field                      | Meaning                                                                |
| -------------------------- | ---------------------------------------------------------------------- |
| Claim available / cooldown | Whether you can marry right now                                        |
| Next claim reset           | Minutes until the claim slot refills                                   |
| Rolls left                 | Hourly pool, plus optional `+$us` / `+$mk` bonus                       |
| Next rolls reset           | Minutes until the hourly pool refills                                  |
| Reaction power %           | Kakera click budget                                                    |
| `$rt` ready / next         | Extra claim token                                                      |
| `$dk` stock / next         | Daily kakera power top-up                                              |
| `$daily` reset             | Minutes until the account-global `$daily` (not the hourly rolls reset) |
| Perk 8 refill              | When daily perk-8 clicks come back                                     |


**Macro:** almost every session starts with `$tu`. Claim timing, `$us`
stacking, `$dk`, and reaction-power estimates all come from this message.
Between rolls the engine tracks power locally instead of polling `$tu` every
time (`macro/reaction_power.py`).

---



## Claims

Claiming a character uses the claim **button** on the roll embed (💍 / 💖 /
similar). Some servers hide buttons and require an emoji reaction instead.
The macro only supports **button claims**. Claim-via-emoji (`$togglebutton` off /
`$claimreact`) stays unimplemented until a later slice *uses* parsed `$settings`.

You get one claim slot per claim interval (`$setclaim`, often 60–180 minutes).
`$rt` (reset claim) is a separate token that grants an extra claim; it has
its own long cooldown.

**Final hour:** the last roll session of the current claim window — when
`$tu`'s claim-reset minutes **equal** the rolls-reset minutes. Example: 3h
claims and 1h rolls → final hour is the hour where both timers show 60.
Implemented in `macro/claim_window.py`.

**Macro claim rules** (`CharacterClaimRules` / `passes_character_claim`):

1. Wish ping + claim button → claim **immediately** (interrupt the roll loop).
  If the slot is on cooldown and `$rt` is available and `auto_use_rt` is on,
   spend `$rt` and claim.
2. Kakera value ≥ `min_kakera`, or claim rank ≤ `max_claim_rank` → claim
  immediately.
3. Otherwise, if `only_final_hour` is on and this is not the final hour →
  skip (save the slot).
4. Eligible leftovers are compared at the **end of the batch**; the best one
  is claimed then.

Already-claimed characters and embeds with no enabled claim button are
skipped.

---



## Kakera

Kakera are gem buttons on a roll. Clicking one pays currency and costs
**reaction power**, except purple.


| Emoji name | Color   | Notes                                            |
| ---------- | ------- | ------------------------------------------------ |
| `kakeraP`  | Purple  | **Free** — no power cost. Always worth clicking. |
| `kakera`   | Blue    | Default cheap kakera                             |
| `kakeraT`  | Teal    |                                                  |
| `kakeraG`  | Green   |                                                  |
| `kakeraY`  | Yellow  |                                                  |
| `kakeraO`  | Orange  |                                                  |
| `kakeraR`  | Red     |                                                  |
| `kakeraW`  | Rainbow | Highest single-color value                       |
| `kakeraL`  | Light   | Splits into several smaller kakera               |
| `kakeraD`  | Dark    |                                                  |
| `kakeraC`  | Chaos   | Highest tier the macro tracks                    |


Typical published value bands (purple/blue/…/rainbow) match older Mudae
guides. Dark and chaos were added later; treat `mudae/constants.py` as
authoritative for **names**, not for exact kakera amounts (those vary with
server bonuses).

**Reaction power:** seeded from `$tu` / `$ku`. Base click cost comes from the
**run channel's** `$bonus.power_cost_per_kakera_button` (fallback **30%**).
Switching account or server reloads that channel's sheet so costs never mix.
A **chaos key** on the character halves the cost; **perk 8** halves it
again. Power regenerates 1% every 3 minutes. `$dk` snaps the bar to
`$bonus.kakera_max_power` (fallback **155**). Most players have a **20h**
`$dk` cooldown (`$bonus.dk_cooldown`; 10h only if the sheet says so).

### Kakera reaction rules

Source of truth for *what should be clicked*: this subsection, then
`macro/rule_eval.py` (decision) and `macro/kakera_reactor.py` (clicks).
Preset fields live on `KakeraReactionRules`.

**Order on each roll:**

1. Kakera reaction enabled, and at least one enabled kakera button.
2. Optional `require_perk_8` (lifted after 40/40 or insufficient roll pool).
3. Optional min-spheres.
4. **Colour list:** perk-8 characters use `perk_8_types_allowed` whenever
  budget mode is on (empty = any colour). Everyone else uses
   `types_allowed` (or the `$us` override list on `$us` rolls).
5. Low-power override, if enabled and bar is below the threshold — this
  **replaces** the colour list, including on perk-8 characters.
6. Chaos-key gate: without a chaos key, only `require_chaos_key_bypass_types`
  (default purple) may click.
7. Affordability (bar vs cost). Mudae's "can't react for N min" still wins
  if the tracker is wrong.
8. **Saving window** (`perk8_is_saving`): only when **Prioritize perk-8**
  is on (`perk_8_priority`, default on), mode is `active`, and local count
   is under the `$ohu8` cap. Non-perk-8 rolls keep only **bypass** colours
   (`perk_8_budget_bypass_types`, default purple). Perk-8 rolls keep the
   perk-8 list. With priority **off**, perk-8 characters still use the
   perk-8 colours, but other rolls use the main filter as they appear.
9. Optional smart power / `$dk` reserve on paid *non*-perk-8 clicks.
10. Remaining-quota slice: at most N clicks that **count toward the 40**.
  Purple never counts. Bypass colours on a **non**-perk-8 roll do not
    count (they still cost power, except purple). Bypass colours on a
    **perk-8** roll **do** count — they are normal perk-8 kakera.

**Daily 40 (**`$ohu8`**):** only perk-8-character paid clicks use the quota.
Red/rainbow on a perk-8 character count because they are on the perk-8
list. The same colours on a normal character are bypass: still clicked
while saving, not counted. After 40/40, non-perk-8 rolls use the main
colour list (equal clicking); perk-8 characters **keep** the perk-8 list
(orange/dark stay allowed).

`$ohu8` **timing:** sent at session start and when the daily refill is due.
Saving is off (`inactive`) until that reply sets `active` / `done`. That
is intentional — the first `$ohu8` of the day is what starts the holdback.
A live `$ohu8` count **overwrites** a stale Run-tab 40/40 (persist from a
spent day or a false catch-up). The local counter is kept only when it is
1–2 clicks ahead of Mudae (a click that has not landed in the `$ohu8`
text yet). After **any wait timeout on a perk-8 click** (first attempt or
retry, success or fail), send `$ohu8` again so a landed-but-unseen click
cannot desync the 40. Non-perk-8 timeouts do not.

`$us`**:** optional narrower `types_allowed` for non-perk-8 `$us` rolls.
Perk-8 characters still use the Reactions perk-8 list. "Don't claim kakera
on `$us` rolls" disables **all** kakera on those rolls, including perk-8.

Implemented in `macro/rule_eval.py` and `macro/kakera_reactor.py`. Caps from
`$bonus` / `$shop` are applied per run channel in `macro/sheet_caps.py`.

**Chaos kakera (**`kakeraC`**) extras:** the `+$k` body can add `+N rolls this hour` (spend them now; they die at the hourly reset), store `$oh`/`$oc`/`$oq`/`$ot`
(logged, not played), spawn `$kl` (logged), grant `N% kakera power discount`
(applied when subtracting tracked power after the click), `+N` omega keys
(`$ok`, key log source `chaos`), spawn an owned character with free kakera
buttons (click all, cost 0), or spawn a wish (claim with wish-ping rules,
`$rt` if `auto_use_rt` is on). `(Shop 5) +1 $ot stored!` can appear on any
kakera react and is not a chaos minigame. Raw windows still go to
`data/chaos_log.json`.

---



## Spheres and `$oh`

Spheres are a second currency / minigame track. They show up in two places:

1. **Roll react buttons** — a sphere on the character embed (perk 9).
2. `$oh` **minigame** — a 5×5 grid of sphere buttons.

Button emoji names are `sp` + a color letter:


| Emoji | Meaning                                                                                                                |
| ----- | ---------------------------------------------------------------------------------------------------------------------- |
| `spM` | Megasphere — free bonus on a **roll** (always click; splits like light kakera)                                         |
| `spP` | Purple — **free** `$oh` **click** (does not use the daily click allowance)                                             |
| `spB` | Blue — lowest paid; skipped in `$oh` (click a face-down instead)                                                       |
| `spT` | Teal — same as blue in `$oh`                                                                                           |
| `spG` | Green                                                                                                                  |
| `spY` | Yellow                                                                                                                 |
| `spD` | Dark — paid click; may resolve to purple in the reward tracker                                                         |
| `spL` | Light                                                                                                                  |
| `spO` | Orange                                                                                                                 |
| `spR` | Red                                                                                                                    |
| `sp`  | **Red.** Mudae's default sphere emoji when "recognizable sphere buttons" is off. A roll button labelled `:sp:` is red. |
| `spW` | Rainbow — highest paid                                                                                                 |
| `spU` | Hidden / face-down in `$oh`                                                                                            |


**Colour-blind variants:** some servers (or `$settings`) use a second emoji
set with a small letter in the corner. Discord names them with a trailing
digit: `spB2` is still **blue**, `spT2` is still **teal**. The same suffix
can appear on other colours. `canonical_sphere_emoji` /
`normalize_sphere_emoji` strip it, so spawn-rate tables, perk-9 filters,
`$oh` skip-blue/teal, `$oc`/`$oq` solvers, and the sphere-click parser all
treat `spB2` as `spB`. Never log `spB2` as its own colour.

There is no chaos sphere. Rank order for paid `$oh` clicks (low → high):
blue, teal, green, yellow, dark, light, orange, red, rainbow
(`SPHERE_VALUE_RANK`).

`$oh` **strategy** (`macro/sphere_game.py`):

- Always take free purple.
- Never click an already-revealed blue or teal.
- Otherwise click the highest-value revealed paid sphere.
- If nothing good is showing, click a random face-down (`spU`).
- The grid is **one message that Mudae edits** after every click — wait for
the edit before the next move.

**Macro on rolls:** `SphereReactionRules` + `SphereReactor` click matching
sphere buttons on the character embed. A filter that includes `spR` also
matches bare `:sp:`.

Artwork: `gui/assets/kakera/Sp*.webp`, labels in `gui/SphereAssets.qml`.
Bare `sp` uses the red (`SpR`) image.

---



## Keys and soulmates

Characters can show **keys** (including a chaos key). Ten chaos keys on one
character is a soulmate. Keys are parsed off the roll embed and stored in
`mudae/key_log.py` / `mudae/soulmate_log.py`.

Chaos keys do **not** change sphere clicks. They only cheapen kakera
reactions (half power cost).

---



## `$us` — stacked extra rolls

`$us` adds rolls from a stack. They are usable immediately and **wiped on
the next rolls reset**. `$tu` shows them as `(+$N $us)`.

Mudae caps each `$us N` add at 20. Sending another `$us N` too fast is
ignored, so the macro waits for a tick reaction (or `$tu`) before adding
more. It also refuses to add near the hourly reset (`us_reset_margin_minutes`,
default 2) so a reset does not throw the stack away.

**Macro:** a separate `$us` mode in `RollCycleEngine` that reads the stack,
adds batches, then rolls them down. Kakera on `$us` rolls can follow the
normal rules or a narrower override (`UsRollKakeraRules`). Drain policy lives
on the preset (Presets → `$us`), not the Run page:

- **Keep draining** pauses on the hourly reset (and on power *if* that stop
is on) instead of quitting.
- **Stop on power** is optional; `$dk` and perk-8 “held for tomorrow” count.
- **Session roll cap** (e.g. 1000) is a hard stop.
- **Local schedule** (`us_schedule_`*) is this computer’s clock, not UTC.
While connected it drains `$us` on its own, like `$p` / `$daily`. Roll `$us`
on the Run page always starts immediately and ignores the window. Auto
drain uses the session cap and other preset stops; leftover `$us` stays on
the stack when the end time hits. If hourly is waiting for a refill, the
schedule pauses it, drains `$us`, then resumes hourly.

---



## Minigames

`$ohu` reports daily uses left / stored for `$oh`, `$oc`, `$oq`, `$ot`.
**Play all minigames** queries `$ohu`, then spends `$oh` / `$oc` / `$oq`.
`$ot` has its own **Play $ot** button but is left out of play-all and of
the after-refill auto-play on purpose (see the `$ot` section below). Extra `$oq` / `$ot` from perk 10 on
the first `$oh` of the day are counted (play-all spends the extra `$oq`).
Playing a game with no uses left gets
`You don't have enough $oh for today. Time to wait before the refill: 3h 08 min.`
(`$oc` / `$oq` / `$ot` in place of `$oh`); the activity log reports
out of minigames instead of a grid timeout.

Each finished `$oh` / `$oc` / `$oq` / `$ot` writes one row to `data/minigame_log.json`
(Statistics → Minigames): the 5×5 after the final reveal, clicks in order,
whether we hit red/rainbow, and **base SP** from `SPHERE_BASE_SP` — not the
chat `+N`, which includes bonuses. `$oq` hunt uses MIXED (`P(purple)+0.1×Gini`).

### `$oh` — sphere spawn rates

Per-cell spawn chance on an `$oh` grid, from Colblitz and **confirmed against
96 logged boards** (2,317 revealed cells). "Logged" is each colour's share of
all 25 cells:


| Colour          | Base SP | Published | Logged | On click                        |
| --------------- | ------- | --------- | ------ | ------------------------------- |
| Rainbow (`spW`) | 500     | 0.04%     | 0.04%  | extremely rare                  |
| Red (`spR`)     | 150     | 0.22%     | 0.21%  |                                 |
| Dark (`spD`)    | ~104    | 1.46%     | 1.17%  | transforms into a random sphere |
| Orange (`spO`)  | 90      | 0.97%     | 0.88%  |                                 |
| Light (`spL`)   | ~76     | 2.96%     | 3.12%  | breaks into component spheres   |
| Yellow (`spY`)  | 55      | 2.57%     | 2.79%  |                                 |
| Green (`spG`)   | 35      | 7.88%     | 7.21%  |                                 |
| Teal (`spT`)    | 20      | 23.48%    | 21.83% | reveals 1 covered cell          |
| Blue (`spB`)    | 10      | 54.49%    | 55.38% | reveals 3 covered cells         |
| Purple (`spP`)  | 5       | 3.93%     | 3.92%  | **free** — always click first   |


The table sums to **98%**. The missing **2% is an** `$oc` **spawn**: it is
indistinguishable from an unclicked cell, so it can only be hit by luck and
stays `spU` on the logged board. That is confirmed — across 94 completed
games the leftover unrevealed cells run at **2.13% per cell**, matching the
2.00% residual. Both the rates and this residual are pinned by
`tests/test_minigame_log_models.py`.

**Reveal mechanic.** Clicking a blue exposes **3** more covered cells and a
teal exposes **1**, and the targets are **uniformly random, not adjacent**
(586 logged unveil events: 26.8% land next to the clicked cell against
24.0% expected by chance). Position therefore does not matter, which is
what licenses a counts-based DP rather than a positional one. The greedy
never clicks an already-revealed blue or teal, so it only ever triggers this
via a face-down that turns out to be one.

**`$oh` play is still greedy** (`macro/sphere_game.py:choose_oh_click`):
take any revealed purple free, else the highest-**paying** revealed sphere,
never blue/teal, else a random face-down. Ordering is by real SP
(`_OH_CLICK_VALUE`), not the ordinal `SPHERE_VALUE_RANK` — that rank puts
dark below orange, but dark pays ~104 against orange's 90.
`SPHERE_VALUE_RANK` is shared with `$oc`/`$oq` and is left alone.

There is no `$oh` *solver* yet, but there is now a simulator and replay
harness (`macro/oh_replay.py`, `scripts/oh_bakeoff.py --from-log`) so any
future policy can be scored. Replaying the 94 recoverable logged boards
gives 156.5 SP against 153.4 in live play. Two cautions baked into it:

* **The replay is stochastic** — unveil targets are random, so every board
  is averaged over several seeds.
* **An `$oc` spawn is invisible.** It renders as `spU` even after being
  unveiled, so it never leaves the face-down pool and cannot be targeted.
  Clicking one grants a whole extra `$oc` game (~314 SP), but the harness
  values it at **0 by default**: priced at 314, a policy search will happily
  stop claiming known spheres to farm a random drop it cannot actually aim
  at. The bakeoff prints both valuations so no conclusion rests on it.

**Headroom.** A prototype policy search over clicks-left thresholds beats
the greedy by only **~1.5–2.5%**, and that margin is flat from 1 to 10
initial reveals — buying the initial-reveal perk raises the score a lot
(145 → 186 SP) but does not widen the gap a solver could exploit.

### `$oq` — the world model, validated

The 12,650 enumerated purple placements (`macro/oq_worlds.py`) were checked
against 64 logged boards: every board has exactly 4 mines, every non-mine
cell's colour equals its adjacent-mine count (0 mismatches in 1,344 cells),
every real placement appears in the enumeration, and per-cell mine frequency
is consistent with the uniform prior the solver assumes (χ² = 16.7, critical
36.4). The model is exact.

One caveat on its *scoring*: once 3 purples are found Mudae auto-reveals the
4th, and **12.5% of the time it is a rainbow (500 SP), not a red (150 SP)** —
7 of 56 logged auto-reveals. The world model cannot tell which, so the replay
paints it red and `avg_base_sp` understates real SP by ~38/game. Use
`avg_base_sp` to compare two policies (the offset is shared) and
`avg_base_sp_rainbow_adjusted` to compare against live play.

### `$oc` — the geometric model, measured

`$oc` (`macro/oc_solver.py`) hunts red by geometric compatibility and never
enumerates full boards. **On 100 fully-revealed logged boards the geometric
rules hold exactly**: zero violations, the true red always survives
`constraint_red_candidates`, and every board is exactly 1 red / 2 orange /
3 yellow / 4 green with red never at the centre. The long-standing caveat
that the published generator "disagrees with Mudae for some red positions"
did not reproduce — the constraint layer can be trusted.

What is *not* determined by the rules is which eligible cell gets which
colour. Measured over those 100 boards:


| Region (relative to red) | Colour mix                            | True EV |
| ------------------------ | ------------------------------------- | ------- |
| orthogonally adjacent    | orange 63%, **green 22%**, teal 15%   | 67.6 SP |
| on the diagonal          | yellow 64%, teal 36%                  | 42.4 SP |
| same row/column only     | green 68%, teal 32%                   | 30.2 SP |
| everything else          | blue 97%, (centre yellow) 2%, teal 1% | 11.0 SP |


Two things fall out of this. **Greens do sit on orthogonally adjacent
cells** (22%), so the orange and green regions genuinely overlap — a cell
next to red may be orange, green or teal. And the **centre** is an ordinary
cell: yellow 23%, green 16%, orange 8%. It is only special in that red is
never there.

Once red is known the solver spends leftover clicks by
**remaining-need-aware** EV rather than a fixed orange→yellow→green
priority: a region already fully found (e.g. both oranges) stops looking
like it might still pay off. With `clicks_left <= 3` hunting also widens
its "guess red directly" threshold from `≤2` candidates to `clicks_left`,
since brute-forcing that many candidates is guaranteed to land on red
before the budget runs out.

**Honest scale:** replaying the 100 logged boards, this is worth
**+1.25 SP/board (335.80 vs 334.55), t = 1.41 — not significant**, and it
changes the play on only 2 boards in 100. Confirming an effect that small
needs ~200 boards. Score it with
`scripts/oc_bakeoff.py --from-log docs/minigames_to_use.jsonl`, which
replays real boards and reports paired deltas with a t-statistic; the
default synthetic mode is calibrated against the table above but is still
a model, so confirm anything important against the log.

### `$ot` — battleship, and why the fleet is known up front

The grid message states the whole rule set, including the fleet size:

```
You can click 4 times on the buttons below (2 minutes).
All colors are free (they don't consume clicks) except for the blue spheres
Identical colors follow one another on the same row or column. For example,
there is a line or a column having ALL the green spheres following one another.
Spheres to find: teal = 4, green = 3, yellow = 3, rarer spheres = 2.

Number of different colors: 6
```

Ships are straight contiguous runs and may touch. Teal (4), green (3) and
yellow (3) are always present; **`Number of different colors: N` means
`N − 4` length-2 ships** — always orange, plus `N − 5` rares drawn from
light / dark / red / rainbow. Which rares is not stated, only how many.
Every cell pays its usual `SPHERE_BASE_SP`, blue included at 10 SP; light
and dark use their measured means (76 / 104), as in `$oh`.

| `N` | 2-ships | ship cells | blue cells | fleet placements |
| --- | ------- | ---------- | ---------- | ---------------- |
| 6   | 2       | 14         | 11         | 597,408          |
| 7   | 3       | 16         | 9          | 1,890,960        |
| 8   | 4       | 18         | 7          | 3,082,032        |
| 9   | 5       | 20         | 5          | 2,485,616        |

**Only blue costs a click**, and the budget is 4. `macro/ot_solver.py`
assumes the game ends on the 4th blue regardless of ship hits. Mudae's
"Extra Chance" reportedly suspends that below 5 ship hits, but neither
logged game ever reached 4 blues while under 5 hits, so nothing we have
confirms it — `EXTRA_CHANCE` is the switch, and flipping it is a rules
change that needs a real board first.

Under that reading ship hits never matter, so **clicking any cell with
`P(blue) = 0` is strictly dominant** — free SP, free information, no risk.
The only real decision is which cell to probe when nothing is certain.

The solver does not enumerate those millions of placements. A configuration
is a (teal, green, yellow) triple — there are only **5,520** legal ones —
plus a set of disjoint dominoes on what is left, and the dominoes are
*counted* by a memoised DP rather than listed. Per-cell marginals come from
one identity: the configurations that leave cell `c` empty are exactly the
packings of the free region **without** `c`. Exact, and 0.28s from a cold
cache falling to ~0.002s once three cells are known.

Because ship hits never matter under that rule, **clicking any `P(blue) = 0`
cell is strictly dominant**, and that harvest is most of a good game. The one
real decision is the probe when nothing is certain: `ev(c) − 60·P(blue at c)`.
Probing by plain EV is the intuitive rule and measurably the worst of that
family — see `docs/TODO.md` for the sweep, including why the penalty is tuned
to the low end and why a one-ply lookahead was measured and rejected.

Validated against real boards in `tests/test_minigame_log_models.py`: every
logged board is straight-line, matches its declared colour count, and is
reachable by the enumerator; blue clicks all cost budget and ship clicks
never do; finished games end on the 4th blue.

Score policies with `scripts/ot_bakeoff.py` (`--known`, `--from-log`,
`--trials`, `--sweep-risk`). Replaying the two hand-played boards gives
**826 SP against the 597.5 scored by hand**.

**`$ot` is manual only.** The Run page has a **Play $ot** button
(`macro/ot_game.py`), but `$ot` is deliberately *not* in
`PLAYABLE_MINIGAMES`, so **play-all skips it and it never starts itself
after the daily refill** — unlike `$oh` / `$oc` / `$oq`. That is on purpose
while the solver is being tried against real boards.


| Command | What it is                 | Engine                 |
| ------- | -------------------------- | ---------------------- |
| `$oh`   | 5×5 sphere grid            | `macro/sphere_game.py` |
| `$oc`   | Color-matching sphere game | `macro/oc_game.py`     |
| `$oq`   | World / path sphere game   | `macro/oq_game.py`     |
| `$ot`   | 5×5 battleship             | `macro/ot_solver.py` (solver only — not played live) |


---



## Perk 8 (daily kakera budget)

Perk 8 marks some characters and grants a **daily kakera-click budget**
(40 clicks, `$ohu8`). The flag is consumed after the first roll of the day,
so leftover clicks expire at **UTC midnight**. The macro can enter **budget
mode**: spend those clicks on perk-8 characters first (**Prioritize perk-8**,
`perk_8_priority`, default on). Bypass colours (default purple; often also
red/rainbow) still click on everyone else without using the 40; on a perk-8
character they **do** use a slot. Purple is free power on every roll. Once
the 40 are used or the roll pool is under 10, treat non-perk-8 characters
equally with the main colour list; perk-8 characters keep the perk-8 colour
list. With priority **off**, perk-8 colours still apply but other rolls are
not skipped. Full click-order rules:
[Kakera reaction rules](#kakera-reaction-rules).

**Power /** `$dk` **reserve** (`macro/perk8_power.py`) is optional on the perk-8
budget panel. Off keeps the old click and `$dk` rules. On keeps enough bar

- `$dk` that a full perk-8 dump is still payable in the first N hours
**after UTC midnight** (the daily reset; default 4h). Unused perk-8 clicks
expire at midnight, so they always get power and `$dk` first — that is not
a separate setting. After 40/40, chaos kakera still click unless *this*
spend would make the next day's post-reset burst fail; `$dk` on those
reacts only if a new use is in hand by midnight (typical cooldown **20h**).
Purple stays free. Costs assume a chaos key (7.5% perk-8, 15% normal).
N hours is a capacity floor, not a cutoff — slow perk-8 keeps rolling
until 40/40 or reset. The Run page shows the live saver state while the
toggle is on.

**The local click count is a stand-in, and Mudae is the authority.** Between
`$ohu8` queries the macro counts its own paid clicks
(`counts_toward_perk8_budget`), which drifts whenever a click's outcome is
uncertain — the click can land even though the wait times out — or whenever a
click happens outside that accounting, as chaos **free kakera** do. Both cases
force a live `$ohu8` resync rather than a guess. (The uncertain-click resync
was briefly narrowed to perk-8 characters only, which showed up as the Run page
reading 39/40 against Mudae's 40/40 for a whole day.)

State is persisted on the **channel profile** (`daily_resets.perk8`) so a
restart does not re-query until refill. Minigame uses (`daily_resets.minigames`)
skip `$ohu` / play-all until refill. Perk 9 click counts (`daily_resets.perk9`)
are restored for the Run tab; sphere reacts do not skip at the cap — Mudae
stops spawning those buttons.

---



## Perk 9 (daily sphere-button budget)

Perk 9 adds **sphere react buttons** on characters you have rolled today.
Each click consumes one slot from a daily budget (shown on `$ohu9` as
`6/20 buttons clicked` in the shared minigame header). The macro tracks
this as **clicks used / cap** on the Run page. The cap is
`10 + perk9_extra_clicks` from the run channel's `$shop` (fallback **20**).

- Query with `$ohu9` — same layout as `$ohu8` / `$ohu`: minigame
counts, refill timer, `buttons clicked`, megasphere stock line, then
`(Perk 9) Rolled today: 44/154` and the list of characters rolled.
- Sphere buttons on those characters are **perk 9 spawns**; after the budget
is used, no more spawn until the daily refill (same window as `$oh` /
sphere stock).
- **Megasphere** (`spM`) on a roll is a free bonus, not a perk 9 click —
the Run counter ignores it.
- The macro increments by one on each confirmed **sphere button click**
(`MessageKind.SPHERE_CLICK`, excluding `spM`). `SphereReactionRules.types_allowed`
still governs which colours to click. After the daily budget is used, Mudae
stops spawning the buttons — the reactor does not add its own skip.



### Adaptive threshold (`perk_9` budget mode)

`SphereReactionRules.budget_aware` (Presets → Sphere reaction, default
**off**) replaces the static colour list with an expected-value decision, so
the same preset is right on a light day and a heavy one. Implemented in
`macro/perk9_threshold.py`; `macro/rule_eval.py` only reads a prebuilt
context, `macro/sphere_reactor.py` builds one per roll.

```
EV(colour) = (base_sp × (1 + double_chance) + additional_spheres) × (1 + shop9)
V(0,c) = V(r,0) = 0
V(r,c) = Σ freq(colour) × max( EV(colour) + V(r-1,c-1),  V(r-1,c) )
click   iff  EV(colour) ≥ V(r-1,c) − V(r-1,c-1)
```

`r` is **perk-9 spawns still expected today**, `c` is clicks left in the
daily cap. `double_chance` / `additional_spheres` come from `$bonus`
(`sphere_double_chance_pct`, `additional_spheres`), `shop9` from `$shop`
(`perk9_sphere_value_pct`) — all via `macro/sheet_caps.py`. The bar falls as
spawns run out and reaches **0** once `r ≤ c`: unused clicks expire at the
UTC reset, so the last ones are worth spending on anything. Megasphere skips
the gate (free, spends no slot). Budget mode only ever **narrows**
`types_allowed`, never widens it.

Base SP and spawn rates default to Colblitz's published p9calc table
(138,925 observed rolls) and are **editable per colour in the preset**
because the sample is still being re-measured locally:


|         | `spB` | `spT` | `spG` | `spY` | `spL` | `spO` | `spD` | `spR` | `spW` |
| ------- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| Base SP | 10    | 20    | 35    | 55    | 75.9  | 90    | 104.5 | 150   | 500   |
| Spawn % | 59.58 | 24.10 | 7.88  | 2.67  | 2.98  | 0.99  | 1.45  | 0.31  | 0.04  |


Dark and light have no entry in `SPHERE_BASE_SP` (dark resolves into another
colour, light splits into fragments); the figures above are measured
averages, which is why dark outranks orange here even though
`SPHERE_VALUE_RANK` — which orders `$oh` clicks, not EV — does not.
Frequencies are conditional on a button appearing, so they total 100% and one
unit of `r` is one spawn, not one roll. A preset stores only the colours the
user edited; the rest stay at these defaults. Set a colour to 0 to drop it.

Remaining spawns come from `$ohu9`'s `(Perk 9) Rolled today: 44/154`
(`parse_perk9_rolled_pool`; `pool − rolled` is a hard ceiling), clamped by
rolls left before the UTC reset, and overridden by
`expected_daily_opportunities` when set. Without any of those signals the
context is `None` and the static filter applies.

### `$ohu9` timing (`macro/perk9_runtime.py`)

Same shape as perk-8's `$ohu8` runtime — it is **not** sent every roll
session. `Perk9Runtime` sends it:

- once at session start (and on a refresh deferred while the gateway was down),
- when the refill deadline has passed or the record is from an earlier UTC day,
- after a sphere click whose `SPHERE_CLICK` confirmation timed out — the click
may have landed, so the count could be short,
- once when the local count first reaches the cap, to confirm before standing
down until the refill.

Between those, counts are tracked locally: every paid sphere button on a roll
is one spawn (`record_perk9_spawn`), every confirmed click bumps the used count
and appends its colour (`record_perk9_click_emoji`). A reply re-syncs both —
clicks via `merge_click_count` (catch up when Mudae is ahead, tolerate a 1–2
click lag, rewind a stale local count) and spawns via `merge_spawn_count`
(Mudae's `Rolled today` keeps rising after the budget is spent because it counts
rolled characters, not spawned buttons, so the larger number wins).

`$ohu` / `$ohu8` / `$ohu9` share the availability header, so the wait keys on
the `(Perk 9)` line (`is_ohu9_response`) — otherwise an `$ohu8` reply would
satisfy an `$ohu9` wait. The reply parses through `parse_ohu`.

Every Run page shows the live state under Smart saver, fed by
`adaptive_status`: Classic via `Perk9AdaptiveStatus.qml`, and Haul / Console /
Boxed via `RunModel.perk9Adaptive*` in each shell's own idiom, with the sphere
rows shared through `Perk9SphereRow.qml`. It shows clicks used/cap, spawns seen and `Rolled today`,
spawns left, the current EV bar and which colours clear it, when the set opens
up (fewer spawns left) or tightens (fewer clicks left), and the click history
newest-first. Clicks Mudae counted that this session never saw — connecting
mid-day, or a missed confirmation — render as face-down `spU` rather than
implying the history is complete.

Score it with `scripts/perk9_bakeoff.py` (`--tuned-for N` compares against a
single static filter picked for one volume).

---



## Perk 10 (invested spheres)

Perk 10 pays on the **first** `$oh` **of the UTC day**. The grid message can
include a line like:

```
+2 $oq, +1 $ot and +5,600 :sp: from your invested spheres!
```

Older lines omit `$ot`: `+2 $oq and +5,344 :sp: from your invested spheres!`

- **Flat SP** is logged as sphere source `perk10` (Statistics → Spheres),
not as `$oh` minigame earnings.
- Extra `$oq` **/** `$ot` **uses** are stored on that `$oh` session
(`oq_bonus` / `ot_bonus`). Statistics → Minigames → `$oh` shows the
totals. Play-all spends the extra `$oq` (like bonus `$oc` from hidden
clicks). Extra `$ot` is counted in `$ohu` availability but play-all never
spends it — `$ot` is the **Play $ot** button only.

---



## `$settings` and `$bonus`

`$settings` is the server's **rule sheet**: prefix, claim/roll timers, sniping,
whether claim/kakera/sphere buttons are “recognizable”, game mode, etc. Each
bullet is `label: value ($command)`. Sending `$command` (with args, or
sometimes bare) changes the live server.

`$bonus` is a **description sheet**, not a list of commands to send. Lines
say *where a bonus comes from* (`$kt`, `$kl`, `$op`, `$shop`, premium,
spheres clicked). Those suffixes are source tags. Sending them does not
edit the sheet.

The GUI fetches `$settings`, `$bonus`, and `$shop` onto a channel profile
(`App.fetchSettings` / `fetchBonus` / `fetchShop`). Parsers:
`mudae/parsers/settings.py`, `bonus.py`, `shop.py` (catalog in
`bonus_catalog.py` / `shop_catalog.py`). Frozen dumps:
`tests/mudae_sheet_fixtures.py`.

**Storage is trusted. Most decisions are not yet.** Field-by-field parse tests
cover every `SETTINGS_FIELD_KEYS` value, the `$bonus` meaning keys
(including part 2: power cap, twice-sphere chance, rolls/hour), and `$shop`
OP1–OP10 (perk 9 extra clicks + SP%). Claim / kakera / roll behaviour still
does not read those fields.
`RollCycleEngine.apply_settings_fields` still only copies `settimer`.
Reaction-power max (`kakera_max_power`) and the perk 9 click cap
(`perk9_click_max`) **are** applied from the run channel's stored sheets.

### `$bonus` meaning keys needed later


| Key                            | Type | Typical source tag       | Later use                                         |
| ------------------------------ | ---- | ------------------------ | ------------------------------------------------- |
| `kakera_max_power`             | int  | `$kt`                    | Reaction-power cap (wired)                        |
| `power_cost_per_kakera_button` | %    | —                        | Kakera react budget                               |
| `additional_spheres`           | int  | clicked + premium        | Perk 9 EV flat SP                                 |
| `sphere_double_chance_pct`     | %    | `$kt`                    | Perk 9 EV double chance                           |
| `rolls_per_hour`               | dict | `$k`/`$kl`/`$kt`/premium | `net`, `sources`, `penalties.bw` / `penalties.bk` |


One `$bonus` bullet is one field. Multi-number lines (`rolls_per_hour`, `oh_daily`, `megaspheres`, `random_kakera`) stay as a single dict instead of flattened keys. Identity is the meaning key, not the suffix — `$bk` on kakera-buttons is not the `$bk` rolls/hour penalty.

### `$shop`

`$shop` is the **ouroperk upgrade sheet** for the connected account (not
server-wide). Discord sends it as Components V2 (Container / TextDisplay /
Thumbnail): empty `content`, empty classic embeds. discord.py-self 2.1
drops those component types, so `mudae/serialization.py` keeps the raw
payload and flattens every `content` field before parsing.

Ten perks, levels 0–10 (`[MAX]` = 10). Continuation lines without a level
tag belong to the previous perk (OP6 omega-key chance, OP9 sphere-value %).
Stored on the channel profile like `$bonus` (`App.fetchShop`). Read-only —
do not send `$shoprefund`.


| Key                        | Type | Later use                                |
| -------------------------- | ---- | ---------------------------------------- |
| `perk9_extra_clicks`       | int  | Daily cap `10 + extra` (max 20)          |
| `perk9_click_max`          | int  | Daily cap `10 + extra` (wired)           |
| `perk9_sphere_value_pct`   | %    | p9calc `shop9_bonus` (10% per OP9 level) |
| `perk2_megasphere_rewards` | int  | Megasphere planner                       |
| `perks`                    | dict | Full OP1–OP10 current/next values        |


`$oh` / megasphere *values* on `$bonus` stay on `oh_daily` / `megaspheres`.

Unknown `$settings` / `$bonus` / `$shop` bullets become warnings (not silent drops).

**Dangerous** `$settings` **commands:** 16 are **direct toggles**. A bare send
flips the live server (no help text, no confirm). Capture tooling
(`scripts/document_settings_commands.py`) skips them unless
`--include-toggles`, which sends then immediately sends again to revert.
List: `DIRECT_TOGGLE_FIELDS` in `mudae/settings_commands.py`.

`$toggleslash`, `$toggleclaimrank`, `$togglelikerank`, `$toggleclaimrolls`,
`$togglelikerolls`, `$togglensfw`, `$toggledisturbing`, `$togglechildtag`,
`$removecopylimit`, `$togglekakeratrade`, `$togglekakeraclaim`,
`$togglekakeralike`, `$togglekakerarolls`, `$togglewishprotect`,
`$togglewishfree`, `$togglespheretrade`.

`$togglerolls` is **not** a toggle. It only prints help for the three
independent rank-on-roll flags above.

---



## `$p` and `$daily` (account-global)

Neither command is per server. Sending `$p` or `$daily` on any channel
consumes the cooldown for that Discord account everywhere, so each account
picks **one** designated channel on the Accounts tab.


| Command  | Cooldown                                               | Success                                           | Retry copy                                       |
| -------- | ------------------------------------------------------ | ------------------------------------------------- | ------------------------------------------------ |
| `$daily` | 20 hours from the successful send                      | Mudae **tick** on the user message                | `Next $daily reset in 20h 00 min.`               |
| `$p`     | Fixed 2-hour slots from UTC midnight (00:00, 02:00, …) | Pokemon grid / `You won` — results are not stored | `Remaining time before your next $p: 1h 41 min.` |


**Macro:** `macro/account_dailies.py` (timing) and
`macro/account_daily_runtime.py` (switch / send / restore). While connected,
due commands go out automatically, **before rolls**. The monitor switches to
the designated channel (reconnect + retries if the gateway drops), then
restores the Run target. Several accounts with a channel set are handled
one after another (still one Discord connection). `$tu`'s
`Next $daily reset` line updates the stored cooldown so a mid-cooldown
connect does not resend.

---

`$bonus` capture is read-only (`$bonus` once). Do not iterate `($kt)` /
`($kl)` as live commands.

The verbatim `$settings` command-help capture is
`docs/archive/MUDAE_SETTINGS_COMMANDS.md` (gitignored) and
`data/settings_commands_capture.json`. Re-run with `--skip-help` to dump
only `$settings` + `$bonus` text.

---



## What the macro does not do (yet)

- Claim by emoji reaction (servers with `$togglebutton` off).
- External sniping of other people's rolls.
- Slash-command rolls.
- Multi-account concurrent connections (config supports it; runtime is
one Discord session — see Phase D in `ARCHITECTURE.md`).
- Playing `$ot` **automatically**. There is a **Play $ot** button, but it is
never part of play-all and never fires after the daily refill.
- Driving claim / kakera / roll from parsed `$settings` / `$bonus` / `$shop`
(parsers are trusted for storage; power max and perk 9 cap are the
exceptions already wired).

