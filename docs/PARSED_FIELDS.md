# Parsed fields — what is wired, and what is sitting unused

Every field the parsers produce, checked against where it is actually consumed.
Method: field names came from `mudae/settings_catalog.py`,
`mudae/parsers/bonus_catalog.py`, `ov_catalog.py`, `shop_catalog.py` and the
parser modules themselves; usage came from grepping `macro/`, `gui/`, `mudae/`
and `scripts/` with `mudae/parsers/` and the catalogs excluded, so "wired" here
means *something outside the parser reads it*.

This is a review list, not a plan. Nothing below is committed to.

---

## Scoreboard

| Sheet | Fields | Wired to behaviour | Stored-only |
|---|---|---|---|
| `$bonus` | 33 | 8 | **25** |
| `$settings` | 34 | 7 | **27** (all 27 are *settable* by the editor, none are *read*) |
| `$ov` | 17 | 1 (`persrare`) | **16** |
| `$shop` | 10 perks + stock | perk 9 (clicks, SP%), perk 1 (spawn share) | **8 perks** |
| `$tu` | 15 | 13 | `rolls_mk_bonus`, `daily_reset_minutes` |
| `$limroul` | 5 | 2 (pool, agreement) | `tops`, `global_rank`, `server_max` |
| `$ohu` / `$ohu8` / chaos / roll / `$dk` | — | nearly all | `like_rank`, `megasphere_left` (one caller) |

`bonus_catalog.py` marks five fields `later=True` ("the macro will need this for
decisions"). **All five are now wired** — the flag no longer marks anything
outstanding and should be re-pointed at whatever comes out of this review.

---

## A. Preflight check — settings that silently blind the parsers

The strongest candidate, because it is not a new feature so much as a class of
failure we have already been bitten by twice (`$togglebutton` claim mode, and
Mudae prose reaching the feed). Several account/server display settings decide
whether a parser can see its input at all. When one is off, nothing errors —
the field simply comes back `None` and the rule downstream quietly stops firing.

| Field | Sheet | What goes blind if it is off |
|---|---|---|
| `setfooter` | `$ov` | `mudae/parsers/roll.py` reads the footer for **perk-8 detection** (`💎/2`), **ownership**, **sphere value on the roll**, and the **rolls-left warning**. All four rely on a footer being printed. |
| `displaykeys` | `$ov` | Keys shown when you roll a character you don't own — the source `parse_keys` reads. Key log and Advisor › Key EV starve. |
| `togglekakerarolls` | `$settings` | Kakera value on rolls → `total_kakera`. `rule_eval.py:205` feeds it straight into the `min_kakera` instant trigger, and `claim_best` ranks on it. |
| `wishdm` | `$ov` | Private wishes. The wish-ping claim path keys on `wished_by`; if wishes are hidden from the channel, that path has nothing to match. |
| `perstogglebutton` | `$ov` | Personal override of the server's `$togglebutton`. Claim method is correctly read per-roll now, but this predicts it *before* the first roll. |
| `toggleletters` | `$ov` | Letters printed next to kakera/sphere buttons — changes what a button looks like to the button parser. |
| `rollsleft` | `$ov` | Where the rolls-left message is drawn, which `roll_limit.py` parses. |
| `togglesnipe` / `togglekakerasnipe` | `$settings` | Whether someone else can take our wish or kakera button, and on what delay — a timing input the reactor currently has no idea about. |
| `hideinfodisable` | `$ov` | Emoji marker on disabled characters — would let a roll be recognised as disable-listed. |

**Shape:** one function that compares the stored `$settings`/`$ov` against what
the macro needs, and a readiness row on the Mudae hub (and/or a warning at
connect). Cheap, uses only sheets we already fetch, and turns a class of silent
failure into a visible one.

---

## B. Kakera value model — the reactor knows cost but not worth

`macro/reaction_power.py` prices a click exactly (base cost from `$bonus`, halved
by chaos key, halved again by perk 8). Nothing prices the *payout*:
`mudae/constants.py`'s `KAKERA_INFO` carries labels and emoji only, and reaction
order comes from the preset's user-chosen list. Everything needed to model the
payout is already parsed and unused:

- `$bonus` — `kakera_button_bonus_pct`, `kakera_button_starwish_bonus_pct`,
  `rank_kakera_bonus_pct`, `kakera_earned_bonus_pct` (premium + server premium),
  `random_kakera` (min/max per light kakera), `kakera_red_rainbow_bonus`,
  `kakera_chaos_bonus`, `chaos_kakera_rarity_mult`, `kakera_gold_keys_bonus`
- `$settings` — `setkakerabonus` (server-wide %), `server_premium`
- `$ov` — `player_premium`

**What it would change:** expected kakera per click *by type*, which is the
missing term in three places that currently guess — the reaction order when
power is scarce, the perk-8 reserve's decision about what to hold power for, and
`us_stop.py`'s `_minimum_kakera_cost` threshold. It is also checkable: the kakera
log already records amount + type per click, so the modelled figure can be scored
against observed income instead of trusted.

---

## C. Sphere EV — three multipliers the perk-9 DP does not see

`macro/perk9_threshold.py` builds its EV from `$shop` perk-9 SP%, `$bonus`
`sphere_double_chance_pct` and `additional_spheres`. Missing:

- `$settings setspherebonus` — a **server-wide % sphere bonus** that multiplies
  every sphere the account earns on that server. Not read anywhere.
- `$bonus additional_sphere_sources` — extra spheres from claims / `$dk` / rank /
  `$rolls`. Would give Statistics and the daily report a source attribution they
  currently infer.
- `$bonus oh_daily` — the daily `$oh` bonus as three numbers (spheres, `$oq`
  chance, `$ot` chance) and `$bonus megaspheres` (rewards + free chance).
  Together with `$shop` OP2 `megasphere_rewards`, OP5/OP10 `ot_chance_pct` and
  OP7 `chaos_double_pct`, these predict how many extra minigame uses a day
  *should* produce — which is exactly the baseline the report has no way to
  state today.

---

## D. Key model — Key EV is starved of half its inputs

Advisor › Key EV models keys per wish spawn from `extra_key_wish_chance_pct` +
perk 4, and abstains on value. Unused and directly relevant:

- `$bonus extra_key_chance_pct` — the **non-wish** variant, which applies to the
  ordinary roll stream. Wiring it turns "keys per wish spawn" into "keys per
  hour", against the 2,200/h cap the page already knows about.
- `$bonus kakera_gold_keys_bonus`, `$shop` OP4 `omega_key_pct`, OP6
  `owned_omega_key_pct` / `wishlist_claim_pct` — the rest of the key sources.
- `$bonus bku_complete_chance_pct` (value + this-interval) — `$bku` is already
  logged (`mudae/kakera_log.py`, `bku` / `bku_reset` on rolls), so this closes
  the loop into a completion forecast rather than a count after the fact.

---

## E. Roll budget and cooldowns

- **`rolls_mk_bonus` is parsed and never read.** `mudae/parsers/tu.py:84-87`
  splits the bonus pool by source: `$us`/`$ru` go to `rolls_us_bonus`, `$mk`/
  `$smk` go to `rolls_mk_bonus`. `rolls_us_bonus` drives a whole ordering rule in
  `roll_cycle.py` (Mudae spends bonus rolls first — the bug fixed on 2026-08-30);
  `rolls_mk_bonus` has **zero consumers**, so monthly-kakera rolls are invisible
  to the same loop that was already wrong about this once.
- **`$bonus mk_per_hour`** — `$mk` is a roll grant on a timer, the same shape as
  `$p` / `$daily`, which already auto-send on a designated channel.
- **`$bonus rt_cooldown`** — `rt.py` parses `rt_available` / `rt_next_minutes`
  reactively; the cooldown length from `$bonus` would let `$rt` be *scheduled*
  the way `$dk` is off `dk_cooldown` (which is wired).
- **`$settings setrare`** — the server-side spawn-rarity multiplier for owned
  characters, the twin of `$ov persrare`. `macro/bw_calc.py` applies persrare's
  N and knows nothing about the server's own multiplier.
- **`$settings haremlimit`** — the collection cap. No claim rule knows it, so
  nothing warns as the harem fills.
- **`$settings channelinstance`** — several Mudae instances in one channel.
  Phase D targeting will need this.
- **`$tu daily_reset_minutes`** — reaches the bridge for display only, though it
  is the same daily boundary `macro/minigame_daily.py` and `perk9_daily.py`
  compute themselves from `shifthour`.

---

## F. Pool and disable-list intelligence

- **`$limroul tops` / `global_rank`.** The parser's own docstring spells out what
  they mean: local `#2,000` sitting at global `#3,405` means **1,405 more popular
  characters are disabled on this server**. That is a live estimate of the
  server's disable list, from a sheet we already fetch — and `TODO.md` currently
  skips the disablelist optimizer precisely because we have no bundle dump. This
  won't give per-character detail, but it sizes the list, and it feeds the `$bw`
  sweep's pool the same way `$limroul`'s Current line does.
- **`$bonus limroul_animanga` / `limroul_game`** — the account's own unlock
  ceiling, cross-checkable against `$settings servlimroul` (server cap) and the
  `$limroul` Current line (what is actually set). Three readings of one number
  that should agree; disagreement is itself information.

---

## G. Small, cheap, low-risk

- `$bonus wishlist_slots` / `wishseries_slots` / `starwish_slots` — capacity for
  the Advisor › Wishlist page, cross-checkable against the `$wl` capture's own
  `wl_used`/`wl_max`/`sw_used`/`sw_max`.
- `$bonus wishprotect_spawn_chance` (a ratio, e.g. 1/499) with `$settings
  togglewishprotect` — whether wishprotect is actually live here, and how often.
- `$settings togglekakeraclaim` / `togglekakeralike` — whether claims and likes
  feed the kakera value shown on rolls, i.e. whether `total_kakera` means what
  a rule assumes it means on this server.
- `$settings togglewishfree` — freewish: a wished character costs no claim.
  A claim rule that knew this could take a wish without spending the slot.
- `$settings togglekakeratrade` / `togglespheretrade` — needed before any future
  trade/invest automation; the invest path is blocked anyway.
- `roll.like_rank` — parsed, no consumer (`claim_rank` has one, in `rule_eval`).
- `$ohu megasphere_left` — one caller (`perk9_daily`), no surface anywhere else.

---

## Deliberately not worth wiring

`$ov`: `rdmimg_random` / `rdmimg_gif_webp` / `rdmimg_custom`, `imglink`,
`kakeradm`, `disablepins`, `togglemovepage`. `$settings`: `prefix` (already used
as a command prefix, not a decision), `lang`, `togglensfw`, `toggledisturbing`,
`togglechildtag`, `removecopylimit`, `toggleclaimrank` / `togglelikerank` /
`toggleclaimrolls` / `togglelikerolls` (display only), `toggleslash` (the macro
rolls with `$`; `bw_calc` already models the slash bonus and deliberately does
not apply it).

---

## If a shortlist is wanted

1. **A — preflight check.** Cheapest, and it protects rules that already exist.
2. **E — `rolls_mk_bonus`.** Smallest possible change, and it is the same class
   of defect as a bug we have already paid for once.
3. **B — kakera value model.** Biggest behavioural upside, and scoreable against
   the existing kakera log rather than taken on faith.
4. **C / D.** Both make existing pages (report, Key EV) say more with no new
   capture.
5. **F.** One genuinely new capability out of a sheet already on disk.
