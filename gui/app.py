"""PySide6 + QML entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from gui.bridge import AppBridge
from gui.tray import TrayController


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FinalMacro")

    bridge = AppBridge()
    engine = QQmlApplicationEngine()

    project_root = Path(__file__).resolve().parent.parent
    engine.addImportPath(str(project_root))

    engine.rootContext().setContextProperty("App", bridge)

    qml_path = Path(__file__).resolve().parent / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        sys.exit(1)

    window = engine.rootObjects()[0]
    tray = TrayController(
        app,
        window,
        bridge,
        icon_path=project_root / "assets" / "app-icon.png",
    )
    bridge.attach_tray(tray)

    app.aboutToQuit.connect(bridge.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
