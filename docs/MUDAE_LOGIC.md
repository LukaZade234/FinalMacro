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
| Perk 8 refill | When daily perk-8 clicks come back |

**Macro:** almost every session starts with `$tu`. Claim timing, `$us`
stacking, `$dk`, and reaction-power estimates all come from this message.
Between rolls the engine tracks power locally instead of polling `$tu` every
time (`macro/reaction_power.py`).

---

## Claims

Claiming a character uses the claim **button** on the roll embed (💍 / 💖 /
similar). Some servers hide buttons and require an emoji reaction instead.
The macro only supports **button claims**. Claim-via-emoji is deliberately
not implemented until the `$settings` audit is done (`docs/TODO.md`).

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

**Reaction power:** seeded from `$tu` / `$ku`. Base click costs 30% of the
bar. A **chaos key** on the character halves the cost; **perk 8** halves it
again. Power regenerates 1% every 3 minutes. `$dk` tops the bar back up
(limited stock).

**Macro:** `KakeraReactionRules` filters by color, optional chaos-key /
perk-8 / min-spheres gates, a low-power override list, and perk-8 daily
budget mode. Purple is the default bypass for both the chaos-key gate and
the perk-8 budget (it is free). `$us` rolls can use a narrower color list.
Implemented in `macro/rule_eval.py` and `macro/kakera_reactor.py`.

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
normal rules or a narrower override (`UsRollKakeraRules`). Stop options
include power exhausted and “stop after N rolls”.

---

## Minigames

`$ohu` reports daily uses left / stored for `$oh`, `$oc`, `$oq`, `$ot`.
**Play all minigames** queries `$ohu`, then spends `$oh` / `$oc` / `$oq`.
`$ot` is parsed but not played yet.

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
(40 clicks, `$ohu8`). The macro can enter **budget mode**: spend those
clicks on perk-8 characters first, still allow free purple on everyone
else, then treat all characters equally once the 40 are used or the roll
pool is under 10.

State is persisted on the **channel profile** (`daily_resets.perk8`) so a
restart does not re-query until refill. Other daily items (`$oh` / `$oc`
counts, sphere stock) are not generalized yet — see `docs/TODO.md`.

---

## `$settings` and `$bonus`

`$settings` is the server's rule sheet: prefix, claim/roll timers, sniping,
whether claim/kakera/sphere buttons are “recognizable”, game mode, etc.
`$bonus` is a second sheet of bonuses.

The GUI can fetch both onto a channel profile. Parsers live in
`mudae/parsers/settings.py` and `bonus.py`. They are **not fully trusted
yet** — field-by-field audit is still open (`docs/TODO.md`). Until that
lands, the macro does not change claim/kakera/roll behavior from parsed
settings.

**Dangerous commands:** 16 `$settings`-adjacent commands are **direct
toggles**. Sending them with no argument flips the live server setting
(no help text, no confirm). During the capture pass each flip was
immediately sent again to revert. Any script that iterates `$settings`
commands must skip these or revert them:

`$toggleslash`, `$toggleclaimrank`, `$togglelikerank`, `$toggleclaimrolls`,
`$togglelikerolls`, `$togglensfw`, `$toggledisturbing`, `$togglechildtag`,
`$removecopylimit`, `$togglekakeratrade`, `$togglekakeraclaim`,
`$togglekakeralike`, `$togglekakerarolls`, `$togglewishprotect`,
`$togglewishfree`, `$togglespheretrade`.

`$togglerolls` is **not** a toggle. It only prints help for the three
independent rank-on-roll flags above.

The verbatim capture is `docs/archive/MUDAE_SETTINGS_COMMANDS.md` (gitignored)
and `data/settings_commands_capture.json`.

---

## What the macro does not do (yet)

- Claim by emoji reaction (servers with `$togglebutton` off).
- External sniping of other people's rolls.
- Slash-command rolls.
- Multi-account concurrent connections (config supports it; runtime is
  one Discord session — see Phase D in `ARCHITECTURE.md`).
- Playing `$ot`.
- Driving decisions from a fully audited `$settings` / `$bonus` parse.
