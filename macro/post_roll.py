"""Post-roll claim: pick highest kakera value after all rolls finish."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mudae.buttons import is_claim_button

from macro.actions import DiscordActions
from macro.config import MacroConfig
from macro.rule_eval import passes_character_claim
from macro.state import AccountState


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

    async def claim_record(self, record: RollRecord, *, reason: str = "") -> bool:
        """Claim one roll immediately (interrupt path). Returns True if claim attempted."""
        prefix = f"{reason}: " if reason else ""
        rules = self._config.character_claim
        if not (rules.enabled or rules.claim_on_wish_ping):
            self._log(f"{prefix}character claim off — skipped")
            return False
        if self._state.claim_available is False:
            self._log(f"{prefix}claim on cooldown — skipped")
            return False
        if record.fields.get("claimed"):
            self._log(f"{prefix}already claimed — skipped")
            return False
        if not record.fields.get("can_claim"):
            self._log(f"{prefix}not claimable — skipped")
            return False
        expire = self._claim_expire_sec()
        if not is_within_claim_timer(record, expire):
            self._log(f"{prefix}claim timer expired (>{expire}s) — skipped")
            return False
        await self._try_claim(record)
        return True

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

    async def _try_claim(self, record: RollRecord) -> None:
        buttons = record.fields.get("buttons") or []
        claim_btn = next(
            (b for b in buttons if is_claim_button(b) and not b.get("disabled")),
            None,
        )
        if not claim_btn:
            self._log(f"No claim button on {record.character_name or '?'}")
            return
        custom_id = claim_btn.get("custom_id") or ""
        if not custom_id:
            return
        self._log(f"Claiming {record.character_name or '?'}…")
        clicked = await self._actions.click_button(record.message_id, custom_id)
        if not clicked:
            self._log(f"Claim click failed for {record.character_name or '?'}")
            return
        parsed = await self._actions.wait_for_claim(timeout=8.0)
        if parsed is None:
            self._log(f"Claim timeout for {record.character_name or '?'}")
            return
        winner = parsed.fields.get("winner") or "?"
        character = parsed.fields.get("character") or record.character_name or "?"
        # The claim slot is now spent — stop further claim attempts this session
        # (next $tu refreshes the real cooldown).
        self._state.claim_available = False
        record.fields["claimed"] = True
        self._log(f"Claimed {character} ({winner})")
