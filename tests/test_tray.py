"""Tests for system tray helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from gui.tray import TrayController


def test_tray_marks_unavailable_when_system_tray_missing():
    window = SimpleNamespace(show=lambda: None, raise_=lambda: None, requestActivate=lambda: None)
    bridge = SimpleNamespace(shutdown=lambda: None)

    with patch("gui.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=False):
        tray = TrayController(None, window, bridge, icon_path=__file__)

    assert tray.available is False


def test_tray_show_window_calls_window_methods():
    calls: list[str] = []
    window = SimpleNamespace(
        show=lambda: calls.append("show"),
        raise_=lambda: calls.append("raise"),
        requestActivate=lambda: calls.append("activate"),
    )
    bridge = SimpleNamespace(shutdown=lambda: None)

    with patch("gui.tray.QSystemTrayIcon.isSystemTrayAvailable", return_value=True):
        with patch("gui.tray.QIcon") as icon_cls:
            icon_cls.return_value.isNull.return_value = False
            with patch("gui.tray.QMenu"):
                with patch("gui.tray.QAction"):
                    with patch("gui.tray.QSystemTrayIcon") as tray_cls:
                        tray_cls.return_value.show.return_value = None
                        tray = TrayController(None, window, bridge, icon_path=__file__)

    tray.show_window()
    assert calls == ["show", "raise", "activate"]
