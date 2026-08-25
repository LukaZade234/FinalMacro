"""Frozen ``$settings`` / ``$bonus`` / ``$shop`` dumps for parser tests.

Key Server 0 ``$settings`` matches a live Premium-3 GM2 capture. Key Server -1
``$settings`` is reconstructed from a stored channel profile (same command
labels Mudae prints). ``$bonus`` part 1 is a live dump; part 2 is reconstructed
from a stored Key Server -1 parse plus typical Mudae wording for the
reaction-power / rolls sheet (including the twice-sphere line).

``$shop`` dumps are live copy-paste of three accounts (all LVL 0, mixed, and
MAX perk 5/9). Discord chrome (``Mudae`` / ``APP`` / timestamp / ``avatar``
thumbnail) is stripped; the body is what Components V2 TextDisplay carries.

These are description sheets. ``($bk)`` / ``($kt)`` / ``($shop)`` on ``$bonus``
are source tags, not commands to send. ``$shop`` itself is read-only here —
do not send ``$shoprefund``.
"""

# Live Key Server 0 dump (Premium 3, game mode 2, 21 rolls/h).
SETTINGS_REPLY = (
    "\U0001f6e0\ufe0f __**Server Settings**__ \U0001f6e0\ufe0f\n"
    "\U0001f31f\U0001f31f\U0001f31f Server Premium 3 \U0001f31f\U0001f31f\U0001f31f\n\n"
    "\u00b7 Prefix: **$** ($prefix)\n"
    "\u00b7 Lang: **en** ($lang)\n"
    "\u00b7 Claim reset: every **60** min. ($setclaim)\n"
    "\u00b7 Exact minute of the reset: xx:**00** ($setinterval)\n"
    "\u00b7 Reset shifted: by +**0** min. ($shifthour)\n"
    "\u00b7 Rolls per hour: **21** ($setrolls)\n"
    "\u00b7 Time before the claim reaction expires: **45** sec. ($settimer)\n"
    "\u00b7 Spawn rarity multiplier for already claimed characters: **10** ($setrare)\n"
    "\u00b7 % kakera bonus: **+100** ($setkakerabonus)\n"
    "\u00b7 % sphere bonus: **+100** ($setspherebonus)\n"
    "\u00b7 Game mode: **2** ($gamemode)\n"
    "\u00b7 $servlimroul = 7,000 $wa, 7,000 $ha, 5,000 $wg, 5,000 $hg\n"
    "\u00b7 This channel instance: **1** ($channelinstance)\n"
    "\u00b7 Slash commands: enabled ($toggleslash)\n\n"
    "\u00b7 Ranking: enabled ($toggleclaimrank/$togglelikerank)\n"
    "\u00b7 Ranks displayed during rolls: claims and likes ($togglerolls)\n"
    "\u00b7 NSFW series: enabled ($togglensfw)\n"
    "\u00b7 Disturbing imagery series: enabled ($toggledisturbing)\n"
    "\u00b7 Child characters: enabled ($togglechildtag)\n"
    "\u00b7 Rolls sniping: 0 ($togglesnipe)\n"
    "\u00b7 Kakera sniping: 0 ($togglekakerasnipe)\n"
    "\u00b7 Limit of characters per collection: **12,000** ($haremlimit)\n"
    "\u00b7 $haremcopy/$kakeracopy/$soulcopy limit: ****disabled**** ($removecopylimit)\n"
    "\u00b7 Claim buttons: ****for all your rolls**** ($togglebutton)\n"
    "\u00b7 Custom buttons: no ($claimreact)\n"
    "\u00b7 Kakera buttons more recognizable: no ($kakerabutton switchset)\n"
    "\u00b7 Sphere buttons more recognizable: no ($spherebutton switchset)\n\n"
    "\u00b7 Kakera trading: enabled ($togglekakeratrade)\n"
    "\u00b7 Kakera calculation: claim and like ranks (and number of claimed characters) "
    "($togglekakeraclaim/$togglekakeralike)\n"
    "\u00b7 Kakera value displayed during rolls: enabled ($togglekakerarolls)\n"
    "\u00b7 $kakeraloots & $ouroperks wishprotect: enabled ($togglewishprotect)\n"
    "\u00b7 $ouroshop freewish: enabled ($togglewishfree)\n"
    "\u00b7 Spheres trading: enabled ($togglespheretrade)"
)

# Same command set, game mode 1 (no $servlimroul), plain text (no markdown).
SETTINGS_GM1_PLAIN = (
    "\U0001f6e0\ufe0f Server Settings \U0001f6e0\ufe0f\n"
    "\U0001f31f\U0001f31f\U0001f31f Server Premium 3 \U0001f31f\U0001f31f\U0001f31f\n\n"
    "\u00b7 Prefix: $ ($prefix)\n"
    "\u00b7 Lang: en ($lang)\n"
    "\u00b7 Claim reset: every 60 min. ($setclaim)\n"
    "\u00b7 Exact minute of the reset: xx:00 ($setinterval)\n"
    "\u00b7 Reset shifted: by +0 min. ($shifthour)\n"
    "\u00b7 Rolls per hour: 21 ($setrolls)\n"
    "\u00b7 Time before the claim reaction expires: 45 sec. ($settimer)\n"
    "\u00b7 Spawn rarity multiplier for already claimed characters: 10 ($setrare)\n"
    "\u00b7 % kakera bonus: +100 ($setkakerabonus)\n"
    "\u00b7 % sphere bonus: +100 ($setspherebonus)\n"
    "\u00b7 Game mode: 1 ($gamemode)\n"
    "\u00b7 This channel instance: 1 ($channelinstance)\n"
    "\u00b7 Slash commands: enabled ($toggleslash)\n\n"
    "\u00b7 Ranking: enabled ($toggleclaimrank/$togglelikerank)\n"
    "\u00b7 Ranks displayed during rolls: claims and likes ($togglerolls)\n"
    "\u00b7 NSFW series: enabled ($togglensfw)\n"
    "\u00b7 Disturbing imagery series: enabled ($toggledisturbing)\n"
    "\u00b7 Child characters: enabled ($togglechildtag)\n"
    "\u00b7 Rolls sniping: 0 ($togglesnipe)\n"
    "\u00b7 Kakera sniping: 0 ($togglekakerasnipe)\n"
    "\u00b7 Limit of characters per collection: 12,000 ($haremlimit)\n"
    "\u00b7 $haremcopy/$kakeracopy/$soulcopy limit: disabled ($removecopylimit)\n"
    "\u00b7 Claim buttons: for all your rolls ($togglebutton)\n"
    "\u00b7 Custom buttons: no ($claimreact)\n"
    "\u00b7 Kakera buttons more recognizable: no ($kakerabutton switchset)\n"
    "\u00b7 Sphere buttons more recognizable: no ($spherebutton switchset)\n\n"
    "\u00b7 Kakera trading: enabled ($togglekakeratrade)\n"
    "\u00b7 Kakera calculation: claim and like ranks (and number of claimed characters) "
    "($togglekakeraclaim/$togglekakeralike)\n"
    "\u00b7 Kakera value displayed during rolls: enabled ($togglekakerarolls)\n"
    "\u00b7 $kakeraloots & $ouroperks wishprotect: enabled ($togglewishprotect)\n"
    "\u00b7 $ouroshop freewish: enabled ($togglewishfree)\n"
    "\u00b7 Spheres trading: enabled ($togglespheretrade)"
)

# Key Server -1 profile: 180 min claim, 8 rolls/h, public-wish buttons, no
# ranks on rolls. Reconstructed from stored channel.settings values.
SETTINGS_KS1_REPLY = (
    "\U0001f6e0\ufe0f Server Settings \U0001f6e0\ufe0f\n\n"
    "\u00b7 Prefix: $ ($prefix)\n"
    "\u00b7 Lang: en ($lang)\n"
    "\u00b7 Claim reset: every 180 min. ($setclaim)\n"
    "\u00b7 Exact minute of the reset: xx:41 ($setinterval)\n"
    "\u00b7 Reset shifted: by +0 min. ($shifthour)\n"
    "\u00b7 Rolls per hour: 8 ($setrolls)\n"
    "\u00b7 Time before the claim reaction expires: 45 sec. ($settimer)\n"
    "\u00b7 Spawn rarity multiplier for already claimed characters: 2 ($setrare)\n"
    "\u00b7 % kakera bonus: +0 ($setkakerabonus)\n"
    "\u00b7 % sphere bonus: +0 ($setspherebonus)\n"
    "\u00b7 Game mode: 2 ($gamemode)\n"
    "\u00b7 $servlimroul = 47,560 $wa, 48,912 $ha, 35,615 $wg, 30,906 $hg\n"
    "\u00b7 This channel instance: 1 ($channelinstance)\n"
    "\u00b7 Slash commands: enabled ($toggleslash)\n\n"
    "\u00b7 Ranking: enabled ($toggleclaimrank/$togglelikerank)\n"
    "\u00b7 Ranks displayed during rolls: no ($togglerolls)\n"
    "\u00b7 NSFW series: enabled ($togglensfw)\n"
    "\u00b7 Disturbing imagery series: enabled ($toggledisturbing)\n"
    "\u00b7 Child characters: enabled ($togglechildtag)\n"
    "\u00b7 Rolls sniping: 0 ($togglesnipe)\n"
    "\u00b7 Kakera sniping: 0 ($togglekakerasnipe)\n"
    "\u00b7 Limit of characters per collection: 12,000 ($haremlimit)\n"
    "\u00b7 $haremcopy/$kakeracopy/$soulcopy limit: disabled ($removecopylimit)\n"
    "\u00b7 Claim buttons: for public wishes only ($togglebutton)\n"
    "\u00b7 Custom buttons: no ($claimreact)\n"
    "\u00b7 Kakera buttons more recognizable: no ($kakerabutton switchset)\n"
    "\u00b7 Sphere buttons more recognizable: no ($spherebutton switchset)\n\n"
    "\u00b7 Kakera trading: enabled ($togglekakeratrade)\n"
    "\u00b7 Kakera calculation: claim and like ranks (and number of claimed characters) "
    "($togglekakeraclaim/$togglekakeralike)\n"
    "\u00b7 Kakera value displayed during rolls: disabled ($togglekakerarolls)\n"
    "\u00b7 $kakeraloots & $ouroperks wishprotect: enabled ($togglewishprotect)\n"
    "\u00b7 $ouroshop freewish: enabled ($togglewishfree)\n"
    "\u00b7 Spheres trading: enabled ($togglespheretrade)"
)

# Live Key Server 0 $bonus 1/2 (player sheet) from data/parsingdebug.json.
BONUS_REPLY_PART1 = (
    "**__Player Bonuses__**\n\n"
    "<:addroll:633217436044492801> \u00b7 Rolls per hour: **+121** (6 $k + 95 $kl + 10 $kt + 10 premium) **-40** ($bw) **-40** ($bk)\n"
    "<:wlslot:633217442151137280> \u00b7 Wishlist slots: **+207** (6 $k + 145 $kl + 26 $kt + 23 premium + 7 server premium 3) **-56** ($sw)\n"
    "<:wlslot:633217442151137280> \u00b7 Wishseries slots: **10** (premium)\n"
    "<:wlslot:633217442151137280> \u00b7 Spawn bonus for wishes: **+650%** ($k + $bw + slash)\n"
    "<:sw:1163913219782492220> \u00b7 Additional % spawn bonus for $starwish: **+665%** ($kt + $bw + $tuto) (= 1,315%)\n"
    "<:sw:1163913219782492220> \u00b7 Starwish slots:  **+15** (8 $kl + 7 $sw)\n"
    "<:wishprotect:633217581725122570> \u00b7 Wishprotect spawn chance: **1/499** ($kl)\n"
    "<:rtcd:633217436992143361> \u00b7 Cooldown for $rt: **5h** (-30h $k -15h $kl)\n"
    "<:disablemore:633217511218872329> \u00b7 $limroul animanga limits: **-10,501** $wa/$ha (7,701 $kl + 1,400 $kt + 1,400 premium)\n"
    "<:disablemore:633217511218872329> \u00b7 $limroul game limits: **-7,114** $wg/$hg (5,134 $kl + 980 $kt + 1,000 premium)\n"
    "<:BronzeIV:605042879039012900> \u00b7 Bronze IV & Silver IV kakera: **+90%** ($kt)\n"
    "<:morekakera:633217512057864192> \u00b7 Bonus for kakera earned: **+15%** (premium + slash) **+100%** (server premium 3)\n"
    "<:morekakera:633217512057864192> \u00b7 Kakera gold keys bonus: **12,360** (5,800 $kt, 2,060 $bk)\n"
    "<:morekakera:633217512057864192> \u00b7 Cooldown for $dk: **10h** (-10h premium)\n"
    "<:morekakera:633217512057864192> \u00b7 $mk per hour: **+2** (premium)\n"
    "<:morekakera:633217512057864192> \u00b7 Kakera max power: **175%** ($kt)\n"
    "<:morekakera:633217512057864192> \u00b7 Power cost per kakera button: **30%** (-60% $k -10% $kt)"
)

# Live Key Server 0 $bonus 2/2 (kakera / sphere sheet) from data/parsingdebug.json.
BONUS_REPLY_PART2 = (
    "<:morekakera:633217512057864192> \u00b7 Additional bonus for kakera buttons: **+65%** ($bk)\n"
    "<:morekakera:633217512057864192> \u00b7 Additional bonus for kakera buttons on starwishes: **+64%** ($sw)\n"
    "<:kakeraL:815961697918779422> \u00b7 Random kakera per light kakera: **13-14** (10 $kt)\n"
    "<:kakeraR:605112980295647242> \u00b7 Additional kakera on the final value of red and rainbow: **2250** ($kt)\n"
    "<:kakeraC:1441097472587075758> \u00b7 Additional kakera on the initial value of chaos: **1329** ($kt)\n"
    "<:kakeraC:1441097472587075758> \u00b7 Rarity of each reward from chaos kakera decreased: chances **1.03x** ($kt)\n"
    "<:bku:1163913181920497755> \u00b7 Chance to complete + reset $bku on $sw: **+476%** ($kl) (this interval: 486%)\n"
    "<:chaoskey:690110264166842421> \u00b7 Chance to get an additional key on wishes: **+76%** ($kt)\n"
    "<:sp:1437140700604137554> \u00b7 Chance to get twice the sphere button value: **2.5%** ($kt)\n"
    "<:sp:1437140700604137554> \u00b7 Additional sphere sources: claims = **44**, $dk = **44**, Bronze IV = **34**, $rolls = **24** ($kt)\n"
    "<:sp:1437140700604137554> \u00b7 Additional spheres: **+18** (spheres clicked + premium)\n"
    "<:sp:1437140700604137554> \u00b7 $oh daily bonus: **+2,800** spheres, **150%** to get 1 $oq ($op) and **32%** $ot ($shop)\n"
    "<:spM:1473308463441379428> \u00b7 Megaspheres: **15** rewards and **16**% chance to be free ($shop)"
)

# Live $shop sheets (Components V2 TextDisplay body; three upgrade mixes).
SHOP_REPLY_LVL0 = (
    "Upgrade bonuses given by ouroperks. These bonuses are applied to ALL characters. "
    "Use $shoprefund to refund spheres. Type $oo for fragments.\n"
    "Each bonus has 10 levels (cost increased by +4,000 per level).\n"
    "You have 13,549 :sp:\n"
    "[LVL 0]  A part of the spawn chance bonus applied by perk 1 is also applied to the character upgraded. Part: 0% > 10%\n"
    "[LVL 0]  A megasphere has 1/50 to appear when you roll any of your claimed characters. 1 megasphere per day (increased with perk 2, see $s megasphere). Number of rewards per megasphere: 0 > 3\n"
    "[LVL 0]  The additional kakera button spawned by perk 3 has a chance to never include blue kakera (or yellow if Sapphire IV): 0% > 10%\n"
    "[LVL 0]  When you get a key thanks to perk 4, there is a chance to get an Omega key. These keys can be added to any character of your collection (see $ok). Chance: 0% > 5%\n"
    "[LVL 0]  When a kakera button gives spheres thanks to perk 5, there is a slight chance to get +1 $ot. Chance for each sphere earned (multiplied by the number of spheres given by the perk 5 level, the value displayed with $op): 0% > 0.014%\n"
    "[LVL 0]  The wish spawned from perk 6 has a chance to be an unclaimed wish from your wishlist if there is any. This claim is free and indicated with a green background (limited to one time per day). Chance: 0% > 1%\n"
    "Claimed wishes that you own spawned from perk 6 have a chance to give +1 Omega key: 0% > 50%\n"
    "[LVL 0]  All chaos kakera spawned by perk 7 have a chance to give double rewards (except for special character spawns and discount), indicated with a blue background: 0% > 2%\n"
    "[LVL 0]  On characters fully upgraded, the kakera buttons of perk 8 give more kakera. Boost (additive with $bk): 0% > 5%\n"
    "[LVL 0]  More sphere buttons spawned by perk 9 can be clicked per day: +0 > +1\n"
    "Spheres clicked from perk 9 give more spheres: 0% > 10%\n"
    "[LVL 0]  The first $oh of the day has a chance to give 1 $ot for each character you have fully upgraded (120 characters max): +0% > +0.25%"
)

SHOP_REPLY_MIXED = (
    "Upgrade bonuses given by ouroperks. These bonuses are applied to ALL characters. "
    "Use $shoprefund to refund spheres. Type $oo for fragments.\n"
    "Each bonus has 10 levels (cost increased by +4,000 per level).\n"
    "You have 15,660 :sp:\n"
    "[LVL 5]  A part of the spawn chance bonus applied by perk 1 is also applied to the character upgraded. Part: 50% > 60%\n"
    "[LVL 5]  A megasphere has 1/50 to appear when you roll any of your claimed characters. 1 megasphere per day (increased with perk 2, see $s megasphere). Number of rewards per megasphere: 15 > 18\n"
    "[LVL 0]  The additional kakera button spawned by perk 3 has a chance to never include blue kakera (or yellow if Sapphire IV): 0% > 10%\n"
    "[LVL 5]  When you get a key thanks to perk 4, there is a chance to get an Omega key. These keys can be added to any character of your collection (see $ok). Chance: 25% > 30%\n"
    "[MAX]  When a kakera button gives spheres thanks to perk 5, there is a slight chance to get +1 $ot. Chance for each sphere earned (multiplied by the number of spheres given by the perk 5 level, the value displayed with $op): 0.14%\n"
    "[LVL 5]  The wish spawned from perk 6 has a chance to be an unclaimed wish from your wishlist if there is any. This claim is free and indicated with a green background (limited to one time per day). Chance: 5% > 6%\n"
    "Claimed wishes that you own spawned from perk 6 have a chance to give +1 Omega key: 250% > 300%\n"
    "[LVL 0]  All chaos kakera spawned by perk 7 have a chance to give double rewards (except for special character spawns and discount), indicated with a blue background: 0% > 2%\n"
    "[LVL 6]  On characters fully upgraded, the kakera buttons of perk 8 give more kakera. Boost (additive with $bk): 30% > 35%\n"
    "[MAX]  More sphere buttons spawned by perk 9 can be clicked per day: +10\n"
    "Spheres clicked from perk 9 give more spheres: 100%\n"
    "[LVL 8]  The first $oh of the day has a chance to give 1 $ot for each character you have fully upgraded (120 characters max): +2% > +2.25%"
)

SHOP_REPLY_MID = (
    "Upgrade bonuses given by ouroperks. These bonuses are applied to ALL characters. "
    "Use $shoprefund to refund spheres. Type $oo for fragments.\n"
    "Each bonus has 10 levels (cost increased by +4,000 per level).\n"
    "You have 55,613 :sp:\n"
    "[LVL 5]  A part of the spawn chance bonus applied by perk 1 is also applied to the character upgraded. Part: 50% > 60%\n"
    "[LVL 5]  A megasphere has 1/50 to appear when you roll any of your claimed characters. 1 megasphere per day (increased with perk 2, see $s megasphere). Number of rewards per megasphere: 15 > 18\n"
    "[LVL 0]  The additional kakera button spawned by perk 3 has a chance to never include blue kakera (or yellow if Sapphire IV): 0% > 10%\n"
    "[LVL 5]  When you get a key thanks to perk 4, there is a chance to get an Omega key. These keys can be added to any character of your collection (see $ok). Chance: 25% > 30%\n"
    "[LVL 1]  When a kakera button gives spheres thanks to perk 5, there is a slight chance to get +1 $ot. Chance for each sphere earned (multiplied by the number of spheres given by the perk 5 level, the value displayed with $op): 0.014% > 0.028%\n"
    "[LVL 5]  The wish spawned from perk 6 has a chance to be an unclaimed wish from your wishlist if there is any. This claim is free and indicated with a green background (limited to one time per day). Chance: 5% > 6%\n"
    "Claimed wishes that you own spawned from perk 6 have a chance to give +1 Omega key: 250% > 300%\n"
    "[LVL 0]  All chaos kakera spawned by perk 7 have a chance to give double rewards (except for special character spawns and discount), indicated with a blue background: 0% > 2%\n"
    "[LVL 3]  On characters fully upgraded, the kakera buttons of perk 8 give more kakera. Boost (additive with $bk): 15% > 20%\n"
    "[LVL 5]  More sphere buttons spawned by perk 9 can be clicked per day: +5 > +6\n"
    "Spheres clicked from perk 9 give more spheres: 50% > 60%\n"
    "[LVL 0]  The first $oh of the day has a chance to give 1 $ot for each character you have fully upgraded (120 characters max): +0% > +0.25%"
)
