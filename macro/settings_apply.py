"""Apply Mudae server settings presets by sending ``$settings`` commands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from macro.actions import DiscordActions
from mudae.parsers.settings import parse_settings
from mudae.parsers.settings_normalize import normalize_settings_fields
from mudae.settings_commands import (
    ESSENTIAL_APPLY_FIELDS,
    SettingsDiffItem,
    commands_from_diff,
    diff_settings,
    validate_preset_for_premium,
)
from mudae.types import MessageKind, ParseResult

SEND_PAUSE_SEC = 3.5
SETTINGS_FETCH_TIMEOUT = 15.0
COMMAND_TIMEOUT = 12.0


def is_settings_parse_result(parsed: ParseResult) -> bool:
    if parsed.kind == MessageKind.SETTINGS:
        return True
    if parsed.kind == MessageKind.COMMAND_RESPONSE:
        cmd = str(parsed.fields.get("parser_command") or "").lower().lstrip("$")
        if cmd == "settings":
            return True
        if parsed.fields.get("setrolls") is not None and parsed.fields.get("gamemode") is not None:
            return True
    return False


@dataclass
class SettingsApplyResult:
    dry_run: bool
    diff: list[SettingsDiffItem] = field(default_factory=list)
    commands_sent: list[str] = field(default_factory=list)
    applied_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified_fields: dict[str, Any] = field(default_factory=dict)
    remaining_mismatches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "diff": [item.to_dict() for item in self.diff],
            "commands_sent": list(self.commands_sent),
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "verified_fields": self.verified_fields,
            "remaining_mismatches": list(self.remaining_mismatches),
        }


class SettingsApplyRunner:
    def __init__(
        self,
        actions: DiscordActions,
        *,
        log: Callable[[str], None] | None = None,
        prefix: str = "$",
        stop_check: Callable[[], bool] | None = None,
    ) -> None:
        self._actions = actions
        self._log = log or (lambda _msg: None)
        self._prefix = prefix
        self._stop_check = stop_check or (lambda: False)

    async def fetch_current_settings(self) -> dict[str, Any]:
        await self._actions.send_command("settings", prefix=self._prefix)
        result = await self._actions.wait_for(
            is_settings_parse_result,
            timeout=SETTINGS_FETCH_TIMEOUT,
        )
        if result is None:
            raise RuntimeError("Timed out waiting for $settings reply")
        if result.kind == MessageKind.SETTINGS:
            return normalize_settings_fields(dict(result.fields))
        content = str(result.fields.get("content") or result.summary or "")
        parsed = parse_settings(content)
        return normalize_settings_fields(dict(parsed.fields))

    async def apply(
        self,
        desired: dict[str, Any],
        *,
        current: dict[str, Any] | None = None,
        dry_run: bool = False,
        groups: frozenset[str] | None = None,
        fields: frozenset[str] | None = None,
        server_premium: int | None = None,
    ) -> SettingsApplyResult:
        outcome = SettingsApplyResult(dry_run=dry_run)
        outcome.warnings.extend(
            validate_preset_for_premium(desired, server_premium=server_premium)
        )

        if current is None:
            self._log("Fetching current $settings…")
            current = await self.fetch_current_settings()

        outcome.diff = diff_settings(
            current,
            desired,
            fields=fields or ESSENTIAL_APPLY_FIELDS,
            groups=groups,
        )
        commands = commands_from_diff(outcome.diff)
        outcome.skipped_count = sum(
            1 for item in outcome.diff if item.command is None
        )

        if dry_run:
            self._log(f"Dry run: {len(commands)} command(s) would be sent")
            for cmd in commands:
                self._log(f"  → {cmd}")
            return outcome

        if outcome.warnings:
            raise RuntimeError("; ".join(outcome.warnings))

        for item in outcome.diff:
            if self._stop_check():
                outcome.errors.append("Apply cancelled")
                break
            cmd = item.command
            if not cmd:
                continue
            self._log(f"Sending {cmd}")
            message_id = await self._actions.send_command(cmd.lstrip("$"), prefix=self._prefix)
            if message_id is not None:
                tick = await self._actions.wait_for_mudae_tick(message_id, timeout=5.0)
                if not tick:
                    self._log(f"  (no Mudae tick for {cmd})")
            await asyncio.sleep(SEND_PAUSE_SEC)
            outcome.commands_sent.append(cmd)
            outcome.applied_count += 1

        self._log("Verifying with $settings…")
        try:
            verified = await self.fetch_current_settings()
            outcome.verified_fields = verified
            remaining = diff_settings(
                verified,
                desired,
                fields=fields or ESSENTIAL_APPLY_FIELDS,
                groups=groups,
            )
            outcome.remaining_mismatches = [
                item.field
                for item in remaining
                if item.command is not None
            ]
            if outcome.remaining_mismatches:
                self._log(
                    "Still mismatched after apply: "
                    + ", ".join(outcome.remaining_mismatches)
                )
            else:
                self._log("All preset fields match after verify")
        except Exception as exc:  # noqa: BLE001
            outcome.errors.append(f"Verify failed: {exc}")

        return outcome
