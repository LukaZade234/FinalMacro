"""Post-roll claim: pick highest kakera value after all rolls finish."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mudae.account_context import username_matches_own
from mudae.buttons import claim_method_from_buttons, is_claim_button
from mudae.constants import CLAIM_REACTION_EMOJI
from mudae.types import MessageKind

from macro.actions import DiscordActions
from macro.config import MacroConfig
from macro.rt_manager import apply_rt_response, has_rt_available
from macro.rule_eval import passes_character_claim
from macro.state import AccountState


_RT_PAUSE_BEFORE_SEC = 1.0
_RT_TICK_TIMEOUT_SEC = 8.0
# Enough spacing that the claim does not land in the same instant as the reset,
# which Mudae can answer as though the reset had not happened. Deliberately
# short: this is paid on *every* $rt, including the ones that were going to work,
# and it comes straight out of a claim window that is only ~45s wide. If the
# claim does not land, the escalating retry ladder below is what handles it —
# that cost is only paid when something actually went wrong.
_RT_SETTLE_AFTER_TICK_SEC = 1.0
# The tick is the only thing Mudae sends, so a lost one leaves no evidence at
# all. ``$tu`` is the one thing that can still say whether the reset landed;
# asking costs a command and recovers both the reset and the claim, where giving
# up throws away a scarce daily token. Kept short so the claim timer survives it.
_RT_TU_CONFIRM_TIMEOUT_SEC = 8.0

# A claim that got no reply is not a claim that failed — the click may have
# landed and only the confirmation been lost, which is exactly how a paid ``$ot``
# click went missing before ``ChannelMonitor.click_button`` learned to retry. So
# a silent attempt is resolved by **re-reading the roll**, and only retried when
# that says the character is genuinely still there.
#
# The pause before each retry, escalating: whatever swallowed the first attempt
# (a rate limit, a gateway hiccup) is more likely to have cleared after 3s than
# after 1s, and backing off beats hammering a Discord endpoint that is already
# refusing. The **first** attempt is never delayed — a wish is claimed the
# instant it spawns, which is the whole point of interrupting the roll loop.
# Attempt count follows this ladder, and the loop aborts early anyway as soon as
# a re-read says the claim window has closed, so the tail rungs cost nothing on
# a roll that is already gone.
_CLAIM_RETRY_PAUSES_SEC = (1.0, 3.0, 5.0)
_CLAIM_ATTEMPTS = len(_CLAIM_RETRY_PAUSES_SEC) + 1
_CLAIM_REPLY_TIMEOUT_SEC = 8.0

# Shortest an ``$rt`` detour can take: the pause before sending, the settle
# after Mudae's tick, and a tick that arrives promptly (the 3s). Derived from
# those two constants so lengthening either one moves this with it, rather than
# leaving a hardcoded floor behind. Used only to refuse a
# spend that *cannot* pay off — a roll with less than this left on its claim
# timer will have a dead button by the time ``$rt`` returns, so
# sending it burns a reset for nothing. Deliberately optimistic: the cost of
# being wrong here is a lost claim, while the cost of being wrong the other way
# is only a wasted ``$rt``, and the timer is normally 45s against a roll that is
# a second or two old.
_RT_ROUND_TRIP_FLOOR_SEC = _RT_PAUSE_BEFORE_SEC + _RT_SETTLE_AFTER_TICK_SEC + 3.0


@dataclass
class RollRecord:
    message_id: int
    character_name: str | None
    fields: dict[str, Any]
    rolled_at: float = field(default_factory=time.monotonic)


def is_within_claim_timer(
    record: RollRecord,
    expire_sec: int,
    *,
    now: float | None = None,
) -> bool:
    """Mudae claim buttons expire after ``settimer`` seconds (often 45)."""
    if expire_sec <= 0:
        return True
    if record.rolled_at <= 0:
        return True
    current = now if now is not None else time.monotonic()
    return (current - record.rolled_at) < expire_sec


def records_within_claim_timer(
    records: list[RollRecord],
    expire_sec: int,
    *,
    now: float | None = None,
) -> list[RollRecord]:
    current = now if now is not None else time.monotonic()
    return [r for r in records if is_within_claim_timer(r, expire_sec, now=current)]


def roll_total_kakera(fields: dict[str, Any]) -> int:
    """Character kakera value from roll embed (``total_kakera`` field)."""
    value = fields.get("total_kakera")
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def pick_best_claimable(
    records: list[RollRecord],
    *,
    expire_sec: int | None = None,
    now: float | None = None,
) -> RollRecord | None:
    """Highest ``total_kakera`` among claimable rolls still inside the claim timer."""
    pool = records
    if expire_sec is not None:
        pool = records_within_claim_timer(records, expire_sec, now=now)
    candidates = [
        r
        for r in pool
        if not r.fields.get("claimed") and r.fields.get("can_claim")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: roll_total_kakera(r.fields))


class PostRollHandler:
    def __init__(
        self,
        actions: DiscordActions,
        config: MacroConfig,
        state: AccountState,
        *,
        log: Callable[[str], None],
    ) -> None:
        self._actions = actions
        self._config = config
        self._state = state
        self._log = log

    def _claim_expire_sec(self) -> int:
        if self._state.claim_expire_sec is not None:
            return max(1, int(self._state.claim_expire_sec))
        return max(1, self._config.claim_expire_sec)

    def _rt_can_still_pay_off(self, record: RollRecord, expire: int) -> bool:
        """Whether enough of the claim timer is left to survive an ``$rt``.

        ``$rt`` is a scarce daily reset, and the claim button dies ``settimer``
        seconds after the roll whatever we do. Spending one on a roll that will
        already be dead when the round trip finishes is a guaranteed loss, so it
        is refused rather than attempted.
        """
        if expire <= 0 or record.rolled_at <= 0:
            return True
        left = expire - (time.monotonic() - record.rolled_at)
        return left >= _RT_ROUND_TRIP_FLOOR_SEC

    async def claim_record(
        self,
        record: RollRecord,
        *,
        reason: str = "",
        allow_rt: bool = False,
    ) -> bool:
        """Claim one roll immediately (interrupt path). Returns True if claim attempted."""
        prefix = f"{reason}: " if reason else ""
        rules = self._config.character_claim
        if not (rules.enabled or rules.claim_on_wish_ping):
            self._log(f"{prefix}character claim off — skipped")
            return False

        # Everything knowable *before* spending anything is checked first. These
        # same three ran only after ``$rt`` had already been sent, so a roll that
        # was already claimed, already un-clickable, or already past its timer
        # cost a reset to discover.
        expire = self._claim_expire_sec()
        if record.fields.get("claimed"):
            owner = record.fields.get("owner") or "someone else"
            self._log(f"{prefix}already claimed by {owner} — skipped")
            return False
        if not record.fields.get("can_claim"):
            self._log(f"{prefix}not claimable — skipped")
            return False
        if not is_within_claim_timer(record, expire):
            self._log(f"{prefix}claim timer expired (>{expire}s) — skipped")
            return False

        needed_rt = allow_rt and self._state.claim_available is False
        if needed_rt and not self._rt_can_still_pay_off(record, expire):
            self._log(
                f"{prefix}claim timer has under {_RT_ROUND_TRIP_FLOOR_SEC:g}s left — "
                "not spending $rt on a claim that would expire mid-round-trip"
            )
            return False
        if not await self._ensure_claim_slot(
            prefix, allow_rt=allow_rt, character=record.character_name or ""
        ):
            self._log(f"{prefix}claim on cooldown — skipped")
            return False
        # $rt can take several seconds (tick + settle + response waits); refresh
        # the roll's fields so a stale "can_claim"/"claimed" snapshot from before
        # $rt doesn't cause a wrong skip or a click on an already-claimed roll.
        if needed_rt:
            await self._refresh_record_fields(record)
            if record.fields.get("claimed"):
                owner = record.fields.get("owner") or "someone else"
                self._log(f"{prefix}already claimed by {owner} — skipped")
                return False
            if not record.fields.get("can_claim"):
                self._log(f"{prefix}not claimable — skipped")
                return False
            if not is_within_claim_timer(record, expire):
                self._log(f"{prefix}claim timer expired (>{expire}s) — skipped")
                return False
        await self._try_claim(record)
        return True

    async def _refresh_record_fields(self, record: RollRecord) -> None:
        """Re-fetch the roll message so claim/button state reflects reality.

        Used after an ``$rt`` detour: cached fields are from roll time, and by
        the time the ``$rt`` round trip finishes, someone else may have
        claimed the character, or Mudae may have disabled the button once its
        own claim timer elapsed.
        """
        from mudae.parsers.pipeline import parse_mudae_message

        try:
            fresh = await self._actions.fetch_message_snapshot(record.message_id)
        except Exception as exc:  # noqa: BLE001 - a refetch must not kill a claim
            self._log(f"Could not re-read the roll: {exc}")
            return
        if fresh is None:
            return
        try:
            parsed = parse_mudae_message(fresh)
        except Exception as exc:  # noqa: BLE001 - same: best-effort refresh only
            self._log(f"Could not parse the re-read roll: {exc}")
            return
        if parsed.fields.get("character_name") is None:
            return
        record.fields = dict(parsed.fields)

    async def claim_best(
        self,
        records: list[RollRecord],
        *,
        context: str = "final roll batch",
        final_hour: bool = True,
    ) -> None:
        """Claim the best character from this roll session only (buttons expire ~45s).

        Eligibility is filtered through ``character_claim`` rules so hard filters
        (chaos key / sphere count / rank caps / min kakera) apply to the picker.
        """
        if not records:
            return
        rules = self._config.character_claim
        if not rules.enabled:
            self._log(f"{len(records)} roll(s) this session; character claim off")
            return
        if self._state.claim_available is False:
            self._log(f"{len(records)} roll(s) this session; claim on cooldown")
            return
        # The open slot was bought with ``$rt`` for one specific character and
        # that claim did not land. Spending it on whoever happens to be worth
        # the most kakera this batch is not what the reset was for, and it also
        # leaves the *next* wish this hour with no slot and no ``$rt``. Leaving
        # it open costs nothing: it keeps until a claim uses it.
        if self._state.rt_claim_slot_for:
            self._log(
                f"{len(records)} roll(s) this session; the open claim slot came "
                f"from $rt spent on {self._state.rt_claim_slot_for} — keeping it "
                "for a wish rather than claiming the best of this batch"
            )
            return

        expire = self._claim_expire_sec()
        now = time.monotonic()
        live = records_within_claim_timer(records, expire, now=now)
        expired = len(records) - len(live)
        if expired:
            self._log(
                f"{expired} roll(s) past claim timer ({expire}s) — "
                "only this session's fresh rolls count"
            )

        eligible: list[RollRecord] = []
        skipped: list[tuple[str, str]] = []
        for record in live:
            if not record.fields.get("can_claim") or record.fields.get("claimed"):
                continue
            decision = passes_character_claim(
                record.fields,
                rules,
                self._state,
                final_hour=final_hour,
                wished_pinged=False,
            )
            if decision.should_claim or decision.reason == "eligible at end of batch":
                eligible.append(record)
            else:
                skipped.append((record.character_name or "?", decision.reason))

        if not eligible:
            if skipped:
                reason_summary = ", ".join(
                    f"{name} ({reason})" for name, reason in skipped[:3]
                )
                more = f" (+{len(skipped) - 3} more)" if len(skipped) > 3 else ""
                self._log(
                    f"No eligible rolls for end-of-batch claim: {reason_summary}{more}"
                )
            else:
                self._log(
                    f"No claimable rolls left in this batch (within {expire}s)"
                )
            return

        best = max(eligible, key=lambda r: roll_total_kakera(r.fields))
        value = roll_total_kakera(best.fields)
        name = best.character_name or "?"
        self._log(
            f"Best this batch: {name} ({value} ka) — claiming at {context} "
            f"({len(eligible)} eligible)"
        )
        await self._try_claim(best)

    async def _ensure_claim_slot(
        self, prefix: str, *, allow_rt: bool = False, character: str = ""
    ) -> bool:
        if self._state.claim_available is not False:
            return True
        if not allow_rt:
            return False
        rules = self._config.character_claim
        if not rules.auto_use_rt or not has_rt_available(self._state):
            return False
        return await self._try_use_rt(
            reason=prefix.rstrip(": "), character=character
        )

    async def _try_use_rt(self, *, reason: str = "", character: str = "") -> bool:
        rules = self._config.character_claim
        if not rules.auto_use_rt or not has_rt_available(self._state):
            if rules.auto_use_rt:
                self._log("$rt: none available — cannot reset claim timer")
            return False

        note = f"{reason} · " if reason else ""
        self._log(f"$rt: waiting {_RT_PAUSE_BEFORE_SEC:g}s before send — {note}claim on cooldown")
        await asyncio.sleep(_RT_PAUSE_BEFORE_SEC)

        message_id = await self._actions.send_command("rt", prefix=self._config.prefix)
        if message_id is None:
            self._log("$rt: send failed — claim cancelled")
            return False
        self._log(f"$rt: sent {self._config.prefix}rt")

        ticked = await self._actions.wait_for_mudae_tick(
            message_id,
            timeout=_RT_TICK_TIMEOUT_SEC,
        )
        if not ticked:
            # No tick is not proof the command was missed — a reaction can be
            # lost like any other gateway event — and it is the only signal
            # there is, so ask $tu rather than write the reset off.
            self._log(f"$rt: no Mudae tick within {_RT_TICK_TIMEOUT_SEC:g}s")
            return await self._confirm_rt_with_tu(character=character)

        # Mudae answers ``$rt`` with a tick on the command message and nothing
        # else — there is no reply to read, so the tick *is* the confirmation.
        # This used to wait 12s for a reply that was never coming, and then
        # cancel the claim when it did not arrive.
        self._log(
            f"$rt: confirmed by tick — waiting {_RT_SETTLE_AFTER_TICK_SEC:g}s "
            "before claim"
        )
        await asyncio.sleep(_RT_SETTLE_AFTER_TICK_SEC)
        apply_rt_response(self._state, {"rt_used": True, "claim_available": True})

        # Remember who the reset was bought for. If this claim then falls
        # through, ``claim_best`` must not spend the slot on someone else.
        self._state.rt_claim_slot_for = character or "a wish"
        self._log("$rt OK — claim slot available")
        return True

    async def _confirm_rt_with_tu(self, *, character: str = "") -> bool:
        """Ask ``$tu`` whether the reset landed when the tick never arrived.

        The tick is the only thing Mudae sends, so losing it leaves no other
        evidence — and reporting the reset as failed loses the claim *and*
        leaves a reset that may already be spent recorded as still available for
        the rest of the day. ``$tu`` is the one thing that can settle it.
        """
        self._log("$rt: asking $tu whether the reset landed")
        message_id = await self._actions.send_command("tu", prefix=self._config.prefix)
        if message_id is None:
            self._log("$rt: $tu send failed — claim cancelled")
            return False
        parsed = await self._actions.wait_for_tu(timeout=_RT_TU_CONFIRM_TIMEOUT_SEC)
        if parsed is None:
            self._log(
                f"$rt: no $tu reply within {_RT_TU_CONFIRM_TIMEOUT_SEC:g}s — "
                "claim cancelled"
            )
            return False

        fields = dict(parsed.fields)
        if not apply_rt_response(self._state, fields):
            self._log("$rt: $tu says the claim is still on cooldown — claim cancelled")
            return False

        self._state.rt_claim_slot_for = character or "a wish"
        self._log("$rt OK — $tu confirms the claim slot is open")
        return True

    def _claim_method(self, record: RollRecord) -> str:
        """``"button"`` / ``"reaction"`` / ``""`` for this record.

        The roll parser already decided this from the components
        (:func:`mudae.buttons.claim_method_from_buttons`); records built
        elsewhere (a chaos wish spawn, an old snapshot) may predate the field,
        so fall back to reading their buttons the same way.
        """
        method = record.fields.get("claim_method")
        if method in {"button", "reaction"}:
            return str(method)
        if record.fields.get("claimed"):
            return ""
        return claim_method_from_buttons(record.fields.get("buttons") or [])

    async def _send_claim(self, record: RollRecord, method: str) -> bool:
        """Press the claim button, or react to the roll when there is none."""
        name = record.character_name or "?"
        if method == "reaction":
            # Buttons are off for this server or account: Mudae takes any emoji
            # on the roll as the claim. Same claim slot, same rules, different
            # transport — everything after this point is unchanged.
            self._log(f"Claiming {name} by reaction ({CLAIM_REACTION_EMOJI})…")
            reacted = await self._actions.add_reaction(
                record.message_id, CLAIM_REACTION_EMOJI
            )
            if not reacted:
                self._log(f"Claim reaction failed for {name}")
            return reacted

        buttons = record.fields.get("buttons") or []
        claim_btn = next(
            (b for b in buttons if is_claim_button(b) and not b.get("disabled")),
            None,
        )
        custom_id = (claim_btn or {}).get("custom_id") or ""
        if not custom_id:
            self._log(f"Claim button on {name} has no id — skipped")
            return False
        self._log(f"Claiming {name}…")
        clicked = await self._actions.click_button(record.message_id, custom_id)
        if not clicked:
            self._log(f"Claim click failed for {name}")
        return clicked

    def _owned_by_us(self, record: RollRecord) -> bool:
        """Whether a re-read roll now says *we* own it."""
        if not record.fields.get("claimed"):
            return False
        return username_matches_own(
            record.fields.get("owner"), self._state.own_usernames
        )

    async def _claim_landed_silently(self, record: RollRecord) -> bool | None:
        """Re-read the roll after a silent attempt.

        ``True`` the claim landed and only the reply was lost, ``False`` it is
        gone for good, ``None`` it is still there to try again.
        """
        await self._refresh_record_fields(record)
        name = record.character_name or "?"
        if self._owned_by_us(record):
            self._log(f"Claim confirmed on {name} by re-reading the roll")
            return True
        if record.fields.get("claimed"):
            owner = record.fields.get("owner") or "someone else"
            self._log(f"{name} was claimed by {owner} — nothing to retry")
            return False
        if not record.fields.get("can_claim"):
            self._log(f"Claim window closed on {name} — not retrying")
            return False
        if not is_within_claim_timer(record, self._claim_expire_sec()):
            self._log(f"Claim timer ran out on {name} — not retrying")
            return False
        return None

    async def _try_claim(self, record: RollRecord) -> None:
        """Claim one roll, retrying while the character is demonstrably still there.

        A wish is claimed within a second or two of spawning, so a claim that
        does not land is a lost click or a lost reply rather than an expired
        window — and giving up on the first silence left the slot open for the
        end-of-batch picker to spend on someone else.
        """
        method = self._claim_method(record)
        if not method:
            if record.fields.get("claimed"):
                owner = record.fields.get("owner") or "someone else"
                self._log(f"{record.character_name or '?'} was already claimed by {owner}")
            else:
                # Not "no button": a roll with no buttons at all is the
                # react-to-claim case and never lands here. This is a claim
                # button Mudae has *disabled*, i.e. the window has closed.
                self._log(
                    f"Claim window closed on {record.character_name or '?'} "
                    "(claim button disabled)"
                )
            return

        name = record.character_name or "?"
        for attempt in range(1, _CLAIM_ATTEMPTS + 1):
            if attempt > 1:
                pause = _CLAIM_RETRY_PAUSES_SEC[attempt - 2]
                self._log(
                    f"Retrying claim on {name} in {pause:g}s "
                    f"({attempt}/{_CLAIM_ATTEMPTS})"
                )
                await asyncio.sleep(pause)

            sent = await self._send_claim(record, method)
            parsed = (
                await self._actions.wait_for_claim(timeout=_CLAIM_REPLY_TIMEOUT_SEC)
                if sent
                else None
            )
            if parsed is not None:
                await self._handle_claim_reply(record, parsed)
                return

            if sent:
                self._log(f"Claim timeout for {name} — checking whether it landed")
            landed = await self._claim_landed_silently(record)
            if landed is True:
                # The click was paid for; treat the slot as spent so nothing
                # else in this batch tries to claim on top of it.
                self._state.claim_available = False
                self._state.rt_claim_slot_for = ""
                return
            if landed is False:
                return
            # Still claimable: the button was re-read, so its ids are current.
            method = self._claim_method(record) or method

        self._log(f"Gave up claiming {name} after {_CLAIM_ATTEMPTS} attempts")

    async def _handle_claim_reply(self, record: RollRecord, parsed: Any) -> None:
        if parsed.kind == MessageKind.CLAIM_INTERVAL:
            # This *is* the same claim slot tracked by `claim_available` /
            # `claim_cooldown_minutes` (normally refreshed from `$tu`) — the
            # click just revealed its real state more precisely than our last
            # `$tu` did. Sync it the same way `$tu` parsing does, so the
            # existing `claim_available is False` guards everywhere else
            # (claim_best, $rt) take effect immediately instead of clicking
            # into the same wall on the next roll in this batch.
            minutes = parsed.fields.get("next_interval_minutes")
            self._state.claim_available = False
            self._state.rt_claim_slot_for = ""
            self._state.set_claim_cooldown(minutes)
            wait_note = f" — next in {minutes}m" if minutes is not None else ""
            self._log(
                f"Claim blocked by this server's claim interval for "
                f"{record.character_name or '?'}{wait_note}"
            )
            return
        winner = parsed.fields.get("winner") or "?"
        character = parsed.fields.get("character") or record.character_name or "?"
        # The claim slot is now spent — stop further claim attempts this session
        # (next $tu refreshes the real cooldown).
        self._state.claim_available = False
        self._state.rt_claim_slot_for = ""
        record.fields["claimed"] = True
        self._log(f"Claimed {character} ({winner})")
