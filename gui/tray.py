"""System tray integration for minimize-to-tray."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_NOTIFICATION_MS = 8000


class TrayController(QObject):
    def __init__(
        self,
        app: QObject,
        window: QObject,
        bridge: QObject,
        *,
        icon_path: Path,
    ) -> None:
        super().__init__()
        self._app = app
        self._window = window
        self._bridge = bridge
        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        self._icon: QSystemTrayIcon | None = None

        if not self._available:
            return

        icon = QIcon(str(icon_path))
        if icon.isNull():
            self._available = False
            return

        tray = QSystemTrayIcon(icon, parent=None)
        tray.setToolTip("FinalMacro")

        menu = QMenu()
        show_action = QAction("Show FinalMacro", menu)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.request_quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_activated)
        tray.show()
        self._icon = tray

    @property
    def available(self) -> bool:
        return self._available and self._icon is not None

    def show_window(self) -> None:
        if self._window is None:
            return
        show = getattr(self._window, "show", None)
        if callable(show):
            show()
        set_state = getattr(self._window, "setWindowState", None)
        window_state = getattr(self._window, "windowState", None)
        if callable(set_state) and callable(window_state):
            from PySide6.QtCore import Qt

            state = window_state()
            if state & Qt.WindowState.WindowMinimized:
                set_state(state & ~Qt.WindowState.WindowMinimized)
        raise_fn = getattr(self._window, "raise_", None)
        if callable(raise_fn):
            raise_fn()
        activate = getattr(self._window, "requestActivate", None)
        if callable(activate):
            activate()

    def request_quit(self) -> None:
        shutdown = getattr(self._bridge, "shutdown", None)
        if callable(shutdown):
            shutdown()
        quit_fn = getattr(self._app, "quit", None)
        if callable(quit_fn):
            quit_fn()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Linux status-notifier backends usually emit Trigger (primary click), not
        # DoubleClick — handle both so left/double click restores the window.
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def notify(self, title: str, message: str) -> None:
        """Show an OS notification balloon from the tray icon, if one exists."""
        if self._icon is None:
            return
        if not QSystemTrayIcon.supportsMessages():
            return
        self._icon.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            _NOTIFICATION_MS,
        )
