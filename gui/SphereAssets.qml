pragma Singleton
import QtQuick

// Sphere button artwork lives alongside kakera assets (``Sp*.webp``).
QtObject {
    readonly property string assetBase: String(Qt.resolvedUrl("assets/kakera/"))

    readonly property var _labels: ({
        "spM": "Megasphere",
        "spP": "Purple",
        "spB": "Blue",
        "spT": "Teal",
        "spG": "Green",
        "spY": "Yellow",
        "spD": "Dark",
        "spL": "Light",
        "spO": "Orange",
        "spR": "Red",
        "sp": "Red",
        "spW": "Rainbow",
        "spU": "Hidden"
    })

    readonly property var _colors: ({
        "spM": "#ff5fa2",
        "spP": "#9d7cd8",
        "spB": "#7aa2f7",
        "spT": "#2ac3de",
        "spG": "#9ece6a",
        "spY": "#e0af68",
        "spD": "#3b4252",
        "spL": "#bb9af7",
        "spO": "#ff9e64",
        "spR": "#f7768e",
        "sp": "#f7768e",
        "spW": "#c0caf5",
        "spU": "#565f89"
    })

    // Preset chip picker — one chip per color; bare ``:sp:`` roll buttons match ``spR``.
    readonly property var options: [
        { id: "spM", label: "Megasphere", color: "#ff5fa2", icon: assetBase + "SpM.webp" },
        { id: "spP", label: "Purple",     color: "#9d7cd8", icon: assetBase + "SpP.webp" },
        { id: "spB", label: "Blue",       color: "#7aa2f7", icon: assetBase + "SpB.webp" },
        { id: "spT", label: "Teal",       color: "#2ac3de", icon: assetBase + "SpT.webp" },
        { id: "spG", label: "Green",      color: "#9ece6a", icon: assetBase + "SpG.webp" },
        { id: "spY", label: "Yellow",     color: "#e0af68", icon: assetBase + "SpY.webp" },
        { id: "spD", label: "Dark",       color: "#3b4252", icon: assetBase + "SpD.webp" },
        { id: "spL", label: "Light",      color: "#bb9af7", icon: assetBase + "SpL.webp" },
        { id: "spO", label: "Orange",     color: "#ff9e64", icon: assetBase + "SpO.webp" },
        { id: "spR", label: "Red",        color: "#f7768e", icon: assetBase + "SpR.webp" },
        { id: "spW", label: "Rainbow",    color: "#c0caf5", icon: assetBase + "SpW.webp" }
    ]

    function canonicalId(sphereId) {
        if (sphereId === undefined || sphereId === null || sphereId === "")
            return ""
        var id = String(sphereId)
        var match = id.match(/^(sp)([A-Za-z])\d+$/i)
        if (match)
            return "sp" + match[2].toUpperCase()
        return id
    }

    function iconUrl(sphereId) {
        var id = canonicalId(sphereId)
        if (!id)
            return ""
        var letter = ""
        if (id === "sp")
            letter = "R"
        else if (id.length >= 3 && id.indexOf("sp") === 0)
            letter = id.charAt(2).toUpperCase()
        else
            return ""
        return Qt.resolvedUrl("assets/kakera/Sp" + letter + ".webp")
    }

    function label(sphereId) {
        var id = canonicalId(sphereId)
        if (!id)
            return "—"
        return _labels[id] || id
    }

    function color(sphereId) {
        var id = canonicalId(sphereId)
        if (!id)
            return "#565f89"
        return _colors[id] || "#565f89"
    }
}
