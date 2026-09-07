.pragma library

// Per-design shape and typography tokens. A design's personality (corner radius,
// font, density, border weight) lives here so the shared widgets in
// gui/components pick it up automatically on every page, not just its Run page.
//
// Font sizes are pixel sizes and must be integers — QML truncates fractions.
//
// `flatPanels` is the one token that changes a widget's *shape* rather than its
// measurements: a PanelCard stops being a filled, bordered, rounded box and
// becomes a hairline rule under a small label. It exists so a design can be
// quiet everywhere without every page being rewritten for it — see
// components/PanelCard.qml.

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
        labelTracking: 0.08, uppercaseLabels: false, flatPanels: false
    },
    haul: {
        name: "Haul",
        description: "Icon rail that expands on hover, rounded cards, session haul beside the feed.",
        shell: "HaulShell.qml",
        defaultPalette: "kakera",
        font: SANS, mono: MONO, monoUi: false,
        radiusXs: 6, radiusSm: 8, radiusMd: 12, radiusLg: 14, radiusPill: 999,
        borderWidth: 1, doubleBorder: false,
        micro: 9, tiny: 11, small: 11, body: 13, medium: 13, large: 15, xlarge: 18, title: 24,
        controlHeight: 38, controlPadH: 16, cardPadding: 15, gap: 10,
        labelTracking: 0.15, uppercaseLabels: true, flatPanels: false
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
        labelTracking: 0.13, uppercaseLabels: true, flatPanels: false
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
        labelTracking: 0.13, uppercaseLabels: false, flatPanels: false
    },
    quiet: {
        name: "Quiet",
        description: "Text nav, no cards. A hairline rule and a small label carry every panel.",
        shell: "QuietShell.qml",
        defaultPalette: "kakera",
        font: SANS, mono: MONO, monoUi: false,
        // Radii are still defined because chips, inputs and buttons keep theirs —
        // it is the *panel* that goes flat, not every corner in the design.
        radiusXs: 3, radiusSm: 7, radiusMd: 7, radiusLg: 7, radiusPill: 999,
        borderWidth: 1, doubleBorder: false,
        micro: 9, tiny: 11, small: 12, body: 13, medium: 13, large: 15, xlarge: 16, title: 22,
        // Roomier than the others: with no card edges to separate things, space
        // is the only separator left, so it has to be worth reading as one.
        // `cardPadding` stays a real inset — plenty of widgets besides PanelCard
        // use it for their own inner margins, and zeroing it put their labels on
        // top of their own edges. A *flat* PanelCard drops its inset itself.
        controlHeight: 36, controlPadH: 16, cardPadding: 14, gap: 18,
        labelTracking: 0.16, uppercaseLabels: true, flatPanels: true
    }
};

var order = ["classic", "haul", "console", "boxed", "quiet"];

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
