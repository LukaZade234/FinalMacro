"""Single write path for macro activity log lines (GUI + state + session files)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from macro.state import AccountState
from mudae.clock import local_hhmmss, utc_now

if TYPE_CHECKING:
    from macro.session_log import SessionLogRecorder

ActivitySeverity = Literal["info", "claim", "click", "skip", "error", "debug"]

ACTIVITY_LOG_MAX_LINES = 400

_SEVERITY_ORDER: tuple[ActivitySeverity, ...] = (
    "info",
    "claim",
    "click",
    "skip",
    "error",
    "debug",
)


@dataclass
class ActivityLogEntry:
    text: str
    severity: ActivitySeverity = "info"
    ts: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"text": self.text, "severity": self.severity}
        if self.ts:
            out["ts"] = self.ts
        return out


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


def _now_ts() -> str:
    return utc_now().isoformat(timespec="seconds")


def _display_ts(iso_ts: str) -> str:
    return local_hhmmss(iso_ts) or iso_ts


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
        max_lines: int = ACTIVITY_LOG_MAX_LINES,
        session: SessionLogRecorder | None = None,
    ) -> None:
        self._state = state
        self._on_update = on_update
        self._max_lines = max(1, max_lines)
        self._session = session

    def set_session(self, session: SessionLogRecorder | None) -> None:
        self._session = session

    def write(
        self,
        text: str,
        *,
        severity: ActivitySeverity | None = None,
        session_only: bool = False,
    ) -> None:
        if not text:
            return
        ts = _now_ts()
        entry = ActivityLogEntry(
            text=text,
            severity=severity or classify_activity_line(text),
            ts=ts,
        )
        if self._session:
            self._session.write(entry, ts=ts)
        if session_only:
            return
        self._state.activity_log.append(entry)
        if len(self._state.activity_log) > self._max_lines:
            self._state.activity_log = self._state.activity_log[-self._max_lines :]
        if self._on_update:
            self._on_update()

    def debug(self, text: str) -> None:
        """Verbose line saved to the session file but hidden from the Run tab."""
        self.write(text, severity="debug", session_only=True)

    def clear(self) -> None:
        self._state.activity_log.clear()
        if self._on_update:
            self._on_update()


def activity_log_text(entries: list[ActivityLogEntry]) -> str:
    lines: list[str] = []
    for entry in entries:
        if entry.ts:
            lines.append(f"[{_display_ts(entry.ts)}] {entry.text}")
        else:
            lines.append(entry.text)
    return "\n".join(lines)


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
            out.append(
                ActivityLogEntry(
                    text=text,
                    severity=sev,  # type: ignore[arg-type]
                    ts=str(item.get("ts") or ""),
                )
            )
        elif isinstance(item, str):
            out.append(ActivityLogEntry(text=item, severity=classify_activity_line(item)))
    return out
