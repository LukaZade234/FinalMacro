.pragma library

// Colour themes. Adding a theme means adding one entry here — nothing else in
// the UI needs to change. Every key below is required.
//
//   bg       window background, and the background of inset inputs
//   surface  cards, bars, panels that sit on top of bg
//   raise    controls and chips that sit on top of surface
//   line     borders and dividers
//   fg       primary text
//   dim      secondary text
//   mute     labels, timestamps, disabled text
//   accent   primary brand colour (active nav, primary buttons, rolls)
//   accent2  secondary accent (kakera reactions, gradients)
//   good     success / claim ready
//   warn     caution / low power
//   bad      errors / stop
//   sphere   mudae sphere id for the app mark (spP, spB, …); follows this palette
//
// `hover` is optional; it defaults to `mute` and is only used for the hovered
// state of raised controls.

var palettes = {
    kakera: {
        name: "Kakera",
        dark: true,
        bg: "#0d0d13", surface: "#15151e", raise: "#1c1c28", line: "#272736",
        fg: "#e8e8f4", dim: "#7b7b92", mute: "#565669",
        accent: "#e8479e", accent2: "#8b6cf0",
        good: "#3ed6b8", warn: "#f2a83c", bad: "#ff5c6c",
        sphere: "spM"
    },
    tokyonight: {
        name: "Tokyo Night",
        dark: true,
        bg: "#1a1b26", surface: "#24283b", raise: "#414868", line: "#414868",
        fg: "#c0caf5", dim: "#a9b1d6", mute: "#6b7394",
        accent: "#7aa2f7", accent2: "#bb9af7",
        good: "#9ece6a", warn: "#e0af68", bad: "#f7768e",
        hover: "#565f89",
        sphere: "spB"
    },
    ember: {
        name: "Ember",
        dark: true,
        bg: "#100e0c", surface: "#171412", raise: "#211c18", line: "#2a2521",
        fg: "#efe6d8", dim: "#9d8f7d", mute: "#6b6055",
        accent: "#e8a33d", accent2: "#c9743a",
        good: "#8fc46a", warn: "#e0b155", bad: "#e5624f",
        sphere: "spY"
    },
    phosphor: {
        name: "Phosphor",
        dark: true,
        bg: "#050a06", surface: "#0a1109", raise: "#0f1a0e", line: "#1c2e1a",
        fg: "#c8f5c0", dim: "#6ea868", mute: "#43683f",
        accent: "#3ef07a", accent2: "#8ae86a",
        good: "#3ef07a", warn: "#e3d24a", bad: "#ff6b5e",
        sphere: "spG"
    },
    ice: {
        name: "Ice",
        dark: true,
        bg: "#0c1016", surface: "#131923", raise: "#1a2230", line: "#26303f",
        fg: "#e2e9f2", dim: "#8697ab", mute: "#5b6879",
        accent: "#4ec3e0", accent2: "#7d9ff0",
        good: "#5bd6a4", warn: "#e3b567", bad: "#f0768b",
        sphere: "spT"
    },
    bone: {
        name: "Bone",
        dark: false,
        bg: "#e9ebee", surface: "#f8f9fa", raise: "#dfe3e8", line: "#ccd2d9",
        fg: "#161b21", dim: "#57616c", mute: "#87919c",
        accent: "#c2185b", accent2: "#5b3fc4",
        good: "#0d8a68", warn: "#9a6510", bad: "#c1352f",
        sphere: "spR"
    },
    mono: {
        name: "Mono",
        dark: true,
        bg: "#0a0a0a", surface: "#121212", raise: "#1b1b1b", line: "#2b2b2b",
        fg: "#f2f2f2", dim: "#8d8d8d", mute: "#5e5e5e",
        accent: "#ffffff", accent2: "#b4b4b4",
        good: "#e0e0e0", warn: "#a5a5a5", bad: "#ff4d4d",
        sphere: "spD"
    }
};

var order = ["kakera", "tokyonight", "ember", "phosphor", "ice", "bone", "mono"];

function get(id) {
    return palettes[id] || palettes["kakera"];
}

// Includes a few colours per entry so the settings page can draw swatches for
// palettes other than the active one.
function list() {
    var out = [];
    for (var i = 0; i < order.length; i++) {
        var p = palettes[order[i]];
        out.push({
            id: order[i],
            name: p.name,
            bg: p.bg,
            surface: p.surface,
            line: p.line,
            accent: p.accent,
            accent2: p.accent2,
            fg: p.fg,
            sphere: p.sphere
        });
    }
    return out;
}
