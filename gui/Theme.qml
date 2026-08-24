pragma Singleton

import QtQuick

import "palettes.js" as Palettes
import "skins.js" as Skins

/*
    Design tokens for the whole app.

    Two independent axes:
      paletteId  which set of colours to use   (gui/palettes.js)
      layoutId   which design/shell to render  (gui/skins.js)

    Main.qml keeps both in sync with the persisted App.uiPalette / App.uiLayout
    settings, so nothing else needs to know where the values came from.

    Colours are exposed under semantic names (bg/surface/accent/...). The
    bgDark/bgMedium/... aliases further down are the original names from before
    theming existed; they map onto the same values and are kept so the existing
    views keep working.
*/
QtObject {
    id: theme

    property string paletteId: "tokyonight"
    property string layoutId: "classic"
    property bool systemFonts: false
    property string systemFontFamily: ""

    readonly property var colors: Palettes.get(paletteId)
    readonly property var shape: Skins.get(layoutId)

    readonly property var paletteList: Palettes.list()
    readonly property var layoutList: Skins.list()
    readonly property string shellSource: shape.shell
    readonly property bool darkPalette: colors.dark

    // ---- colours -----------------------------------------------------------

    readonly property color bg: colors.bg
    readonly property color surface: colors.surface
    readonly property color raised: colors.raise
    readonly property color line: colors.line
    readonly property color fg: colors.fg
    readonly property color dim: colors.dim
    readonly property color mute: colors.mute
    readonly property color hover: colors.hover !== undefined ? colors.hover : colors.mute
    readonly property color accent: colors.accent
    readonly property color accent2: colors.accent2
    readonly property color good: colors.good
    readonly property color warn: colors.warn
    readonly property color bad: colors.bad

    // Original token names, kept as aliases for the pre-theming views.
    readonly property color bgDark: bg
    readonly property color bgMedium: surface
    readonly property color bgLight: raised
    readonly property color bgHover: hover
    readonly property color fgPrimary: fg
    readonly property color fgSecondary: dim
    readonly property color fgMuted: mute
    readonly property color accentPrimary: accent
    readonly property color accentSecondary: accent2
    readonly property color success: good
    readonly property color warning: warn
    readonly property color error: bad
    readonly property color border: line
    readonly property color inputBg: bg

    // App mark: mudae sphere whose colour follows the active palette.
    readonly property string markSphereId: colors.sphere || "spP"

    // ---- typography --------------------------------------------------------

    readonly property string fontFamily: systemFonts
        ? (systemFontFamily || shape.font) : shape.font
    readonly property string monoFamily: systemFonts
        ? (systemFontFamily || shape.mono) : shape.mono
    // True for the designs that are monospace throughout, so a component can
    // skip its own mono override rather than switching to a second font.
    readonly property bool monoUi: systemFonts ? false : shape.monoUi

    readonly property int sizeMicro: shape.micro
    readonly property int sizeTiny: shape.tiny
    readonly property int sizeSmall: shape.small
    readonly property int sizeBody: shape.body
    readonly property int sizeMedium: shape.medium
    readonly property int sizeLarge: shape.large
    readonly property int sizeXLarge: shape.xlarge
    readonly property int sizeTitle: shape.title

    // ---- shape and density -------------------------------------------------

    readonly property int radiusXs: shape.radiusXs
    readonly property int radiusSm: shape.radiusSm
    readonly property int radiusMd: shape.radiusMd
    readonly property int radiusLg: shape.radiusLg
    readonly property int radiusPill: shape.radiusPill
    readonly property int borderWidth: shape.borderWidth
    readonly property bool doubleBorder: shape.doubleBorder

    readonly property int controlHeight: shape.controlHeight
    readonly property int controlPadH: shape.controlPadH
    readonly property int cardPadding: shape.cardPadding
    readonly property int gap: shape.gap
    readonly property bool uppercaseLabels: shape.uppercaseLabels

    // ---- helpers -----------------------------------------------------------

    // CSS `color-mix(in srgb, X n%, transparent)`.
    function fade(base, amount) {
        var c = Qt.color(base)
        return Qt.rgba(c.r, c.g, c.b, amount)
    }

    // CSS `color-mix(in srgb, top n%, bottom)` — an opaque blend.
    function blend(top, bottom, amount) {
        var a = Qt.color(top)
        var b = Qt.color(bottom)
        var rest = 1 - amount
        return Qt.rgba(a.r * amount + b.r * rest,
                       a.g * amount + b.g * rest,
                       a.b * amount + b.b * rest,
                       1)
    }

    // CSS letter-spacing is in em; QML wants pixels.
    function tracking(pixelSize) {
        return pixelSize * shape.labelTracking
    }

    // Section headers are uppercase in some designs and sentence case in others.
    function sectionLabel(text) {
        return shape.uppercaseLabels ? text.toUpperCase() : text
    }
}
