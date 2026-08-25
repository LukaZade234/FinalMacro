pragma Singleton
import QtQuick
import gui 1.0

// Kakera, sphere, soul-key, starwish, and BKU artwork under ``gui/assets/kakera/``.
// Live-feed ``:kakeraO:`` / ``:spY:`` / ``:chaoskey:`` / ``:starwish:`` / ``:bku:``
// tokens resolve here. ``feedHtml`` also tints amounts and claim status.
QtObject {
    readonly property string assetBase: String(Qt.resolvedUrl("assets/kakera/"))

    readonly property var _kakeraFile: ({
        "kakera": "Kakera.png",
        "kakerap": "KakeraP.png",
        "kakerat": "KakeraT.png",
        "kakerag": "KakeraG.png",
        "kakeray": "KakeraY.png",
        "kakerao": "KakeraO.png",
        "kakerar": "KakeraR.png",
        "kakeraw": "KakeraW.png",
        "kakeral": "KakeraL.png",
        "kakerad": "KakeraD.webp",
        "kakerac": "KakeraC.webp"
    })

    readonly property var _keyFile: ({
        "bronze": "BronzeSoulKey.webp",
        "bronzekey": "BronzeSoulKey.webp",
        "silver": "SilverSoulKey.webp",
        "silverkey": "SilverSoulKey.webp",
        "gold": "GoldSoulKey.webp",
        "goldkey": "GoldSoulKey.webp",
        "chaos": "ChaosSoulKey.webp",
        "chaoskey": "ChaosSoulKey.webp",
        "omega": "OmegaSoulKey.webp",
        "omegakey": "OmegaSoulKey.webp"
    })

    readonly property var _markFile: ({
        "starwish": "Starwish.webp",
        "sw": "Starwish.webp",
        "bku": "BKU.webp"
    })

    function _tokenId(name) {
        return String(name || "").replace(/:/g, "").toLowerCase()
    }

    function kakeraUrl(kakeraId) {
        var file = _kakeraFile[_tokenId(kakeraId)]
        return file ? assetBase + file : ""
    }

    function keyUrl(keyType) {
        var file = _keyFile[_tokenId(keyType)]
        return file ? assetBase + file : ""
    }

    function sphereUrl(sphereId) {
        var id = _tokenId(sphereId)
        if (!id)
            return ""
        var letter = ""
        if (id === "sp")
            letter = "R"
        else if (id.indexOf("sp") === 0 && id.length >= 3)
            letter = id.charAt(2).toUpperCase()
        else
            return ""
        return assetBase + "Sp" + letter + ".webp"
    }

    function urlFor(name) {
        var id = _tokenId(name)
        if (!id)
            return ""
        if (_kakeraFile[id])
            return assetBase + _kakeraFile[id]
        if (_keyFile[id])
            return assetBase + _keyFile[id]
        if (_markFile[id])
            return assetBase + _markFile[id]
        return sphereUrl(id)
    }

    // Mix a semantic colour into primary text so highlights read as a tint,
    // not a neon chip, and still follow the active palette.
    function ink(semantic) {
        return Theme.blend(semantic, Theme.fg, 0.52)
    }

    function _escape(text) {
        return String(text || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
    }

    function cssColor(c) {
        var x = Qt.color(c)
        function hex(n) {
            var v = Math.round(Math.max(0, Math.min(1, n)) * 255)
            var s = v.toString(16)
            return s.length < 2 ? "0" + s : s
        }
        return "#" + hex(x.r) + hex(x.g) + hex(x.b)
    }

    function _span(color, inner) {
        return '<span style="color:' + cssColor(color) + '">' + inner + '</span>'
    }

    function _replaceAll(str, re, replacer) {
        re.lastIndex = 0
        var out = ""
        var last = 0
        var m = re.exec(str)
        while (m !== null) {
            out += str.substring(last, m.index)
            out += replacer(m)
            last = m.index + m[0].length
            if (m[0].length === 0)
                break
            m = re.exec(str)
        }
        out += str.substring(last)
        return out
    }

    function colorize(escaped) {
        var s = escaped
        var ka = ink(Theme.accent2)
        var sp = ink(Theme.accent)
        var ok = ink(Theme.good)
        var warn = ink(Theme.warn)
        var mute = Theme.mute
        var fg = Theme.fg
        var cmd = ink(Theme.accent)

        s = _replaceAll(s, /[0-9][0-9,]* ka\b/g, function(m) {
            return _span(ka, m[0])
        })
        s = _replaceAll(s, /\+[0-9][0-9,]*(?=\s*\(\$k\))/g, function(m) {
            return _span(ka, m[0])
        })
        s = _replaceAll(s, /\+[0-9][0-9,]*(?=\s*\(\d+\/\d+\))/g, function(m) {
            return _span(sp, m[0])
        })
        s = _replaceAll(s, /:bku: (\+[0-9][0-9,]*)/g, function(m) {
            return ":bku: " + _span(warn, m[1])
        })
        s = _replaceAll(s, /:omegakey: (\+[0-9][0-9,]*)/g, function(m) {
            return ":omegakey: " + _span(ka, m[1])
        })
        s = _replaceAll(s, /\bunclaimed\b/g, function(m) {
            return _span(ok, m[0])
        })
        s = _replaceAll(s, /\bbelongs to [^·<]+/g, function(m) {
            return _span(mute, m[0])
        })
        s = _replaceAll(s, /^Claimed (.+?)(?=\s*\(|$)/g, function(m) {
            return "Claimed " + _span(ok, m[1])
        })
        s = _replaceAll(s, /^(Roll \d+: )(\$\w+)/g, function(m) {
            return _span(mute, m[1]) + _span(cmd, m[2])
        })
        s = _replaceAll(s, /\bwish×\d+/g, function(m) {
            return _span(warn, m[0])
        })

        // Character name on a roll card (before the first separator, with a ka total).
        if (s.indexOf(" ka") !== -1 || s.indexOf(":kakera") !== -1) {
            var cut = s.indexOf(" · ")
            if (cut > 0 && s.indexOf("<") !== 0) {
                var nameColor = s.indexOf("unclaimed") !== -1 ? ok : fg
                s = _span(nameColor, s.substring(0, cut)) + s.substring(cut)
            }
        }
        return s
    }

    function toHtml(text, size) {
        var px = size || 16
        var str = String(text || "")
        var re = /:([A-Za-z][A-Za-z0-9]*):/g
        var out = ""
        var last = 0
        var m = re.exec(str)
        while (m !== null) {
            out += str.substring(last, m.index)
            var url = urlFor(m[1])
            out += url
                ? ('<img src="' + url + '" width="' + px + '" height="' + px + '" />')
                : m[0]
            last = m.index + m[0].length
            m = re.exec(str)
        }
        out += str.substring(last)
        return out
    }

    function feedHtml(text, size, tint) {
        var escaped = _escape(text)
        if (tint === false)
            return toHtml(escaped, size)
        return toHtml(colorize(escaped), size)
    }
}
