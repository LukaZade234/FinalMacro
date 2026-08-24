import QtQuick

import gui 1.0

/*
    Everything the Run designs display, read from the App bridge once and
    formatted once.

    The three Run pages differ only in how they arrange this data, so all of the
    parsing, unit formatting and severity classification lives here rather than
    being repeated (and drifting) in each design.

    Values that the macro has not learned yet are reported as -1 for numbers and
    "—" for text, so a design can choose between hiding a gauge and showing a
    placeholder.
*/
Item {
    id: model

    visible: false
    width: 0
    height: 0

    // ---- raw payloads ------------------------------------------------------

    property var stateData: ({})
    property var summary: ({})
    property var activeRules: ({})
    property var entries: []

    // ---- connection --------------------------------------------------------

    readonly property bool connected: App.connected
    readonly property bool connecting: App.connecting
    readonly property bool disconnecting: App.disconnecting
    readonly property bool standby: App.notificationStandby
    readonly property bool engineRunning: App.macroEngineRunning
    readonly property bool sessionActive: App.sessionActive
    readonly property string phase: App.macroPhase
    readonly property bool macroRunning: phase === "Rolling"
        || phase === "Checking $tu"
        || phase === "Post-roll"
        || phase === "Stopping"

    readonly property string connectLabel: {
        if (connecting) return "Connecting…"
        if (disconnecting) return "Disconnecting…"
        return connected ? "Disconnect" : "Connect"
    }
    readonly property string statusLine: {
        if (connecting) return "connecting…"
        if (standby) return "standby"
        if (!connected) return "disconnected"
        return sessionElapsedText !== "" ? "connected " + sessionElapsedText : "connected"
    }

    // ---- rolls -------------------------------------------------------------

    readonly property int rollsLeft: App.macroRollsLeft
    readonly property int rollsMax: App.macroRollsMax
    readonly property int usBonus: numberOr(stateData.rolls_us_bonus, 0)
    readonly property real usStacked: numberOr(stateData.us_stacked, 0)

    readonly property string rollsText: rollsLeft >= 0
        ? (rollsMax > 0 ? rollsLeft + "/" + rollsMax : String(rollsLeft))
        : "—"
    // -1 when $settings has never been read, so the gauge has no scale.
    readonly property real rollsFraction: (rollsLeft >= 0 && rollsMax > 0)
        ? Math.min(1, rollsLeft / rollsMax)
        : -1
    readonly property string usText: {
        if (usBonus <= 0 && usStacked <= 0) return "—"
        var parts = []
        if (usBonus > 0) parts.push("+" + usBonus)
        if (usStacked > 0) parts.push(Math.round(usStacked) + " stacked")
        return parts.join(" · ")
    }

    readonly property int resetMinutes: numberOr(stateData.rolls_reset_minutes, -1)
    readonly property string resetText: resetMinutes >= 0 ? durationFromMinutes(resetMinutes) : "—"
    // Rolls refill hourly, so the reset countdown is always out of 60 minutes.
    readonly property real resetFraction: resetMinutes >= 0
        ? Math.min(1, Math.max(0, (60 - resetMinutes) / 60))
        : -1

    // ---- claim -------------------------------------------------------------

    readonly property string claimStatus: App.macroClaimStatus
    readonly property bool claimReady: claimStatus === "can claim"
    readonly property int claimCooldownMinutes: numberOr(stateData.claim_cooldown_minutes, -1)
    readonly property int nextClaimMinutes: numberOr(stateData.next_claim_reset_minutes, -1)

    readonly property string claimText: {
        if (claimStatus === "can claim") return "Ready"
        if (claimCooldownMinutes >= 0) return durationFromMinutes(claimCooldownMinutes)
        if (claimStatus === "on cooldown") return "Cooldown"
        return "—"
    }
    readonly property string nextClaimText: nextClaimMinutes >= 0
        ? durationFromMinutes(nextClaimMinutes)
        : (claimCooldownMinutes >= 0 ? durationFromMinutes(claimCooldownMinutes) : "—")
    readonly property string claimTone: claimReady ? "good" : (claimCooldownMinutes >= 0 ? "warn" : "neutral")

    // ---- power and dk ------------------------------------------------------

    readonly property int powerPercent: App.macroPowerPercent
    readonly property real powerMax: numberOr(stateData.power_max_percent, 100)
    readonly property string powerText: powerPercent >= 0 ? powerPercent + "%" : "—"
    readonly property real powerFraction: (powerPercent >= 0 && powerMax > 0)
        ? Math.min(1, powerPercent / powerMax)
        : -1
    readonly property string powerTone: powerPercent < 0 ? "neutral" : (powerPercent < 30 ? "warn" : "good")

    readonly property int dkStock: App.macroDkStock
    readonly property string dkText: dkStock >= 0 ? String(dkStock) : "—"
    readonly property int dkNextMinutes: numberOr(stateData.dk_next_minutes, -1)

    // ---- perks -------------------------------------------------------------

    readonly property var today: summary.today || ({})
    readonly property int perk8Used: numberOr(today.perk8_used, 0)
    readonly property int perk8Max: numberOr(today.perk8_max, -1)
    readonly property string perk8Text: perk8Max > 0 ? perk8Used + " / " + perk8Max : String(perk8Used)
    readonly property real perk8Fraction: perk8Max > 0 ? Math.min(1, perk8Used / perk8Max) : -1
    readonly property int perk9Today: numberOr(today.perk9_spheres, 0)

    // ---- session haul ------------------------------------------------------

    readonly property var session: summary.session || ({})
    readonly property int sessionKakera: numberOr(session.kakera, 0)
    readonly property int sessionSpheres: numberOr(session.spheres, 0)
    readonly property int sessionKeys: numberOr(session.keys, 0)
    readonly property int sessionClaims: numberOr(session.claims, 0)

    readonly property var lastClaim: summary.last_claim || null
    readonly property string lastClaimName: lastClaim ? lastClaim.character : ""
    readonly property string lastClaimDetail: lastClaim ? lastClaim.detail : ""
    readonly property string lastClaimTime: lastClaim ? lastClaim.time : ""

    property double nowMs: Date.now()
    readonly property string sessionElapsedText: {
        var started = session.started_at
        if (!connected || !started) return ""
        var startMs = Date.parse(started)
        if (isNaN(startMs)) return ""
        return durationFromSeconds(Math.max(0, (nowMs - startMs) / 1000))
    }

    // ---- preset rules ------------------------------------------------------

    readonly property bool claimRuleOn: ruleEnabled("character_claim")
    readonly property bool kakeraRuleOn: ruleEnabled("kakera_reaction")
    readonly property bool sphereRuleOn: ruleEnabled("sphere_reaction")

    // ---- activity feed -----------------------------------------------------

    property string filterKind: "all"

    readonly property var feed: decorateEntries(entries)
    readonly property var counts: countByKind(feed)
    readonly property var visibleFeed: filterKind === "all"
        ? feed
        : feed.filter(function(e) { return e.kind === model.filterKind })

    // ---- helpers -----------------------------------------------------------

    function numberOr(value, fallback) {
        if (value === undefined || value === null) return fallback
        var n = Number(value)
        return isNaN(n) ? fallback : n
    }

    function ruleEnabled(block) {
        return !!(activeRules[block] && activeRules[block].enabled)
    }

    function durationFromMinutes(minutes) {
        if (minutes < 0) return "—"
        if (minutes < 60) return Math.round(minutes) + "m"
        var h = Math.floor(minutes / 60)
        var m = Math.round(minutes % 60)
        return m > 0 ? h + "h " + m + "m" : h + "h"
    }

    function durationFromSeconds(seconds) {
        var total = Math.floor(seconds)
        var h = Math.floor(total / 3600)
        var m = Math.floor((total % 3600) / 60)
        if (h > 0) return h + "h " + m + "m"
        var s = total % 60
        return m > 0 ? m + "m " + s + "s" : s + "s"
    }

    function compact(value) {
        var n = Number(value) || 0
        if (Math.abs(n) < 10000) return n.toLocaleString(Qt.locale(), "f", 0)
        if (Math.abs(n) < 1000000) return (n / 1000).toFixed(n < 100000 ? 1 : 0) + "k"
        return (n / 1000000).toFixed(1) + "M"
    }

    // The activity log only carries a coarse severity, but the designs colour
    // commands differently from ordinary lines, so commands are recognised here.
    function classify(entry) {
        var severity = entry.severity || "info"
        if (severity === "error") return "error"
        if (severity === "claim") return "claim"
        if (severity === "click") return "kakera"
        if (severity === "skip") return "skip"
        var text = String(entry.text || "")
        if (/^(sent|checked|playing|running)\s+\$/i.test(text) || /\$\w+/.test(text.split(" ")[0]))
            return "cmd"
        return "info"
    }

    function glyphFor(kind) {
        switch (kind) {
        case "cmd": return "$"
        case "claim": return "★"
        case "kakera": return "◆"
        case "error": return "!"
        default: return "·"
        }
    }

    function colorFor(kind) {
        switch (kind) {
        case "claim": return Theme.good
        case "kakera": return Theme.accent2
        case "error": return Theme.bad
        case "cmd": return Theme.accent
        case "skip": return Theme.mute
        default: return Theme.dim
        }
    }

    function timeOf(entry) {
        if (!entry.ts) return ""
        var ms = Date.parse(entry.ts)
        if (isNaN(ms)) return ""
        return Qt.formatTime(new Date(ms), "HH:mm:ss")
    }

    function decorateEntries(list) {
        var out = []
        for (var i = 0; i < list.length; i++) {
            var entry = list[i]
            var kind = classify(entry)
            out.push({
                text: String(entry.text || ""),
                kind: kind,
                glyph: glyphFor(kind),
                time: timeOf(entry)
            })
        }
        return out
    }

    function countByKind(list) {
        var out = { all: list.length, claim: 0, kakera: 0, skip: 0, error: 0, cmd: 0, info: 0 }
        for (var i = 0; i < list.length; i++)
            out[list[i].kind] = (out[list[i].kind] || 0) + 1
        return out
    }

    // ---- loading -----------------------------------------------------------

    function reloadState() {
        stateData = parseJson(App.macroStateJson, {})
    }

    function reloadSummary() {
        summary = parseJson(App.runSummaryJson, {})
    }

    function reloadFeed() {
        entries = parseJson(App.macroActivityLogJson, [])
    }

    function reloadRules() {
        var presets = parseJson(App.presetsJson, {})
        var id = presets.active_preset_id
        activeRules = id ? parseJson(App.getPresetRulesJson(id), {}) : {}
    }

    function parseJson(text, fallback) {
        try {
            var parsed = JSON.parse(text)
            return parsed === null ? fallback : parsed
        } catch (e) {
            return fallback
        }
    }

    Connections {
        target: App
        function onMacroStateChanged() { model.reloadState() }
        function onMacroLogChanged() { model.reloadFeed() }
        function onRunSummaryChanged() { model.reloadSummary() }
        function onConfigChanged() { model.reloadRules() }
        function onConnectedChanged() { model.reloadSummary() }
    }

    Timer {
        interval: 1000
        running: model.connected
        repeat: true
        onTriggered: model.nowMs = Date.now()
    }

    Component.onCompleted: {
        reloadState()
        reloadSummary()
        reloadFeed()
        reloadRules()
    }
}
