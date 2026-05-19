"""Single write path for macro activity log lines (GUI + state)."""

from __future__ import annotations

from collections.abc import Callable

from macro.state import AccountState


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
        max_lines: int = 20,
    ) -> None:
        self._state = state
        self._on_update = on_update
        self._max_lines = max(1, max_lines)

    def write(self, text: str) -> None:
        if not text:
            return
        self._state.activity_log.append(text)
        if len(self._state.activity_log) > self._max_lines:
            self._state.activity_log = self._state.activity_log[-self._max_lines :]
        if self._on_update:
            self._on_update()

    def clear(self) -> None:
        self._state.activity_log.clear()
        if self._on_update:
            self._on_update()
