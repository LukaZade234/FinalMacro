"""Which preset settings belong to each account, and which only the main decides.

With alts in the channel, a preset is no longer "the settings for the run".
Each field is one of three kinds:

``ACCOUNT``
    How *this* account rolls and reacts: its roll command, what it claims,
    which kakera and sphere buttons it clicks, its own ``$kl``. An alt with a
    preset of its own uses that preset's value; an alt without one inherits the
    main's.

``SESSION``
    How the *session* behaves, which every account follows together: the
    server's prefix, the roll pacing (all accounts share one channel and one
    command lane), the claim window, notification-mode disconnects, and the
    force-divorce farm, whose cycle the main owns and alts only take turns in.
    Always the main's value.

``MAIN_ONLY``
    Things only the main ever does. ``$us`` rolls are the main's alone: when
    the main runs out of rolls it switches to ``$us``, and alts never do. An
    alt's copy has these switched off, so no alt code path can start them.

Every ``MacroConfig`` field must be in exactly one set; the test suite fails
on a field that is not, so a new setting cannot slip through unclassified.
"""

from __future__ import annotations

import copy
import dataclasses

from macro.config import MacroConfig, UsRollKakeraRules

ACCOUNT: frozenset[str] = frozenset(
    {
        "roll_command",
        "character_claim",
        "kakera_reaction",
        "sphere_reaction",
        "kakera_loot",
    }
)

SESSION: frozenset[str] = frozenset(
    {
        "prefix",
        "roll_delay_sec",
        "humanize_roll_delay",
        "roll_delay_jitter_sec",
        "claim_expire_sec",
        "notification_mode",
        "force_divorce",
    }
)

MAIN_ONLY: frozenset[str] = frozenset(
    {
        "us_batch_size",
        "us_reset_margin_minutes",
        "us_read_before_add_delay_sec",
        "us_add_delay_sec",
        "us_roll_timeout_retry_sec",
        "us_keep_draining",
        "us_stop_on_power_exhausted",
        "us_stop_on_key_limit",
        "us_stop_after_rolls_enabled",
        "us_stop_after_rolls",
        "us_schedule_enabled",
        "us_schedule_start",
        "us_schedule_end",
        "us_roll_kakera",
    }
)


def scope_of(field_name: str) -> str:
    if field_name in ACCOUNT:
        return "account"
    if field_name in SESSION:
        return "session"
    if field_name in MAIN_ONLY:
        return "main_only"
    raise KeyError(f"MacroConfig.{field_name} has no preset scope — add it to macro/preset_scope.py")


def unclassified_fields() -> list[str]:
    """Fields of ``MacroConfig`` missing from every scope (should be empty)."""
    names = [f.name for f in dataclasses.fields(MacroConfig)]
    return [name for name in names if name not in ACCOUNT | SESSION | MAIN_ONLY]


def alt_config(main: MacroConfig, own: MacroConfig | None = None) -> MacroConfig:
    """The settings an alt runs with.

    ``own`` is the alt's own preset, or ``None`` when only the main has one.
    ACCOUNT fields come from ``own`` when given (else the main's), SESSION
    fields always from the main, and MAIN_ONLY fields are switched off.
    """
    source = own if own is not None else main
    values: dict[str, object] = {}
    for f in dataclasses.fields(MacroConfig):
        kind = scope_of(f.name)
        if kind == "account":
            values[f.name] = copy.deepcopy(getattr(source, f.name))
        elif kind == "session":
            values[f.name] = copy.deepcopy(getattr(main, f.name))
    config = MacroConfig(**values)  # MAIN_ONLY fields keep their defaults…
    # …and the ones that could start $us on their own are pinned off.
    config.us_schedule_enabled = False
    config.us_keep_draining = False
    config.us_roll_kakera = UsRollKakeraRules()
    return config
