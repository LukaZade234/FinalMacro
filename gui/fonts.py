"""Register the bundled UI fonts with Qt.

The QML designs ask for "Space Grotesk" and "IBM Plex Mono" by family name. Qt
only knows those families once the .ttf files are registered, which has to
happen before the QML engine loads anything, so this runs from gui/app.py at
startup. If a file is missing the app still runs — Qt falls back to a default
sans/monospace face.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Space Grotesk also ships as a variable font (SpaceGrotesk.ttf), which is kept
# around only as the source for scripts/build_fonts.py. Loading it here would
# register a second "Space Grotesk" whose default instance is Light and let Qt
# match against it, so only the generated static weights are listed.
BUNDLED_FONTS = (
    "SpaceGrotesk-Regular.ttf",
    "SpaceGrotesk-Medium.ttf",
    "SpaceGrotesk-SemiBold.ttf",
    "SpaceGrotesk-Bold.ttf",
    "IBMPlexMono-Regular.ttf",
    "IBMPlexMono-SemiBold.ttf",
)


def load_bundled_fonts() -> list[str]:
    """Register the bundled fonts and return the family names Qt accepted."""
    families: list[str] = []
    for name in BUNDLED_FONTS:
        path = FONT_DIR / name
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    return families
