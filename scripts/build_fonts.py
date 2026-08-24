"""Generate the static Space Grotesk weights the QML themes use.

Space Grotesk ships as a single variable font whose default instance is Light,
and Qt will not interpolate ``font.weight`` across a variable axis, so every
label would render thin. Instancing the ``wght`` axis up front gives Qt four
real families to match against.

Run after replacing ``gui/fonts/SpaceGrotesk.ttf``; the generated files are
committed so the app has no build step.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONT_DIR = Path(__file__).resolve().parent.parent / "gui" / "fonts"
VARIABLE_SOURCE = FONT_DIR / "SpaceGrotesk.ttf"

WEIGHTS = {
    "Regular": 400,
    "Medium": 500,
    "SemiBold": 600,
    "Bold": 700,
}


NAME_IDS = (1, 2, 3, 4, 6, 16, 17)


def build_instance(style: str, weight: int) -> Path:
    font = TTFont(VARIABLE_SOURCE)
    # updateFontNames needs a STAT axis value per weight and Space Grotesk only
    # declares a few, so name records are rewritten by hand below instead.
    instancer.instantiateVariableFont(font, {"wght": weight}, inplace=True, updateFontNames=False)

    # Every instance must report the same family with the weight carried by
    # usWeightClass, otherwise Qt sees four unrelated families and
    # ``font.weight`` silently falls back to the default instance.
    name_table = font["name"]
    name_table.names = [n for n in name_table.names if n.nameID not in NAME_IDS]
    for platform_id, encoding_id, language_id in ((3, 1, 0x409), (1, 0, 0)):
        name_table.setName("Space Grotesk", 1, platform_id, encoding_id, language_id)
        name_table.setName(style, 2, platform_id, encoding_id, language_id)
        name_table.setName(f"SpaceGrotesk-{style}-FinalMacro", 3, platform_id, encoding_id, language_id)
        name_table.setName(f"Space Grotesk {style}", 4, platform_id, encoding_id, language_id)
        name_table.setName(f"SpaceGrotesk-{style}", 6, platform_id, encoding_id, language_id)
        name_table.setName("Space Grotesk", 16, platform_id, encoding_id, language_id)
        name_table.setName(style, 17, platform_id, encoding_id, language_id)

    os2 = font["OS/2"]
    os2.usWeightClass = weight
    # fsSelection bit 5 = BOLD, bit 6 = REGULAR; they must not both be set.
    os2.fsSelection &= ~((1 << 5) | (1 << 6))
    if weight >= 700:
        os2.fsSelection |= 1 << 5
        font["head"].macStyle |= 1
    else:
        os2.fsSelection |= 1 << 6
        font["head"].macStyle &= ~1

    out_path = FONT_DIR / f"SpaceGrotesk-{style}.ttf"
    font.save(out_path)
    font.close()
    return out_path


def main() -> int:
    if not VARIABLE_SOURCE.exists():
        raise SystemExit(f"missing variable source font: {VARIABLE_SOURCE}")

    for style, weight in WEIGHTS.items():
        path = build_instance(style, weight)
        print(f"wrote {path.name} ({path.stat().st_size // 1024} KB, wght={weight})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
