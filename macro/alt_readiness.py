"""Is an alt ready to act on its own? Its sheets decide.

**``$bonus`` is required.** It holds the alt's own click cost, power max and
``$dk`` cooldown (``macro/sheet_caps.py``). Without it the alt would be priced
with Mudae's defaults, and an alt has worse upgrades than the main, so a
guess could send it clicking kakera it cannot afford. An alt with no
``$bonus`` stored for the run channel takes no trigger at all; passing to the
main by hand still works.

**On the main's rolls an alt always pays full price.** Keys stay on a
character whoever owns it, but they are only *soulkeys* for the owner. Mudae's
"your characters with 10+ keys consume half the power" never applies to an
alt reacting on the main's characters, so its cost there is its ``$bonus``
base (30% at default), halved only by a chaos key or perk 8 on the roll.

**``$shop`` and ``$ov`` are checked, not required yet.** ``$shop`` holds the
perk-9 click cap an alt needs once it rolls for sphere buttons. ``$ov`` holds
display settings that decide what a parser can see on the alt's *own* rolls
(``docs/PARSED_FIELDS.md`` §A). The parsers are proven on the main's
settings, so each of those the alt has set differently is listed.
"""

from __future__ import annotations

from typing import Any

# $ov settings that change what the parsers see on a roll the alt makes.
# (key, label, why it matters) — docs/PARSED_FIELDS.md §A.
OV_ROLL_DISPLAY: tuple[tuple[str, str, str], ...] = (
    ("setfooter", "Footer informations for rolls ($setfooter)",
     "perk-8 mark, ownership and sphere value are read from the footer"),
    ("displaykeys", "Keys on characters you don't own ($displaykeys)",
     "changes the key line the roll parser reads"),
    ("toggleletters", "Letters next to kakera/sphere buttons ($toggleletters)",
     "changes what a button looks like to the button parser"),
    ("perstogglebutton", "Buttons under rolls ($perstogglebutton)",
     "decides claim by button or by reaction"),
    ("rollsleft", "Rolls left message ($rollsleft)",
     "where the rolls-left warning is printed"),
    ("wishdm", "Private wishes ($wishdm)",
     "hidden wishes leave the wish-ping claim path nothing to match"),
)


def _present(fields: dict[str, Any] | None) -> bool:
    return bool(fields) and any(v not in (None, "", [], {}) for k, v in fields.items() if k not in ("part", "parts"))


def bonus_is_usable(bonus: dict[str, Any] | None) -> bool:
    """The part of ``$bonus`` the alt's actions price with has been read."""
    bonus = bonus or {}
    return bonus.get("power_cost_per_kakera_button") is not None or bonus.get("kakera_max_power") is not None


def ov_differences(main_ov: dict[str, Any] | None, alt_ov: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Roll-display settings the alt has set differently from the main."""
    if not _present(main_ov) or not _present(alt_ov):
        return []
    out = []
    for key, label, why in OV_ROLL_DISPLAY:
        main_value, alt_value = (main_ov or {}).get(key), (alt_ov or {}).get(key)
        if main_value is None or alt_value is None or main_value == alt_value:
            continue
        out.append({"key": key, "label": label, "main": main_value, "alt": alt_value, "why": why})
    return out


def alt_readiness(
    *,
    bonus: dict[str, Any] | None,
    shop: dict[str, Any] | None,
    ov: dict[str, Any] | None,
    main_ov: dict[str, Any] | None,
) -> dict[str, Any]:
    """``ready`` gates every automatic action; ``notes`` are advice only."""
    blocking: list[str] = []
    notes: list[str] = []
    if not bonus_is_usable(bonus):
        blocking.append("$bonus not read for this server — the alt is not used until it is")
    if not _present(shop):
        notes.append("$shop not read — needed once the alt rolls for sphere buttons")
    if not _present(ov):
        notes.append("$ov not read — can't check its roll display settings")
    elif not _present(main_ov):
        notes.append("the main's $ov isn't read — nothing to compare the alt's against")
    diffs = ov_differences(main_ov, ov)
    if diffs:
        notes.append(f"{len(diffs)} roll display setting(s) differ from the main")
    return {"ready": not blocking, "blocking": blocking, "notes": notes, "ov_diffs": diffs}
