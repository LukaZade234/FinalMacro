"""Force-divorce farming: the policy half.

Emerald IV pays a character's own kakera value every time it is claimed, and a
character's value grows with the keys on it. So divorcing the single most
valuable character in the harem and claiming it again banks that value, over and
over. ``$forcedivorce`` is used rather than ``$divorce`` because it does not
strip 5% of the character's keys — which is also why the whole method needs
server admin.

What makes this delicate is not the earning, it is the exposure. Between the
divorce and the re-claim the character belongs to **nobody**, and it is by
definition the most valuable character on the server. Two invariants follow, and
everything else here exists to serve them:

* **Never divorce without a claim slot already in hand.** A divorce with no way
  to claim leaves the character sitting unowned for up to an hour. The check is
  ``claim_available`` *or* an unspent ``$rt`` — which is also why the ``$rt``
  re-cycle needs no branch of its own: a reset in hand simply *is* a slot.
* **Claim nothing else, all day.** One slot per reset has to go to the target,
  so wishes, series wishes and the end-of-batch best pick are all refused while
  a session is live. :meth:`ForceDivorceSession.allows_claim` is the gate every
  claim path consults.

This module holds no I/O. The engine drives it, and the exchange with Mudae
(``$forcedivorce`` → prompt → ``y`` → result) lives in ``macro/roll_cycle.py``,
so this half stays testable without a Discord connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro.wishlist import normalize_wishlist_name

# A claim slot bought with ``$rt`` still needs rolls to find the character
# again, so a reset is only worth spending when there is time to hunt with it.
# Under this, the free slot at the next claim reset arrives sooner than the
# hunt would finish, and holding the ``$rt`` for the next cycle is strictly
# better than burning it now.
RT_MIN_MINUTES_BEFORE_RESET = 30

# Phases, in the order one cycle runs through them.
IDLE = "idle"          # armed, waiting for a claim slot
DIVORCING = "divorcing"  # $forcedivorce sent, prompt not yet confirmed
HUNTING = "hunting"    # divorced and unowned — every roll is looking for it
CLAIMED = "claimed"    # banked; waiting for the next slot to come round
STOPPED = "stopped"    # aborted, reason on ``stop_reason``


# Where the across-restart record lives in the account's daily blob.
FORCE_DIVORCE_KEY = "force_divorce"


@dataclass
class ForceDivorceRecord:
    """What survives a restart: which character, and whether we still own it.

    Without this, a macro that divorced a character and was stopped before
    claiming it back would, on the next start, read ``$mmk=``, see a *different*
    name at the top (the real target is not in the harem — that is what being
    divorced means) and divorce that one too. Two of the account's most valuable
    characters would then be sitting unowned instead of one.
    """

    target: str = ""
    # False means "divorced and not claimed back" — i.e. still out there.
    owned: bool = True
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ForceDivorceRecord:
        if not isinstance(data, dict):
            return cls()
        return cls(
            target=str(data.get("target") or "").strip(),
            owned=bool(data.get("owned", True)),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "owned": self.owned,
            "updated_at": self.updated_at,
        }

    @property
    def outstanding(self) -> bool:
        """A character we divorced and never claimed back."""
        return bool(self.target) and not self.owned


def load_force_divorce_record(daily_resets: dict[str, Any] | None) -> ForceDivorceRecord:
    if not daily_resets:
        return ForceDivorceRecord()
    return ForceDivorceRecord.from_dict(daily_resets.get(FORCE_DIVORCE_KEY))


def save_force_divorce_record(
    daily_resets: dict[str, Any],
    record: ForceDivorceRecord,
) -> dict[str, Any]:
    updated = dict(daily_resets or {})
    updated[FORCE_DIVORCE_KEY] = record.to_dict()
    return updated


def harem_holds(fields: dict[str, Any], name: str) -> bool:
    """Whether a ``$mmk=`` page still lists ``name``.

    The target is by definition the most valuable character owned, so if it is
    owned it is on page 1. Absent from page 1 therefore means it is not owned —
    which, for a character this account divorced itself, means it is still out
    there waiting to be claimed back.
    """
    key = normalize_wishlist_name(name)
    if not key:
        return False
    for entry in (fields or {}).get("entries") or []:
        if normalize_wishlist_name(str(entry.get("name") or "")) == key:
            return True
    return False


@dataclass
class ForceDivorceTarget:
    """The character being farmed, as read from ``$mmk=``."""

    name: str
    kakera: int = 0
    # UTC date key of the ``$mmk=`` that chose it. The ordering does not move
    # meaningfully within a day, so one fetch a day is enough.
    day: str = ""

    @property
    def key(self) -> str:
        return normalize_wishlist_name(self.name)


@dataclass
class ForceDivorceSession:
    """Live state of one force-divorce farming run."""

    phase: str = IDLE
    target: ForceDivorceTarget | None = None
    cycles: int = 0
    kakera_banked: int = 0
    spheres_banked: int = 0
    stop_reason: str = ""
    # Set while the divorce is unconfirmed, so a lost reply can be resolved by
    # re-reading the harem rather than guessed at.
    pending_character: str = ""
    notes: list[str] = field(default_factory=list)

    # --- target ------------------------------------------------------------

    def needs_target(self, day: str) -> bool:
        """True when ``$mmk=`` should be (re-)read for this UTC day."""
        if self.target is None:
            return True
        return bool(day) and self.target.day != day

    def set_target(self, name: str, kakera: int = 0, *, day: str = "") -> None:
        self.target = ForceDivorceTarget(name=str(name).strip(), kakera=int(kakera or 0), day=day)

    def is_target(self, character_name: Any) -> bool:
        if self.target is None:
            return False
        return normalize_wishlist_name(str(character_name or "")) == self.target.key

    # --- the claim gate ----------------------------------------------------

    def allows_claim(self, character_name: Any) -> bool:
        """Whether *any* claim path may spend the slot on this character.

        Only the target, and only while a session is running. This is
        deliberately blunt: a wish ping, an app-wishlist match and the
        end-of-batch highest-kakera pick are all worth less than the slot they
        would spend, because the slot is what the farm runs on.
        """
        if self.phase == STOPPED:
            return True  # session over — normal claim rules apply again
        return self.is_target(character_name)

    @property
    def active(self) -> bool:
        return self.phase != STOPPED

    # --- the divorce gate --------------------------------------------------

    def can_divorce(
        self,
        state: Any,
        *,
        allow_rt: bool = True,
        rt_min_minutes: int = RT_MIN_MINUTES_BEFORE_RESET,
    ) -> tuple[bool, str]:
        """Whether to force-divorce right now, and why not when the answer is no.

        The claim slot is checked *before* the divorce, never after: the
        character is exposed the moment it is divorced, and a slot that is not
        already in hand may not arrive for an hour.

        An unspent ``$rt`` counts as a slot — that is what lets a cycle start
        again the moment the last one banks — but only with ``rt_min_minutes``
        left before the claim reset, since a reset bought with no time to
        re-roll the character is a reset wasted.
        """
        if self.phase == STOPPED:
            return False, "session stopped"
        if self.target is None:
            return False, "no target chosen yet"
        if self.phase in {DIVORCING, HUNTING}:
            return False, f"{self.target.name} is already divorced and unclaimed"
        if getattr(state, "claim_available", None) is True:
            return True, ""
        if allow_rt and getattr(state, "rt_available", None) is True:
            left = getattr(state, "next_claim_reset_minutes", None)
            if left is not None and int(left) < int(rt_min_minutes):
                return False, (
                    f"$rt is available but the claim reset is {int(left)}m away "
                    f"(under {int(rt_min_minutes)}m) — saving it for the next cycle"
                )
            return True, ""
        return False, "no claim slot and no $rt — would leave the character exposed"

    # --- transitions -------------------------------------------------------

    def begin_divorce(self) -> None:
        self.phase = DIVORCING
        self.pending_character = self.target.name if self.target else ""

    def note_divorced(self) -> None:
        self.phase = HUNTING
        self.pending_character = ""

    def note_divorce_failed(self) -> None:
        """Back to waiting: nothing was divorced, so nothing is exposed."""
        self.phase = IDLE
        self.pending_character = ""

    def note_claimed(self, *, kakera: int = 0, spheres: int = 0) -> None:
        self.phase = CLAIMED
        self.cycles += 1
        self.kakera_banked += max(0, int(kakera or 0))
        self.spheres_banked += max(0, int(spheres or 0))

    def ready_for_next_cycle(self) -> None:
        if self.phase == CLAIMED:
            self.phase = IDLE

    def stop(self, reason: str) -> None:
        self.phase = STOPPED
        self.stop_reason = str(reason or "stopped")

    # --- reporting ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "target": self.target.name if self.target else "",
            "target_kakera": self.target.kakera if self.target else 0,
            "cycles": self.cycles,
            "kakera": self.kakera_banked,
            "spheres": self.spheres_banked,
            "stop_reason": self.stop_reason,
        }


def target_from_harem(fields: dict[str, Any]) -> tuple[str, int] | None:
    """Top row of a ``$mmk=`` page — the most valuable character owned.

    ``$mmk=`` sorts by kakera value descending, so row 0 of page 1 is the
    answer and no paging is needed.
    """
    name = (fields or {}).get("top_name")
    if not name:
        return None
    try:
        kakera = int((fields or {}).get("top_kakera") or 0)
    except (TypeError, ValueError):
        kakera = 0
    return str(name), kakera
