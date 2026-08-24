.pragma library

// Per-design shape and typography tokens. A design's personality (corner radius,
// font, density, border weight) lives here so the shared widgets in
// gui/components pick it up automatically on every page, not just its Run page.
//
// Font sizes are pixel sizes and must be integers — QML truncates fractions.

var SANS = "Space Grotesk";
var MONO = "IBM Plex Mono";

var skins = {
    classic: {
        name: "Classic",
        description: "The original sidebar layout.",
        shell: "ClassicShell.qml",
        defaultPalette: "tokyonight",
        font: SANS, mono: MONO, monoUi: false,
        radiusXs: 4, radiusSm: 6, radiusMd: 8, radiusLg: 10, radiusPill: 999,
        borderWidth: 1, doubleBorder: false,
        micro: 10, tiny: 10, small: 11, body: 12, medium: 13, large: 14, xlarge: 16, title: 24,
        controlHeight: 34, controlPadH: 14, cardPadding: 15, gap: 12,
        labelTracking: 0.08, uppercaseLabels: false
    },
    haul: {
        name: "Haul",
        description: "Icon rail, rounded cards, session haul beside the feed.",
        shell: "HaulShell.qml",
        defaultPalette: "kakera",
        font: SANS, mono: MONO, monoUi: false,
        radiusXs: 6, radiusSm: 8, radiusMd: 12, radiusLg: 14, radiusPill: 999,
        borderWidth: 1, doubleBorder: false,
        micro: 9, tiny: 11, small: 11, body: 13, medium: 13, large: 15, xlarge: 18, title: 24,
        controlHeight: 38, controlPadH: 16, cardPadding: 15, gap: 10,
        labelTracking: 0.15, uppercaseLabels: true
    },
    console: {
        name: "Console",
        description: "Monospace terminal with a tab bar and a command bar.",
        shell: "ConsoleShell.qml",
        defaultPalette: "kakera",
        font: MONO, mono: MONO, monoUi: true,
        radiusXs: 2, radiusSm: 3, radiusMd: 4, radiusLg: 5, radiusPill: 4,
        borderWidth: 1, doubleBorder: false,
        micro: 10, tiny: 11, small: 12, body: 13, medium: 13, large: 14, xlarge: 16, title: 20,
        controlHeight: 34, controlPadH: 13, cardPadding: 13, gap: 10,
        labelTracking: 0.13, uppercaseLabels: true
    },
    boxed: {
        name: "Boxed",
        description: "Menu bar, double-ruled boxes and a status line.",
        shell: "BoxedShell.qml",
        defaultPalette: "kakera",
        font: MONO, mono: MONO, monoUi: true,
        radiusXs: 0, radiusSm: 0, radiusMd: 0, radiusLg: 0, radiusPill: 0,
        borderWidth: 3, doubleBorder: true,
        micro: 9, tiny: 11, small: 12, body: 13, medium: 13, large: 14, xlarge: 16, title: 20,
        controlHeight: 36, controlPadH: 15, cardPadding: 14, gap: 11,
        labelTracking: 0.13, uppercaseLabels: false
    }
};

var order = ["classic", "haul", "console", "boxed"];

function get(id) {
    return skins[id] || skins["classic"];
}

function list() {
    var out = [];
    for (var i = 0; i < order.length; i++) {
        var skin = skins[order[i]];
        out.push({ id: order[i], name: skin.name, description: skin.description });
    }
    return out;
}
