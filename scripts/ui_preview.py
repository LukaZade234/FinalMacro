"""Render the GUI offscreen to a PNG, for checking a design without running it.

    QT_QPA_PLATFORM=offscreen python3 scripts/ui_preview.py --layout haul --out /tmp/haul.png

Loads the real shells against a real AppBridge, so QML errors surface here the
same way they would in the app. Exits non-zero if QML reported any warning.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, QUrl
from PySide6.QtQuick import QQuickView
from PySide6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gui.bridge import AppBridge  # noqa: E402
from gui.fonts import load_bundled_fonts  # noqa: E402

PAGE_NAMES = [
    "run", "accounts", "servers", "presets", "mudae", "spheres", "advisor",
    "statistics", "debug", "settings",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", default="haul", choices=["classic", "haul", "console", "boxed"])
    parser.add_argument("--palette", default="kakera")
    parser.add_argument("--page", default="0")
    parser.add_argument("--out", default="/tmp/finalmacro-preview.png")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=770)
    parser.add_argument("--settle-ms", type=int, default=1200)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="seed the mockup's readings so gauges and the feed are not empty",
    )
    args = parser.parse_args()

    page = int(args.page) if args.page.isdigit() else PAGE_NAMES.index(args.page)

    app = QApplication(sys.argv)
    load_bundled_fonts()

    bridge = AppBridge()
    if args.demo:
        from scripts import preview_data

        preview_data.apply(bridge)

    view = QQuickView()
    view.engine().addImportPath(str(PROJECT_ROOT))
    view.engine().rootContext().setContextProperty("App", bridge)
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(QSize(args.width, args.height))

    problems: list[str] = []
    view.engine().warnings.connect(
        lambda errors: problems.extend(error.toString() for error in errors)
    )

    view.setSource(QUrl.fromLocalFile(str(PROJECT_ROOT / "scripts" / "preview.qml")))
    if view.status() != QQuickView.Status.Ready:
        print("FAILED to load preview.qml")
        for error in view.errors():
            print("  ", error.toString())
        return 1

    root = view.rootObject()
    root.setProperty("layoutId", args.layout)
    root.setProperty("paletteId", args.palette)
    if page:
        root.setProperty("currentPage", page)

    view.show()

    def capture() -> None:
        try:
            image = view.grabWindow()
            if image.isNull():
                print("grabWindow returned a null image")
                app.exit(1)
                return
            image.save(args.out)
            print(f"wrote {args.out} ({image.width()}x{image.height()})")
            app.exit(1 if problems else 0)
        except Exception as exc:  # never leave the event loop hanging
            print(f"capture failed: {exc!r}")
            app.exit(1)

    QTimer.singleShot(args.settle_ms, capture)
    code = app.exec()

    if problems:
        print(f"\n{len(problems)} QML warning(s):")
        for problem in dict.fromkeys(problems):
            print("  ", problem)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
