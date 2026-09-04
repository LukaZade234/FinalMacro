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
similar) *where buttons exist*. `$togglebutton` (per server) and the user's own
settings can switch them off, and an unclaimed roll then arrives with no
components at all — you claim it by **reacting** to the roll with any emoji.
The macro supports both.

**It reads the mode off the roll, not off `$settings`.** The two settings can
disagree (a server can have buttons on while the account has them off), and the
roll is the only place their combination actually shows up, so nothing here
depends on `$settings` being parsed:

| roll's components | mode | `claim_method` |
| --- | --- | --- |
| an **enabled** claim button | button | `"button"` |
| **no** claim button at all | reaction | `"reaction"` |
| a **disabled** claim button | button, window shut | `None` |

`mudae.buttons.claim_method_from_buttons` owns that table; `parse_roll` adds the
two roll-level vetoes (already claimed, or a profile embed rather than a roll)
and sets `can_claim = claim_method is not None`, which is what every claim rule
downstream gates on. The disabled-button row matters: that is button mode with
the claim window already closed, and reacting there would do nothing, so it must
not be confused with the button-less case.

`PostRollHandler._send_claim` (`macro/post_roll.py`) then either clicks or
reacts; everything after the claim is sent — the `wait_for_claim` reply, the
`CLAIM_INTERVAL` sync, marking the slot spent — is the same path either way.
The reaction is `CLAIM_REACTION_EMOJI` (`✅`, `mudae/constants.py`), the same
green tick Mudae itself uses to acknowledge a command; Mudae accepts *any*
emoji, so the choice is cosmetic and picking a custom one is a future polish
item. `ChannelMonitor.add_reaction` retries transport blips exactly like
`click_button`, since a lost claim react loses the character just as a lost
click does.

You get one claim slot per claim interval (`$setclaim`, often 60–180 minutes).
`$rt` (reset claim) is a separate token that grants an extra claim; it has
its own long cooldown.

**Final hour:** the last roll session of the current claim window — when
`$tu`'s claim-reset minutes **equal** the rolls-reset minutes. Example: 3h
claims and 1h rolls → final hour is the hour where both timers show 60.
Implemented in `macro/claim_window.py`.

**Macro claim rules** (`CharacterClaimRules` / `passes_character_claim`):

1. Wish ping on a claimable roll (button *or* reaction) → claim
  **immediately** (interrupt the roll loop).
  If the slot is on cooldown and `$rt` is available and `auto_use_rt` is on,
   spend `$rt` and claim.
  **The app's own wishlist counts as a wish ping.** A roll whose character or
   series is on the app-side wishlist (`macro/wishlist.py`, Advisor → Wishlist)
   raises the *same* `code="wish_ping"` interrupt, so it takes this identical
   path — `$rt` included — rather than a parallel one. It is gated on
   `claim_on_wish_ping` like a real ping, and unlike the Mudae-side check it
   also verifies `claimed` / `can_claim` first, since a name match carries no
   guarantee the roll is still claimable. Names match exactly, case- and
   whitespace-insensitively (never substring). A **Global** toggle picks what
   is matched: one list everywhere, or a separate list per (account, channel),
   resolved against the *run target* — not the page's scope bar.
2. Kakera value ≥ `min_kakera`, or claim rank ≤ `max_claim_rank` → claim
  immediately.
3. Otherwise, if `only_final_hour` is on and this is not the final hour →
  skip (save the slot).
4. Eligible leftovers are compared at the **end of the batch**; the best one
  is claimed then.

Already-claimed characters, profile embeds, and rolls whose claim button Mudae
has disabled are skipped. A roll with **no** button is not skipped — that is the
reaction case above.

**"Once per interval" rejection.** If the claim slot's real state has drifted
from what the last `$tu` reported (e.g. connecting mid-window), a claim button
click can come back rejected: *"For this server, you can claim once per
interval of Xh. The next interval begins in **N** min."* — parsed as
`MessageKind.CLAIM_INTERVAL` (`mudae/parsers/claim_interval.py`). This is the
**same slot** `claim_available` / `claim_cooldown_minutes` already track, just
reported through a different message, so `_try_claim`
(`macro/post_roll.py`) syncs it the same way `$tu` parsing does — `wait_for_claim`
recognizes the kind (it used to time out on it, since it only matched
`CLAIM`/`MARRIAGE`) and the handler sets `claim_available = False` /
`set_claim_cooldown(next_interval_minutes)` from the reply. The existing
`claim_available is False` guards (in `claim_best`, and the `$rt`-bypass path
in `claim_record`) then apply immediately, instead of a later roll in the same
batch clicking into the same wall again.

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
  The threshold always assumes the *next* click lands on a chaos key — the
  cheapest a paid click can ever be — using the account's real `$bonus` base
  cost when known (fallback 30%, so 15% under chaos). Deliberate: pricing the
  stop at a plain click's cost (30%, no chaos) would trip the toggle well
  before power is actually exhausted, since a chaos-key click might still be
  affordable. `macro/us_stop.py::_minimum_kakera_cost`.
- **Pause at the hourly key limit** (`us_stop_on_key_limit`, default off) — see
below.
- **Session roll cap** (e.g. 1000) is a hard stop.
- **Local schedule** (`us_schedule_`*) is this computer’s clock, not UTC.
While connected it drains `$us` on its own, like `$p` / `$daily`. Roll `$us`
on the Run page always starts immediately and ignores the window. Auto
drain uses the session cap and other preset stops; leftover `$us` stays on
the stack when the end time hits. If hourly is waiting for a refill, the
schedule pauses it, drains `$us`, then resumes hourly.

### Roll order: the `$us` bonus goes first

The usable pool is `rolls_left + rolls_us_bonus`, and **Mudae spends the
already-added `$us` rolls before the hourly ones**. That is Mudae's rule, not a
macro preference, and every roll obeys it whatever the macro calls the roll.
Two things follow:

- Leftover normal rolls are only reachable once the bonus is spent. `$tu`
reading `1 (+6 $us)` means six `$us` rolls and *then* the hourly one — the `1`
does not move until the bonus is empty.
- The bonus rolls must carry the `$us` kakera rules
(`kakera_rules_for_roll(us_roll=True)`), because they are `$us` rolls.

`_run_us_cycle` therefore rolls the bonus batch first and the leftover normal
rolls after, in both the steady-state path and the reset-margin one. Getting
this backwards is what caused the **`$tu` ↔ one-roll alternation**: the loop
rolled a single "leftover normal" roll, the roll came off the bonus, `$tu`
reported the same `rolls_left`, and it rolled one more — one `$tu` per roll
until the bonus drained.

### Hourly key limit

Mudae grants at most **2,200 keys per hour**. Past that the roll card prints

```
❌ (You reached the limit of 2,200 keys per hour!)
```

in place of the key line. The roll still counts and can still be claimed —
only the key gain is refused — so it is a reason to stop rolling, not a failed
roll. `parse_key_limit` (`mudae/parsers/kakera.py`) reads the number Mudae
names rather than assuming 2,200; `parse_roll` exposes it as `key_limit`, the
Run feed marks the card, and `AccountState.key_limit_hit` holds it until the
hourly rolls reset clears it (the key window shares that boundary).

`us_stop_on_key_limit` turns it into a **pause**: the loop stops rolling on the
capped card, waits out the rest of the hour, then resumes with the stack
untouched (`_wait_for_key_limit_reset`). Unlike the reaction-power pause it is
**not** gated behind keep draining — power may never come back inside a
session, whereas the key cap always lifts at the next reset, which the loop
already waits out for everyone. Enabling the toggle is the opt-in.

The tell that the hour turned is `$tu`'s reset countdown jumping back **up**
(e.g. 30m → 58m); the raw number says nothing on its own. The wait sleeps
through the bulk of the countdown using the known deadline rather than polling
`$tu` at it, and a local schedule window ending still cuts it short.

The toggle lives in the `$us` rules alone — the cap is effectively unreachable
on hourly rolls.

---



## Mudae direct messages

A few Mudae commands answer by **DM** rather than in the channel — `$wlsz+z!`
is the one this was built for, since it sends the whole wishlist (with the
sphere upgrades on each character) in one message instead of a paged embed.

The gateway is the whole **account**, not one channel: `discord.py-self`
delivers the account's DMs over the same connection the run channel uses, so
no second connection or login is involved. `ChannelMonitor` nonetheless drops
every DM unless **Settings → Mudae direct messages** is on
(`allow_mudae_dms`, default **off**) — it is the account's private mail, not
the shared channel the user pointed the macro at, so it is opt-in.

With the toggle on, `_handle_mudae_dm` is deliberately the narrowest path in
the reader:

- Only messages with **no guild** (the definition of a DM) and only from
  Mudae's own bot id (`is_mudae_message`) are looked at. Another guild's
  channel is still ignored — the toggle opens DMs, not everything the account
  can see.
- It parses the snapshot and hands it to `on_parsed`, which is what lets
  `DiscordActions.wait_for` match a reply that arrives by mail rather than in
  the channel.
- It does **not** reach the live feed (that mirrors channel text, and a DM is
  not in the channel), does not touch `CommandContextTracker` /
  `ClaimContextTracker` (both keyed to the run channel), and does not cache
  the message for button clicks.
- The flag is read per message, so flipping it off stops the reading
  immediately without a reconnect.

**With the toggle off** the same information has to come from the in-channel
reply, which Mudae pages — the macro clicks through each page and joins them.
That is the slower path and a slow page can truncate a long list, which is the
trade the setting exists to let the user make.

### `$wl` — the wishlist listing

`$wlsz+z!` (DM) and `$wlz+z!` (channel) return the same body: the account's
wishlist, one line per character. The `s` flag is what redirects a reply to
DMs and works on most commands; it is only worth using where the reply is long
enough to be paged, which is why `$settings` / `$bonus` never need it. Mudae
reacts to the command with a **mailbox** when it sent the DM and an **✕** when
it could not.

```
lukazade234's Wishlist - 160/162 $wl, 16/16 $sw
Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full
Nazuna Nanakusa ✅ 🔐 +125% · 7,000 sp - 5 (x5), 6, 8, 9, 10
Tanya Degurechaff ✅ 🔐 · 7,600 sp - 4 (x2), 5 (x5), 6, 8, 9, 10
Page 1 / 8
```

The header is the **wishlist size** the `$bw` optimum has always been blocked
on. `⭐` marks a starwish, and **starwishes are a subset of the `$wl` count,
not extra slots** — 16 starred rows against `16/16 $sw`, and 160 rows over 8
pages of 20 against `160/162 $wl`. `+N%` is the character's sphere value bonus
(absent on most rows), the `N sp` figure is spheres invested, and the tail is
the **ouroperk roster** — `Full`, or perk numbers with `(xN)` multiplicity.
That roster is the capture `macro/sphere_upgrades.py` abstains on for perk 1
and the Spheres → Characters page needs.

Parsed by `mudae/parsers/wishlist.py`, one message at a time; `$wl` bolds
rows inconsistently (and mid-row, `**7,000** sp`), so bold is stripped rather
than trusted. `merge_wishlist_pages` joins the parts and de-duplicates by
name, since paging back and forth revisits rows.

`macro/wishlist_capture.py` drives whichever route the setting allows:

- **DM** — parts arrive back to back with no page footer, so the end is found
  from the header count plus a quiet gap.
- **Pages** — 20 rows at a time, navigated with the **two buttons** on the
  message. They carry Mudae's custom `wleft` / `wright` emoji, so they look
  like reactions but are ordinary components. **They classify as `claim`**:
  their custom ids have the same `<id>p<id>p<id>` shape a claim button has, so
  `classify_button_kind` cannot tell them apart — the forward arrow is found
  by its `wright` emoji, never by button kind. Mudae edits the one message in
  place, which is the same click → wait for the edit → read it loop the
  minigame boards already use. Paging stops when every page number has been
  seen rather than when the forward button goes quiet, since a paginator that
  wraps never runs out.

**A reply the macro asked for is routed by command name, not by shape.**
`parse_mudae_message` pairs a reply with the command just sent and dispatches
on that, returning **before** `classify_message` runs — so the classifier
protects only *unpaired* messages (a hand-typed command, or the edit that
arrives after a page click). `$wl` / `$wlz` / `$wlsz` are therefore aliased to
a `wishlist` parser in `mudae/commands.py`; without that alias the command is
unknown, `resolve_command` falls through to detection, and
`detect_command_from_snapshot` answers **`roll`** for anything with a
roll-shaped embed. That is what made the listing parse as a roll.

Note the consequence for consumers: a paired reply comes back as
`COMMAND_RESPONSE` with `parser_command: "wishlist"`, not as
`MessageKind.WISHLIST` — true of every command, not just this one. Anything
waiting on a listing must accept both, the way
`macro.actions.is_tu_parse_result` does for `$tu`.

**Flags reach the alias table two different ways.** `send_command` records
what the macro sent *verbatim* (`wlz+z!`), while `CommandContextTracker` — which
watches what the **user** types — has already stripped flags to the bare word
(`wlz`). Only the second used to hit the aliases, so the identical message
parsed correctly when typed by hand and as a **roll** when the macro sent it.
`normalize_command` now falls back to the leading command word, with an exact
match still winning so `ohu8` / `ohu9` are untouched.

**Page edits nearly died in the reader.** Every page after the first arrives as
an *edit* of the same message, and `ChannelMonitor._handle_message` drops
edited Mudae messages whose embed looks like a character embed unless they are
ownership confirmations. A listing embed does look like one, so page clicks
were silently discarded before any parser saw them; the reader now lets a
listing through that filter.

**The channel reply is an embed; the DM is plain text.** The channel form
carries **no message content at all** — the header is the embed's `author`,
the rows its `description`, and `Page 1 / 8` its `footer` — so anything
reading only `content` sees an empty message. `wishlist_text()` reads both
forms. Classifying it matters for a second reason: with claim-shaped buttons
and an author line that reads like a character name, an unclassified listing
page parses as a **roll**, complete with `can_claim: true`.

Either way a listing that lost a part comes back **marked incomplete** rather
than as a short wishlist — both the `$bw` maths and the perk roster are wrong
if rows go missing silently.

#### Ouroperks per character

The roster on each row is what a character carries. **Perks 1–5 have six
levels; perks 6–10 are a single unlock.** At level 0 a perk does nothing.

| # | Levels | What it does | At max |
| - | ------ | ------------ | ------ |
| 1 | 6 | Spawn chance up for the character(s) **next to this one in `$wishlist`** | 125% |
| 2 | 6 | Base kakera value up | 160 |
| 3 | 6 | Chance of **+1 kakera button** under this character | 55% |
| 4 | 6 | Chance of **+1 key** for this character | 30% |
| 5 | 6 | Spheres per kakera button (except purple) you click on a roll of it | 23 |
| 6 | 1 | 2% chance a random wishlist character appears after rolling it — wishprotected if unclaimed, **3 omega keys** if already yours | — |
| 7 | 1 | Kakera buttons can become **chaos kakera** on a roll of it (1% per kakera, not red/light/dark/rainbow) | — |
| 8 | 1 | Spawns **4 kakera buttons** (no purple) at half power on the day's first roll, yours only. Discount covers the day's first 40 clicks; after 40, perk-5 spheres on those buttons are **doubled** | — |
| 9 | 1 | A **sphere button** on the day's first roll of it; 1/7 per click gives a `$oq`. Up to 10 spheres a day, yours only | — |
| 10 | 1 | The day's first `$oh` gives **+4 spheres** and +0.5% chance of a `$oq` | — |

**Costs.** Each level of perks 1–5 costs **200, 400, 600, 800, 1000** and then
**2000** for the sixth — 5,000 to max one. Perks 6–10 cost **1000** each to
unlock. All ten maxed is therefore `5 × 5000 + 5 × 1000 =` **30,000 sp**,
which is exactly what the `Full` rows list.

That ladder is not just reference: `gui/mudae_wishlist_store.py` derives each
character's cost from its roster and shows it against Mudae's own `N sp`
figure. They agree on every real row seen so far — `5 (x5), 6, 8, 9, 10` is
3000 + 4000 = 7,000, `5 (x6), …` is 5000 + 4000 = 9,000, `4 (x2), 5 (x5), …`
is 600 + 3000 + 4000 = 7,600 — so a disagreement means the ladder changed or
the row was misread, and the page flags it rather than hiding it.

**The `+N%` on a row is not yet explained.** Observed values are 125 / 188 /
313, and perk 1 maxed is 125%, so it is presumably spawn chance a character
*receives* from its neighbours' perk 1 rather than its own — but no neighbour
arithmetic reproduces all three figures, so it is stored and displayed as
Mudae reports it and nothing is derived from it.

---



## Minigames

`$ohu` reports daily uses left / stored for `$oh`, `$oc`, `$oq`, `$ot`.
**Play all minigames** queries `$ohu`, then spends `$oh` / `$oc` / `$oq` / `$ot`.
`$ot` also keeps its own **Play $ot** button for an on-demand single play.
Extra `$oq` / `$ot` from perk 10 on the first `$oh` of the day are counted and
play-all spends both.
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

**`$oh` play is greedy, and it is now checked, not just assumed**
(`macro/sphere_game.py:choose_oh_click`): take any revealed purple free,
else the highest-**paying** revealed sphere, never blue/teal, else a random
face-down — and, only once no face-down remains and clicks are still left,
a revealed blue/teal rather than forfeiting the click. Ordering among
revealed spheres is by real SP (`_OH_CLICK_VALUE`), not the ordinal
`SPHERE_VALUE_RANK` — that rank puts dark below orange, but dark pays ~104
against orange's 90. `SPHERE_VALUE_RANK` is shared with `$oc`/`$oq` and is
left alone.

`macro/oh_solver.py` backward-induces the exact expected value of "click a
face-down" against "click a known revealed blue/teal" over
`(clicks_left, blue_visible, teal_visible)` — the one decision on this board
without a self-evidently dominant answer (a revealed purple is always free
money; anything green or above already outpays a face-down click before its
unveil bonus is even counted, so it is always taken on sight; see the
solver's docstring for the full argument). **Result: a face-down click wins
at every clicks-left level checked, 1 through 10** — it carries the same
chance of resolving to blue or teal, and the same resulting unveil, plus a
shot at every higher-value colour, so it strictly out-earns cashing in a
known one. The shipped "never click a revealed blue/teal" rule was already
optimal; the DP confirms it rather than replacing it, and 0 of the 94
recoverable logged boards change under it (`scripts/oh_bakeoff.py
--from-log docs/minigames_to_use.jsonl`). The one real gap the DP did
surface was an endgame bug: the old heuristic returned `None` (forfeiting
the click) whenever no face-down remained even if a revealed blue/teal and
budget both still did — fixed by falling back to the best revealed sphere,
blue/teal included, only in that last-resort case.

There is now a simulator and replay harness (`macro/oh_replay.py`,
`scripts/oh_bakeoff.py --from-log`) so any future policy can be scored, and
a `policy="dp"` leg exercises the solver's chooser the same way. Replaying
the 94 recoverable logged boards gives 156.5 SP against 153.4 in live play.
Two cautions baked into it:

* **The replay is stochastic** — unveil targets are random, so every board
  is averaged over several seeds.
* **An `$oc` spawn is invisible.** It renders as `spU` even after being
  unveiled, so it never leaves the face-down pool and cannot be targeted.
  Clicking one grants a whole extra `$oc` game (~314 SP), but the harness
  values it at **0 by default**: priced at 314, a policy search will happily
  stop claiming known spheres to farm a random drop it cannot actually aim
  at. The bakeoff prints both valuations so no conclusion rests on it.

**The `$oc` grant scales with the `$oh` multiplier.** An `$oh` played as
`$oh 4` spends four uses and multiplies its rewards, the `$oc` grant
included, and Mudae writes the whole amount on one hidden-sphere line:
`<:spU:…> **+4 $oc**`. The number is the count of uses, not spheres — the
same amount slot a coloured line uses for SP, which is why
`total_reward_from_content` skips `spU` lines. `macro/sphere_game.py`
reads it with `oc_grants_from_content` / `new_oc_grants` and passes it to
`classify_oh_click(oc_grants=…)`; play-all then adds it to the `$oc`
budget. Counting the *lines* instead (what the macro did until this was
found) banks one use out of four and silently drops the rest.

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

**Only blue costs a click**, and the budget is 4.

#### Extra Chance — the hidden rule

A blue ends the board **only when it is the 4th-or-later blue *and* at least
5 non-blue cells have already been clicked.** Below 5 hits the blue is
granted instead, tagged `(Extra chance)` in the reward line, and play
continues — repeatably. That is why a perfect game is *8* Extra Chances:
11 blues on a 6-colour board, minus the 3 that were never fatal anyway.

Hits are counted at the moment of the blue click. Crossing 5 hits on a ship
cell arms the ending without triggering it; the **next blue** is what ends
the board.

Confirmed by the ten games of 2026-08-30, which split cleanly:

| games | ship hits at the 4th blue | what Mudae did |
| ----- | ------------------------- | -------------- |
| 9     | 6, 8, 10, 10, 12, 13, 14, 16, 16 | locked the grid and revealed the board |
| 1     | **3** | left the grid clickable |

The macro was still stopping itself at 4 blues, so on that tenth board it
walked away from a live game with 18 cells unclicked — which is why that row
in `data/minigame_log.json` is full of `spU`. `macro/ot_solver.ot_game_over`
now owns the rule, `EXTRA_CHANCE` switches it, and the old reading is kept so
`scripts/ot_bakeoff.py` can price the difference.

**This inverts the game.** While hits are under 5 *nothing* can end the
board: blues are free and the four ship hits are the scarce resource. Clear
the blues and every remaining cell is a certain ship, free forever — the
whole 25. The old rule made "click any `P(blue) = 0` cell" strictly
dominant; the new one makes it a mistake while the phase is live, because a
certain ship stays collectable afterwards but the hit token does not come
back.

The solver does not enumerate those millions of placements. A configuration
is a (teal, green, yellow) triple — there are only **5,520** legal ones —
plus a set of disjoint dominoes on what is left, and the dominoes are
*counted* by a memoised DP rather than listed. Per-cell marginals come from
one identity: the configurations that leave cell `c` empty are exactly the
packings of the free region **without** `c`. Exact, and 0.28s from a cold
cache falling to ~0.002s once three cells are known.

#### The policy — two phases

*While Extra Chance is live* (`hunt`): hold the certain ships back and score
`ev(c) + 600·P(blue at c)`, chasing the blues that can never be clicked
safely later.

*Afterwards*: every certain ship is free, so harvest first, then probe by
`ev(c) − 60·P(blue at c)` — the same expression with the opposite sign. Once
the budget is spent but the board is still alive, only certain ships are
safe, so the harvest does all the work and the probe only runs when nothing
is certain at all. Scoring that last probe by what it *unlocks* was tried and
still loses (968.1 vs 971.1 on the real boards), so `lookahead` stays a dead
end everywhere.

The two halves have **different boundaries**, measured on 120 generated
boards per colour count per generator (uniform / sequential, paired t vs the
old solver):

| `N` | blues | deferring only | + blue bonus (600) |
| --- | ----- | -------------- | ------------------ |
| 6   | 11    | +129 (t 3.7) / +142 (t 2.3) | **+176 (t 4.0) / +206 (t 3.9)** |
| 7   |  9    | +109 / −7 | **+219 (t 2.6) / +15** |
| 8   |  7    | +30 / −56 | −46 / −111 (t −2.6) |
| 9   |  5    | −15 / +13 | −118 (t −3.7) / −154 (t −3.9) |

Deferring is on everywhere: a clear win at 6 colours under both generators
and never significantly negative anywhere. The bonus is on only at 6–7
(`OT_BLUE_BONUS_COLORS`), because at 8–9 there are just 5–7 blues, the four
ship hits run out before the hunt lands one, and the budget is better spent
resolving the board — `--sweep-blue-bonus` is negative at every bonus from
150 up on both. Nothing adaptive rescued 8–9 (`K/(5−h)`, `K·(5−h)/5`, and
scaling by blue density all still lost). With the bonus off, 8–9 is a wash —
the two generators do not even agree on its sign — which is exactly why the
switch exists rather than one global setting.

On the **27 real boards**: **915 SP against the 745.5 those boards actually
paid**, **100.2% of the all-ships ceiling** (blues pay too, so a cleared board
lands above it), **7 of them cleared outright** — **+168.9 SP over the old
solver, t = 3.72**. Only **9.6%** of the total board SP is left unclicked, and
none of it is recoverable by the endgame: on every board that lost SP the
endgame collected *everything* that was certain when the hunt ended. Fixing only the end condition
and keeping the old policy changes *nothing* on these 16, because the old
probe always reaches 5 hits before its 4th blue; it would have saved the
10:45 board, which is not in the set precisely because it was abandoned.

#### `OT_RARE_WEIGHTS` is measured, not borrowed

The rare length-2 ship colours used to be weighted by the Colblitz `$oh`
per-cell *spawn* rates (L 2.96 / D 1.46 / R 0.22 / W 0.04), on the assumption
that ship rarity tracks sphere rarity. **It does not.** Across the 26 rare
slots then available, those weights predict 1.2 reds and 0.2 rainbows
where **4 and 3** turned up. Since rainbow pays 500, an unidentified length-2
cell on a 7-colour board was valued at ~92 SP against a true ~208, and the
solver walked past rare ships. The weights are now the observed counts
(L 13 / D 6 / R 4 / W 3); `tests/test_minigame_log_models.py` re-checks them
against the log rather than pinning them.

Two things this sample cannot yet settle. Seventeen of the twenty-seven
boards carry exactly one rare, and that one is **light 14 times to dark 3** —
far more lopsided than the weights predict, so the single-rare draw may follow
a different rule from the multi-rare one. And `OT_CELL_SP`
still values light/dark at the `$oh` means (76 / 104), while the eight `$ot`
light clicks logged so far resolved to 40–200 (mean ≈ 86) and the two darks to
5 and 35. The per-click `resolved` lists are in `data/minigame_log.json`, so
both become measurable as boards accumulate.

#### What `$ot` actually pays

`base_value` in the minigame log is `SPHERE_BASE_SP`, and that is **not** the
award. `2 × base_value + 36 × clicks` reproduces 5 of the 10 logged rewards
exactly (`+1202`, `+2770`, `+1404`, `+3940`, `+662`) and is within 3% on 4
more. The per-click term matters strategically — one more click is worth ≥ 56
real SP whatever colour it is — but the multiplier is account-scoped (`$oq`
grids print their own `Multiplier: 3x`), so it stays out of the solver and
lives in `ot_replay.OT_CLICK_BONUS_SP` as a reporting figure only.

Validated against real boards in `tests/test_minigame_log_models.py`: every
logged board is straight-line, matches its declared colour count, and is
reachable by the enumerator; blue clicks all cost budget and ship clicks
never do; and a finished game's last blue always satisfies `ot_game_over`
while the unfinished one does not.

Score policies with `scripts/ot_bakeoff.py` (`--known`, `--from-log`,
`--trials`, `--by-colors`, `--sweep-risk`, `--sweep-blue-bonus`). Because the
bonus wins at 6–7 and loses at 8–9, an aggregate mean averages a real effect
against a real regression — use `--by-colors` for anything you act on.

**`$ot` runs in `PLAYABLE_MINIGAMES`**, the same as `$oh` / `$oc` / `$oq`:
play-all spends it and it starts itself after the daily refill. It was
manual-only (Run page **Play $ot** button, `macro/ot_game.py`) while the
solver was tried against real boards; that measured 100.2% of the all-ships
ceiling across 27 real boards under Extra Chance, so it was promoted. The
button still exists for an on-demand single play.


| Command | What it is                 | Engine                 |
| ------- | -------------------------- | ---------------------- |
| `$oh`   | 5×5 sphere grid            | `macro/sphere_game.py` |
| `$oc`   | Color-matching sphere game | `macro/oc_game.py`     |
| `$oq`   | World / path sphere game   | `macro/oq_game.py`     |
| `$ot`   | 5×5 battleship             | `macro/ot_game.py` + `macro/ot_solver.py` |


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

**Minigames start themselves at exactly two moments: when the hourly macro is
started, and at the UTC daily reset.** Every other play is the user's to
trigger from the Run page. This is a deliberate limit, not a consequence of
when uses happen to be available: uses accrue all day — a chaos capture grants
a `$oc`, perk 10 grants `$oq` / `$ot` on an `$oh` board — so there is almost
always something spendable, and `RollCycleEngine._maybe_play_daily_minigames`
is reached from every hourly cycle and every scheduled wake. It gates on
`_minigames_played_for_day` so those extra opportunities pass without playing.
Anything left unspent waits for the next reset batch rather than being spent at
the first opportunity that notices it.

There is deliberately **no** hold-off in the closing minutes before the reset.
The daily allowance is use-it-or-lose-it — the refreshing set is forfeited at
midnight, while bonus uses (chaos grants, perk 10) carry over — so a macro
started late in the day should spend as much as it can before the reset rather
than wait for it.

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
- **The budget belongs to one (account, channel) pair**, like every other daily
allowance, so nothing about it may be counted across scopes. `daily_resets.perk9`
is already stored that way, and the two reads that rebuild the Run panel from
`sphere_log` — `sync_perk9_clicks_from_log` for the counter and
`recent_perk9_click_colours` for the clicked row — filter on
`AccountState.run_channel_id` as well as the recording account. Counting the whole
log made a switch to a fresh server open part-way through a budget it had not
touched. Everything else the panel tracks per channel (spawns seen, spawns at the
last `$ohu9` sync, regular rolls, the pool line, the colour history) is dropped by
`AccountState.clear_perk9_channel_tracking()` on a switch; `perk9_hazard` is not,
because the learned rate describes the account's rolling, not the channel.
- **Dark and light pay out as another colour.** Dark prints
`<:spD:…> turns into <:spW:…>` and then pays on the next line under `spW`;
light prints `:spL: breaks down into :spB: + … => +312`. The sphere that was
clicked — the one that spent the perk-9 slot — is the **source**, so
`parse_sphere_click` takes `sphere_type` from the transform header and records
the outcome separately as `sphere_resolved`. Reading the payout line instead
made the Run panel and the sphere log claim a rainbow was clicked, and the two
disagreed depending on whether the newline survived. `SPHERE_TRANSFORM_EMOJIS`
in `mudae/constants.py` is the set that behaves this way; the same rule already
applied to `$oh` via `classify_oh_click`.



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
the gate (free, spends no slot).

In budget mode the bar **replaces** `types_allowed` rather than narrowing it,
and the Presets colour list is greyed out to say so. Filtering first is what
made clicks expire: a typical list omits `spB` and `spT`, five spawns in six,
so almost nothing the bar would have cleared at the end of the day ever
reached it. With the toggle off the static list is still the only gate.

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

#### How many spawns are still coming (`r`)

`$ohu9`'s `(Perk 9) Rolled today: 44/154` (`parse_perk9_rolled_pool`) gives a
hard ceiling — the pool cannot spawn a character twice — but it is *not* a
forecast: the tail of a pool is effectively unrollable, so `pool − rolled`
plateaus, never falls to `c`, and the "bar → 0 at the end of the day" promise
above never fires. Rolling samples the pool without replacement, so the arrival
rate decays as the pool empties:

```
rolled(k) = pool × (1 − e^{−h₀k/pool})
r         = (pool − rolled) × (1 − e^{−h₀ · rolls_left_today / pool})
h₀        = −(pool / k) × ln( (pool − rolled_to) / (pool − rolled_from) )
```

`h₀` is spawns per roll — what share of the account's roll space its perk-9
pool covers. It is **measured per account, never shipped as a constant**. One
account's logs fit 0.37, but that number moves with upgrades, pool size and how
popular the pooled characters are; an account with the same 154 characters and
a fifth of the reach sees ~23 spawns a day, and handing it 0.37 is barely
better than the bug. Until an account has measured its own rate the forecast
arm is simply absent and the pool ceiling applies exactly as before.

The rate is learned from stretches of ordinary rolling, bounded by `$ohu9`
replies and by `$us` rolls, and accumulated per calendar day
(`record_hazard_interval`), then averaged roll-weighted over the trailing
`PERK9_HAZARD_WINDOW_DAYS` (14) — "the last 2 weeks", so an upgrade is
reflected within about that long instead of lingering for months.

**`$us` rolls are excluded.** They spawn perk-9 buttons like any other roll,
but a drain can clear a large slice of the pool in half an hour, and counting
that as the account's normal pace would inflate the estimate for every later
day. A `$us` roll therefore ends the stretch being measured and the next one
starts from the post-drain `rolled`: the depletion it caused is respected, its
rolls are not counted. (Charging its characters to ordinary rolls instead would
roughly treble the rate — `scripts/perk9_bakeoff.py --with-us-burst`.)

`expected_daily_opportunities` still overrides everything when set. Without any
signal at all the context is `None` and the static filter applies.

`rolled` is day-scoped: the pool refills at the reset, so `rollover_perk9_if_needed`
clears it along with the click and spawn counters, and `rolled_synced_at` records
when `$ohu9` last read the line. That is deliberately **not** `updated_at` —
`$ohu` and `$ohu8` merge into the same record for the click counter and the
refill but carry no perk-9 roll line, and treating their stamp as freshness both
suppressed the `$ohu9` due after the reset and passed yesterday's count off as
today's.

#### The last hour (`PERK9_SPENDDOWN_MINUTES`)

Inside the last 60 minutes before the UTC reset the bar is forced to **0** and
any sphere is worth a leftover click, because a click saved past the reset is
worth nothing. This is deliberately independent of `h₀`, `r` and the value
table — it is the one guarantee that holds no matter how wrong the forecast is.

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
clicks). Extra `$ot` is counted in `$ohu` availability and play-all spends it
like any other minigame use.

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

The GUI fetches `$settings`, `$bonus`, and `$shop` onto a channel profile.
Parsers: `mudae/parsers/settings.py`, `bonus.py`, `shop.py` (catalog in
`bonus_catalog.py` / `shop_catalog.py`). Frozen dumps:
`tests/mudae_sheet_fixtures.py`.

**Where the fetch buttons are.** Each sheet is fetched from the scope bar of
the page that reads it — `$settings` and `$bonus` on Mudae, `$shop` and `$wl`
on Spheres — because the account/server pickers beside the button are what the
command is sent *as*. A fetch does not need the macro to be connected there,
or connected at all: `AppBridge.fetchForScope` hops or stands up a temporary
connection and puts the session back (see ARCHITECTURE.md → "Temporary
connections"). It refuses only while the macro is busy with something a sheet
is not worth interrupting. `App.fetchSettings` / `fetchBonus` / `fetchShop` /
`fetchMudaeWishlist` still exist and mean "for the Run pair".

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
Stored on the channel profile like `$bonus`, but **keyed by account id**
(`channel.shop_by_account`, `gui/sheet_store.py`) because both sheets describe
the connected account, not the server — storing one per channel let a second
account on the same channel overwrite the first's power max and perk-9 cap.
A sheet saved before that split is read back for the main account only and
flagged `inferred`. Read-only — do not send `$shoprefund`.


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



## Maintenance and outages

Mudae goes down for a reboot every so often. While it is down it answers
**every** command with the same text instead of the reply that was asked
for — `$tu`, `$wa`, `$oh`, anything:

```
Command under maintenance!
(For 3 minutes, reboot)
```

**It has to be recognised before the reply is paired with the command.**
`mudae/parsers/pipeline.parse_mudae_message` matches a Mudae message to the
command the macro just typed (`mudae.commands.resolve_command`) rather than
to the message's own shape, so without a check ahead of that a maintenance
reply to `$tu` was handed to `parse_tu` and came back as a valid-looking but
empty sheet. The hourly loop read "0 rolls, reset passed", sent `$tu` again,
and did that once every three seconds for the length of the outage. The
check is the first thing `parse_mudae_message` does, and
`mudae/parsers/maintenance.py` owns it (`MessageKind.MAINTENANCE`).

**The backoff is the macro's own, not Mudae's estimate.** The parenthesised
window is parsed and logged, but Mudae keeps printing "(For 3 minutes)"
well past three minutes, so it is advisory. `macro/maintenance.py` holds the
ladder — **5, then 10, then 30 minutes** — and once it is spent the macro
stops, on the grounds that three quarters of an hour is not a reboot. A
command that Mudae answers normally resets the ladder, so a second outage
later starts at five minutes again.

`MaintenanceWatch` lives on `DiscordActions`, which every Mudae message for
that account passes through (`feed`), so the outage is noticed whichever
command hit it and every command shares one ladder — an outage first seen on
`$ohu` and then on a roll keeps counting up instead of restarting.
`RollCycleEngine._maintenance_halt` is what waits: it returns `"retry"`
after the pause, `"stop"` when the ladder is spent or the user pressed Stop,
and `""` when there is no outage, so the caller's ordinary failure handling
still applies. It is checked wherever the loops used to stop outright — a
failed `$tu` and a failed roll, in both the hourly and the `$us` cycle.

## What the macro does not do (yet)

- External sniping of other people's rolls.
- Slash-command rolls.
- Multi-account concurrent connections (config supports it; runtime is
one Discord session — see Phase D in `ARCHITECTURE.md`).
- Driving claim / kakera / roll from parsed `$settings` / `$bonus` / `$shop`
(parsers are trusted for storage; power max and perk 9 cap are the
exceptions already wired).

