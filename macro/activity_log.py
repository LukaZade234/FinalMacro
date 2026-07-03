"""Single write path for macro activity log lines (GUI + state)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from macro.state import AccountState

ActivitySeverity = Literal["info", "claim", "click", "skip", "error"]

_SEVERITY_ORDER: tuple[ActivitySeverity, ...] = (
    "info",
    "claim",
    "click",
    "skip",
    "error",
)


@dataclass
class ActivityLogEntry:
    text: str
    severity: ActivitySeverity = "info"

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "severity": self.severity}


def classify_activity_line(text: str) -> ActivitySeverity:
    """Heuristic severity tag for a single activity-log line."""
    lower = text.lower()
    if any(
        token in lower
        for token in (
            "error",
            "timeout",
            " failed",
            "failed ",
            "click failed",
            "claim click failed",
            "claim timeout",
        )
    ):
        return "error"
    if " skip" in lower or "skipped" in lower or "— skipped" in lower:
        return "skip"
    if (
        lower.startswith("claiming ")
        or lower.startswith("claimed ")
        or "claim now" in lower
        or "character claim" in lower
    ):
        return "claim"
    if (
        " click ×" in lower
        or " click " in lower
        or lower.startswith("kakera click")
        or lower.startswith("sphere click")
        or "$oh: click" in lower
    ):
        return "click"
    return "info"


class ActivityLog:
    """
    Append-only activity log backed by ``AccountState.activity_log``.

    All macro components should log through this type so lines are never
    duplicated and UI notifications stay in one place.
    """

    def __init__(
        self,
        state: AccountState,
        *,
        on_update: Callable[[], None] | None = None,
        max_lines: int = 200,
    ) -> None:
        self._state = state
        self._on_update = on_update
        self._max_lines = max(1, max_lines)

    def write(self, text: str, *, severity: ActivitySeverity | None = None) -> None:
        if not text:
            return
        entry = ActivityLogEntry(
            text=text,
            severity=severity or classify_activity_line(text),
        )
        self._state.activity_log.append(entry)
        if len(self._state.activity_log) > self._max_lines:
            self._state.activity_log = self._state.activity_log[-self._max_lines :]
        if self._on_update:
            self._on_update()

    def clear(self) -> None:
        self._state.activity_log.clear()
        if self._on_update:
            self._on_update()


def activity_log_text(entries: list[ActivityLogEntry]) -> str:
    return "\n".join(entry.text for entry in entries)


def normalize_activity_log(raw: list[Any]) -> list[ActivityLogEntry]:
    """Coerce legacy plain-string logs into structured entries."""
    out: list[ActivityLogEntry] = []
    for item in raw:
        if isinstance(item, ActivityLogEntry):
            out.append(item)
        elif isinstance(item, dict):
            text = str(item.get("text") or "")
            sev = str(item.get("severity") or "info")
            if sev not in _SEVERITY_ORDER:
                sev = classify_activity_line(text)
            out.append(ActivityLogEntry(text=text, severity=sev))  # type: ignore[arg-type]
        elif isinstance(item, str):
            out.append(ActivityLogEntry(text=item, severity=classify_activity_line(item)))
    return out
