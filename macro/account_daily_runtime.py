"""Send account-global ``$p`` / ``$daily`` on a designated channel.

Transport (channel switch, send, wait, persist) is injected so tests do not need
Discord. One plan at a time: switch, send due commands, then the caller restores
the run-target channel.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any

from macro.account_dailies import (
    COMMAND_DAILY,
    COMMAND_P,
    AccountDailyPlan,
    daily_ready_after_success,
    iso_ready,
    next_p_reset_at,
    ready_after_minutes,
)
from mudae.clock import utc_now
from mudae.parsers.p_daily import is_daily_parse_result, is_p_parse_result
from mudae.types import ParseResult

SWITCH_ATTEMPTS = 3
SWITCH_RETRY_SEC = 2.0
# Pause after a channel switch and between $p / $daily so Mudae replies
# are not still in flight when the next command is typed.
COMMAND_GAP_SEC = 2.5
P_REPLY_TIMEOUT_SEC = 15.0
DAILY_TICK_TIMEOUT_SEC = 8.0
DAILY_COOLDOWN_TIMEOUT_SEC = 8.0
FAIL_BACKOFF_SEC = 60.0

SwitchFn = Callable[[str, int], Awaitable[bool]]
SendFn = Callable[[str], Awaitable[int | None]]
TickFn = Callable[[int, float], Awaitable[bool]]
WaitFn = Callable[..., Awaitable[tuple[Any, ParseResult] | None]]
SleepFn = Callable[[float], Awaitable[None]]
LogFn = Callable[[str], None]
PersistFn = Callable[[str, dict[str, str]], None]


class AccountDailyRuntime:
    """Orchestrate sequential ``$p`` / ``$daily`` sends with channel switching."""

    def __init__(
        self,
        *,
        switch_to: SwitchFn,
        send_command: SendFn,
        wait_for_tick: TickFn,
        wait_for: WaitFn,
        sleep: SleepFn,
        log: LogFn,
        persist_account: PersistFn,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._switch_to = switch_to
        self._send_command = send_command
        self._wait_for_tick = wait_for_tick
        self._wait_for = wait_for
        self._sleep = sleep
        self._log = log
        self._persist = persist_account
        self._now = now or utc_now
        self._fail_until: dict[tuple[str, str], float] = {}

    def _blocked(self, account_id: str, command: str) -> bool:
        import time

        deadline = self._fail_until.get((account_id, command), 0.0)
        return time.monotonic() < deadline

    def _note_fail(self, account_id: str, command: str) -> None:
        import time

        self._fail_until[(account_id, command)] = time.monotonic() + FAIL_BACKOFF_SEC

    def _clear_fail(self, account_id: str, command: str) -> None:
        self._fail_until.pop((account_id, command), None)

    async def switch_with_retries(self, token: str, discord_channel_id: int) -> bool:
        last_ok = False
        for attempt in range(1, SWITCH_ATTEMPTS + 1):
            last_ok = await self._switch_to(token.strip(), int(discord_channel_id))
            if last_ok:
                return True
            self._log(
                f"$p/$daily: channel switch failed "
                f"({attempt}/{SWITCH_ATTEMPTS}) — retrying"
            )
            await self._sleep(SWITCH_RETRY_SEC * attempt)
        return last_ok

    async def run_plans(
        self,
        plans: list[AccountDailyPlan],
        *,
        home_token: str,
        home_channel_id: int,
        discord_channel_id_for: Callable[[AccountDailyPlan], int | None],
    ) -> bool:
        """Send due commands one account at a time, then restore the home channel.

        Returns True when at least one command was attempted.
        """
        if not plans:
            return False
        work: list[tuple[AccountDailyPlan, int, list[str]]] = []
        for plan in plans:
            channel_id = discord_channel_id_for(plan)
            if channel_id is None:
                self._log(
                    f"$p/$daily: {plan.account_name} has no Discord channel id "
                    "for the designated channel"
                )
                continue
            cmds = [
                cmd
                for cmd in plan.commands
                if not self._blocked(plan.account_id, cmd)
            ]
            if not cmds:
                continue
            if not plan.token.strip():
                self._log(f"$p/$daily: {plan.account_name} has no token — skipping")
                continue
            work.append((plan, channel_id, cmds))
        if not work:
            return False
        attempted = False
        try:
            for plan, channel_id, cmds in work:
                switched = await self.switch_with_retries(plan.token, channel_id)
                if not switched:
                    self._log(
                        f"$p/$daily: could not reach {plan.account_name}'s "
                        "designated channel — skipping"
                    )
                    continue
                attempted = True
                await self._sleep(COMMAND_GAP_SEC)
                for index, command in enumerate(cmds):
                    if index:
                        await self._sleep(COMMAND_GAP_SEC)
                    await self._send_one(plan, command)
                await self._sleep(COMMAND_GAP_SEC)
        finally:
            restored = await self.switch_with_retries(home_token, home_channel_id)
            if not restored:
                self._log("$p/$daily: failed to restore the run-target channel")
        return attempted

    async def _send_one(self, plan: AccountDailyPlan, command: str) -> None:
        if command == COMMAND_P:
            await self._send_p(plan)
        elif command == COMMAND_DAILY:
            await self._send_daily(plan)

    async def _send_p(self, plan: AccountDailyPlan) -> None:
        self._log(f"$p: sending for {plan.account_name}")
        try:
            await self._send_command("p")
        except Exception as exc:
            self._log(f"$p: send failed ({exc})")
            self._note_fail(plan.account_id, COMMAND_P)
            return
        result = await self._wait_for(
            lambda _snapshot, parsed: is_p_parse_result(parsed),
            timeout=P_REPLY_TIMEOUT_SEC,
        )
        now = self._now()
        if result is None:
            self._log(f"$p: no reply for {plan.account_name} — will retry")
            self._note_fail(plan.account_id, COMMAND_P)
            return
        _snapshot, parsed = result
        cooldown = parsed.fields.get("p_cooldown_minutes")
        if cooldown is not None:
            ready = ready_after_minutes(int(cooldown), now=now)
            self._persist(plan.account_id, {"p_next_ready_at": iso_ready(ready)})
            self._clear_fail(plan.account_id, COMMAND_P)
            self._log(f"$p: on cooldown for {plan.account_name} · next in {int(cooldown)}m")
            return
        # Cooldown is the only negative outcome. A pokemon grid / "You won"
        # line, or any other $p-tagged reply, means the send went through.
        ready = next_p_reset_at(now)
        self._persist(plan.account_id, {"p_next_ready_at": iso_ready(ready)})
        self._clear_fail(plan.account_id, COMMAND_P)
        self._log(f"$p: ok for {plan.account_name}")

    async def _send_daily(self, plan: AccountDailyPlan) -> None:
        self._log(f"$daily: sending for {plan.account_name}")
        try:
            message_id = await self._send_command("daily")
        except Exception as exc:
            self._log(f"$daily: send failed ({exc})")
            self._note_fail(plan.account_id, COMMAND_DAILY)
            return
        now = self._now()
        ticked = False
        if message_id is not None:
            ticked = await self._wait_for_tick(int(message_id), DAILY_TICK_TIMEOUT_SEC)
        if ticked:
            ready = daily_ready_after_success(now)
            self._persist(plan.account_id, {"daily_next_ready_at": iso_ready(ready)})
            self._clear_fail(plan.account_id, COMMAND_DAILY)
            self._log(f"$daily: ok for {plan.account_name}")
            return
        result = await self._wait_for(
            lambda _snapshot, parsed: is_daily_parse_result(parsed),
            timeout=DAILY_COOLDOWN_TIMEOUT_SEC,
        )
        if result is None:
            self._log(f"$daily: no ack for {plan.account_name} — will retry")
            self._note_fail(plan.account_id, COMMAND_DAILY)
            return
        _snapshot, parsed = result
        cooldown = parsed.fields.get("daily_cooldown_minutes")
        if cooldown is None:
            self._log(f"$daily: unexpected reply for {plan.account_name} — will retry")
            self._note_fail(plan.account_id, COMMAND_DAILY)
            return
        ready = ready_after_minutes(int(cooldown), now=now)
        self._persist(plan.account_id, {"daily_next_ready_at": iso_ready(ready)})
        self._clear_fail(plan.account_id, COMMAND_DAILY)
        self._log(
            f"$daily: on cooldown for {plan.account_name} · next in {int(cooldown)}m"
        )
