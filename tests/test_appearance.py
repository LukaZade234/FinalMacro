"""The appearance allowlists in Python must match the ones QML offers.

Settings lists designs and palettes from `gui/skins.js` / `gui/palettes.js` on
the QML side, while `gui/bridge.py` decides which of them may be *stored*. The
two are separate lists with nothing linking them, so a design added to one and
not the other is offered in the UI and then silently refused — which is exactly
what happened when the Quiet shell shipped: picking it did nothing at all, with
no error anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

from gui.bridge import (
    _DEFAULT_UI_LAYOUT,
    _DEFAULT_UI_PALETTE,
    _LAYOUT_PALETTE,
    _UI_LAYOUTS,
    _UI_PALETTES,
)

GUI = Path(__file__).resolve().parent.parent / "gui"

_ORDER_RE = re.compile(r"var\s+order\s*=\s*\[(.*?)\]", re.DOTALL)
_KEY_RE = re.compile(r'"([a-z0-9_]+)"')


def _skin_ids() -> set[str]:
    """The design ids `Skins.list()` puts in the Settings picker."""
    match = _ORDER_RE.search((GUI / "skins.js").read_text())
    assert match, "gui/skins.js has no `var order = [...]`"
    return set(_KEY_RE.findall(match.group(1)))


def _palette_ids() -> set[str]:
    match = _ORDER_RE.search((GUI / "palettes.js").read_text())
    assert match, "gui/palettes.js has no `var order = [...]`"
    return set(_KEY_RE.findall(match.group(1)))


def test_every_design_the_ui_offers_can_be_stored():
    assert _skin_ids() == set(_UI_LAYOUTS)


def test_every_palette_the_ui_offers_can_be_stored():
    assert _palette_ids() == set(_UI_PALETTES)


def test_every_design_has_a_shell_file_to_load():
    """`skins.js` names a shell per design; a typo there is a blank window."""
    text = (GUI / "skins.js").read_text()
    for shell in re.findall(r'shell:\s*"([^"]+)"', text):
        assert (GUI / "shells" / shell).is_file(), f"missing gui/shells/{shell}"


def test_the_shell_switcher_knows_every_design():
    """`ShellSwitcher` maps a layout id to a component; a design it does not
    name falls through to Classic, which looks like the picker being ignored."""
    text = (GUI / "shells" / "ShellSwitcher.qml").read_text()
    named = set(re.findall(r'case\s+"([a-z0-9_]+)"\s*:', text))
    # The default arm covers exactly one design, so every *other* one is cased.
    assert named == set(_UI_LAYOUTS) - {_DEFAULT_UI_LAYOUT}


def test_every_design_starts_on_a_palette_that_exists():
    for layout, palette in _LAYOUT_PALETTE.items():
        assert layout in _UI_LAYOUTS, f"{layout} has a default palette but is not a design"
        assert palette in _UI_PALETTES, f"{layout} defaults to unknown palette {palette}"
    # Every design needs one, or picking it leaves the previous design's colours.
    assert set(_LAYOUT_PALETTE) == set(_UI_LAYOUTS)


def test_the_defaults_are_themselves_valid():
    assert _DEFAULT_UI_LAYOUT in _UI_LAYOUTS
    assert _DEFAULT_UI_PALETTE in _UI_PALETTES


def test_the_preview_script_can_render_every_design():
    """`scripts/ui_preview.py` is how a shell is checked; a design it does not
    accept cannot be screenshotted, so it never gets reviewed."""
    text = (Path(__file__).resolve().parent.parent / "scripts" / "ui_preview.py").read_text()
    match = re.search(r'"--layout".*?choices=\[(.*?)\]', text, re.DOTALL)
    assert match, "ui_preview.py no longer declares --layout choices"
    assert set(_KEY_RE.findall(match.group(1))) == set(_UI_LAYOUTS)
