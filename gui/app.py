"""PySide6 + QML entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from gui.bridge import AppBridge
from gui.single_instance import SingleInstanceServer, raise_window, try_notify_running_instance
from gui.tray import TrayController


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FinalMacro")
    app.setDesktopFileName("finalmacro")

    if try_notify_running_instance():
        return

    project_root = Path(__file__).resolve().parent.parent
    icon_path = project_root / "assets" / "app-icon.png"
    window_icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
    if not window_icon.isNull():
        app.setWindowIcon(window_icon)

    bridge = AppBridge()
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(project_root))

    engine.rootContext().setContextProperty("App", bridge)

    qml_path = Path(__file__).resolve().parent / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        sys.exit(1)

    window = engine.rootObjects()[0]
    if not window_icon.isNull():
        set_icon = getattr(window, "setIcon", None)
        if callable(set_icon):
            set_icon(window_icon)

    tray = TrayController(
        app,
        window,
        bridge,
        icon_path=icon_path,
    )
    bridge.attach_tray(tray)

    instance_server = SingleInstanceServer()
    instance_server.listen(on_raise=lambda: (
        tray.show_window() if tray.available else raise_window(window)
    ))

    app.aboutToQuit.connect(bridge.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
