# Mudae logic

How Mudae works, and how FinalMacro uses each mechanic. Code locations are
pointers only — the file map lives in [`ARCHITECTURE.md`](ARCHITECTURE.md).

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

| Field | Meaning |
|-------|---------|
| Claim available / cooldown | Whether you can marry right now |
| Next claim reset | Minutes until the claim slot refills |
| Rolls left | Hourly pool, plus optional `+$us` / `+$mk` bonus |
| Next rolls reset | Minutes until the hourly pool refills |
| Reaction power % | Kakera click budget |
| `$rt` ready / next | Extra claim token |
| `$dk` stock / next | Daily kakera power top-up |
| `$daily` reset | Minutes until the account-global `$daily` (not the hourly rolls reset) |
| Perk 8 refill | When daily perk-8 clicks come back |

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

| Emoji name | Color | Notes |
|------------|-------|--------|
| `kakeraP` | Purple | **Free** — no power cost. Always worth clicking. |
| `kakera` | Blue | Default cheap kakera |
| `kakeraT` | Teal | |
| `kakeraG` | Green | |
| `kakeraY` | Yellow | |
| `kakeraO` | Orange | |
| `kakeraR` | Red | |
| `kakeraW` | Rainbow | Highest single-color value |
| `kakeraL` | Light | Splits into several smaller kakera |
| `kakeraD` | Dark | |
| `kakeraC` | Chaos | Highest tier the macro tracks |

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

**Daily 40 (`$ohu8`):** only perk-8-character paid clicks use the quota.
Red/rainbow on a perk-8 character count because they are on the perk-8
list. The same colours on a normal character are bypass: still clicked
while saving, not counted. After 40/40, non-perk-8 rolls use the main
colour list (equal clicking); perk-8 characters **keep** the perk-8 list
(orange/dark stay allowed).

**`$ohu8` timing:** sent at session start and when the daily refill is due.
Saving is off (`inactive`) until that reply sets `active` / `done`. That
is intentional — the first `$ohu8` of the day is what starts the holdback.
A live `$ohu8` count **overwrites** a stale Run-tab 40/40 (persist from a
spent day or a false catch-up). The local counter is kept only when it is
1–2 clicks ahead of Mudae (a click that has not landed in the `$ohu8`
text yet). After **any wait timeout on a perk-8 click** (first attempt or
retry, success or fail), send `$ohu8` again so a landed-but-unseen click
cannot desync the 40. Non-perk-8 timeouts do not.

**`$us`:** optional narrower `types_allowed` for non-perk-8 `$us` rolls.
Perk-8 characters still use the Reactions perk-8 list. "Don't claim kakera
on `$us` rolls" disables **all** kakera on those rolls, including perk-8.

Implemented in `macro/rule_eval.py` and `macro/kakera_reactor.py`. Caps from
`$bonus` / `$shop` are applied per run channel in `macro/sheet_caps.py`.

**Chaos kakera (`kakeraC`) extras:** the `+$k` body can add `+N rolls this
hour` (spend them now; they die at the hourly reset), store `$oh`/`$oc`/`$oq`/`$ot`
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
2. **`$oh` minigame** — a 5×5 grid of sphere buttons.

Button emoji names are `sp` + a color letter:

| Emoji | Meaning |
|-------|---------|
| `spM` | Megasphere — free bonus on a **roll** (always click; splits like light kakera) |
| `spP` | Purple — **free `$oh` click** (does not use the daily click allowance) |
| `spB` | Blue — lowest paid; skipped in `$oh` (click a face-down instead) |
| `spT` | Teal — same as blue in `$oh` |
| `spG` | Green | |
| `spY` | Yellow | |
| `spD` | Dark — paid click; may resolve to purple in the reward tracker |
| `spL` | Light | |
| `spO` | Orange | |
| `spR` | Red | |
| `sp` | **Red.** Mudae's default sphere emoji when "recognizable sphere buttons" is off. A roll button labelled `:sp:` is red. |
| `spW` | Rainbow — highest paid |
| `spU` | Hidden / face-down in `$oh` |

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

**`$oh` strategy** (`macro/sphere_game.py`):

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

* **Keep draining** pauses on the hourly reset (and on power *if* that stop
  is on) instead of quitting.
* **Stop on power** is optional; `$dk` and perk-8 “held for tomorrow” count.
* **Session roll cap** (e.g. 1000) is a hard stop.
* **Local schedule** (`us_schedule_*`) is this computer’s clock, not UTC.
  While connected it drains `$us` on its own, like `$p` / `$daily`. Roll `$us`
  on the Run page always starts immediately and ignores the window. Auto
  drain uses the session cap and other preset stops; leftover `$us` stays on
  the stack when the end time hits. If hourly is waiting for a refill, the
  schedule pauses it, drains `$us`, then resumes hourly.

---

## Minigames

`$ohu` reports daily uses left / stored for `$oh`, `$oc`, `$oq`, `$ot`.
**Play all minigames** queries `$ohu`, then spends `$oh` / `$oc` / `$oq`.
`$ot` is parsed but not played yet. Extra `$oq` / `$ot` from perk 10 on
the first `$oh` of the day are counted (play-all spends the extra `$oq`).
Playing a game with no uses left gets
``You don't have enough $oh for today. Time to wait before the refill: 3h 08 min.``
(``$oc`` / ``$oq`` / ``$ot`` in place of ``$oh``); the activity log reports
out of minigames instead of a grid timeout.

Each finished `$oh` / `$oc` / `$oq` writes one row to `data/minigame_log.json`
(Statistics → Minigames): the 5×5 after the final reveal, clicks in order,
whether we hit red/rainbow, and **base SP** from `SPHERE_BASE_SP` — not the
chat `+N`, which includes bonuses. `$oq` hunt uses MIXED (`P(purple)+0.1×Gini`).

| Command | What it is | Engine |
|---------|------------|--------|
| `$oh` | 5×5 sphere grid | `macro/sphere_game.py` |
| `$oc` | Color-matching sphere game | `macro/oc_game.py` |
| `$oq` | World / path sphere game | `macro/oq_game.py` |
| `$ot` | Tracked in `$ohu` only | — |

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

**Power / `$dk` reserve** (`macro/perk8_power.py`) is optional on the perk-8
budget panel. Off keeps the old click and `$dk` rules. On keeps enough bar
+ `$dk` that a full perk-8 dump is still payable in the first N hours
**after UTC midnight** (the daily reset; default 4h). Unused perk-8 clicks
expire at midnight, so they always get power and `$dk` first — that is not
a separate setting. After 40/40, chaos kakera still click unless *this*
spend would make the next day's post-reset burst fail; `$dk` on those
reacts only if a new use is in hand by midnight (typical cooldown **20h**).
Purple stays free. Costs assume a chaos key (7.5% perk-8, 15% normal).
N hours is a capacity floor, not a cutoff — slow perk-8 keeps rolling
until 40/40 or reset. The Run page shows the live saver state while the
toggle is on.

State is persisted on the **channel profile** (`daily_resets.perk8`) so a
restart does not re-query until refill. Minigame uses (`daily_resets.minigames`)
skip `$ohu` / play-all until refill. Perk 9 click counts (`daily_resets.perk9`)
are restored for the Run tab; sphere reacts do not skip at the cap — Mudae
stops spawning those buttons.

---

## Perk 9 (daily sphere-button budget)

Perk 9 adds **sphere react buttons** on characters you have rolled today.
Each click consumes one slot from a daily budget (shown on `$ohu9` as
``6/20 buttons clicked`` in the shared minigame header). The macro tracks
this as **clicks used / cap** on the Run page. The cap is
`10 + perk9_extra_clicks` from the run channel's `$shop` (fallback **20**).

- Query with **`$ohu9`** — same layout as `$ohu8` / `$ohu`: minigame
  counts, refill timer, ``buttons clicked``, megasphere stock line, then
  ``(Perk 9) Rolled today: 44/154`` and the list of characters rolled.
- Sphere buttons on those characters are **perk 9 spawns**; after the budget
  is used, no more spawn until the daily refill (same window as `$oh` /
  sphere stock).
- **Megasphere** (`spM`) on a roll is a free bonus, not a perk 9 click —
  the Run counter ignores it.
- The macro increments by one on each confirmed **sphere button click**
  (`MessageKind.SPHERE_CLICK`, excluding `spM`). `SphereReactionRules.types_allowed`
  still governs which colours to click. After the daily budget is used, Mudae
  stops spawning the buttons — the reactor does not add its own skip.

---

## Perk 10 (invested spheres)

Perk 10 pays on the **first `$oh` of the UTC day**. The grid message can
include a line like:

```
+2 $oq, +1 $ot and +5,600 :sp: from your invested spheres!
```

Older lines omit `$ot`: `+2 $oq and +5,344 :sp: from your invested spheres!`

- **Flat SP** is logged as sphere source `perk10` (Statistics → Spheres),
  not as `$oh` minigame earnings.
- Extra **`$oq` / `$ot` uses** are stored on that `$oh` session
  (`oq_bonus` / `ot_bonus`). Statistics → Minigames → `$oh` shows the
  totals. Play-all spends the extra `$oq` (like bonus `$oc` from hidden
  clicks). Extra `$ot` is counted in `$ohu` availability but not played yet.

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

| Key | Type | Typical source tag | Later use |
| --- | --- | --- | --- |
| `kakera_max_power` | int | `$kt` | Reaction-power cap (wired) |
| `power_cost_per_kakera_button` | % | — | Kakera react budget |
| `additional_spheres` | int | clicked + premium | Perk 9 EV flat SP |
| `sphere_double_chance_pct` | % | `$kt` | Perk 9 EV double chance |
| `rolls_per_hour` | dict | `$k`/`$kl`/`$kt`/premium | `net`, `sources`, `penalties.bw` / `penalties.bk` |

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

| Key | Type | Later use |
| --- | --- | --- |
| `perk9_extra_clicks` | int | Daily cap `10 + extra` (max 20) |
| `perk9_click_max` | int | Daily cap `10 + extra` (wired) |
| `perk9_sphere_value_pct` | % | p9calc `shop9_bonus` (10% per OP9 level) |
| `perk2_megasphere_rewards` | int | Megasphere planner |
| `perks` | dict | Full OP1–OP10 current/next values |

`$oh` / megasphere *values* on `$bonus` stay on `oh_daily` / `megaspheres`.

Unknown `$settings` / `$bonus` / `$shop` bullets become warnings (not silent drops).

**Dangerous `$settings` commands:** 16 are **direct toggles**. A bare send
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

| Command | Cooldown | Success | Retry copy |
| --- | --- | --- | --- |
| `$daily` | 20 hours from the successful send | Mudae **tick** on the user message | `Next $daily reset in 20h 00 min.` |
| `$p` | Fixed 2-hour slots from UTC midnight (00:00, 02:00, …) | Pokemon grid / `You won` — results are not stored | `Remaining time before your next $p: 1h 41 min.` |

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
- Playing `$ot`.
- Driving claim / kakera / roll from parsed `$settings` / `$bonus` / `$shop`
  (parsers are trusted for storage; power max and perk 9 cap are the
  exceptions already wired).
