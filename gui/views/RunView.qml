import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"
import "../clock.js" as Clock

Item {
    id: runRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var stateData: ({})
    property var activeRules: ({})
    property var activityEntries: []
    property var runSummary: ({})
    property double nowMs: Date.now()

    function refreshSummary() {
        try {
            runSummary = JSON.parse(App.runSummaryJson)
        } catch (e) {
            runSummary = {}
        }
    }

    function refreshActiveRules() {
        try {
            var presetData = JSON.parse(App.presetsJson)
            var id = presetData.active_preset_id
            activeRules = id ? (JSON.parse(App.getPresetRulesJson(id)) || {}) : {}
        } catch (e) {
            activeRules = {}
        }
    }

    function blockEnabled(block) {
        return !!(activeRules[block] && activeRules[block].enabled)
    }

    function refreshState() {
        try {
            stateData = JSON.parse(App.macroStateJson)
        } catch (e) {
            stateData = {}
        }
    }

    function refreshActivityLog() {
        try {
            activityEntries = JSON.parse(App.macroActivityLogJson)
        } catch (e) {
            activityEntries = []
        }
    }

    function macroIsRunning() {
        var p = App.macroPhase
        return p === "Rolling" || p === "Checking $tu" || p === "Post-roll" || p === "Stopping"
    }

    function rollsLeftText() {
        var left = App.macroRollsLeft >= 0 ? App.macroRollsLeft.toString() : "—"
        if (App.macroRollsMax > 0)
            left += "/" + App.macroRollsMax
        var us = stateData.rolls_us_bonus
        if (us !== undefined && us !== null && us > 0)
            left += " (+" + us + " $us)"
        var stacked = stateData.us_stacked
        if (stacked !== undefined && stacked !== null)
            left += " · " + stacked + " stacked"
        return left
    }

    function powerText() {
        var pct = Clock.livePowerPercent(
            stateData.power_percent,
            stateData.power_updated_at,
            stateData.power_max_percent,
            runRoot.nowMs
        )
        if (pct >= 0)
            return pct + "%"
        return "—"
    }

    function dkText() {
        if (App.macroDkStock >= 0)
            return App.macroDkStock.toString()
        return "—"
    }

    function resetText() {
        var sec = Clock.remainingSeconds(stateData.rolls_reset_at, runRoot.nowMs)
        if (sec >= 0)
            return (sec <= 0 ? 0 : Math.max(1, Math.floor(sec / 60))) + "m"
        var m = stateData.rolls_reset_minutes
        if (m !== undefined && m !== null)
            return m + "m"
        return "—"
    }

    function rollsTone() {
        return App.macroEngineRunning ? "active" : "neutral"
    }

    function claimTone() {
        var s = App.macroClaimStatus
        if (s === "can claim")
            return "good"
        if (s.indexOf("cooldown") >= 0)
            return "warn"
        return "neutral"
    }

    function powerTone() {
        var pct = Clock.livePowerPercent(
            stateData.power_percent,
            stateData.power_updated_at,
            stateData.power_max_percent,
            runRoot.nowMs
        )
        if (pct >= 0 && pct < 30)
            return "warn"
        return "neutral"
    }

    function dkTone() {
        return App.macroDkStock > 0 ? "good" : "neutral"
    }

    function syncControlBars() {
        var bars = [connectionBar, actionBar]
        for (var i = 0; i < bars.length; i++) {
            bars[i].connected = App.connected
            bars[i].macroRunning = runRoot.macroIsRunning()
            bars[i].macroEngineRunning = App.macroEngineRunning
            bars[i].notificationStandby = App.notificationStandby
            bars[i].sessionActive = App.sessionActive
        }
    }

    function refreshStatusBar() {
        statusBar.rollsValue = runRoot.rollsLeftText()
        statusBar.claimValue = App.macroClaimStatus
        statusBar.powerValue = runRoot.powerText()
        statusBar.dkValue = runRoot.dkText()
        statusBar.resetValue = runRoot.resetText()
        statusBar.phase = App.macroPhase
        statusBar.rollsTone = runRoot.rollsTone()
        statusBar.claimTone = runRoot.claimTone()
        statusBar.powerTone = runRoot.powerTone()
        statusBar.dkTone = runRoot.dkTone()
    }

    Connections {
        target: App
        function onConnectedChanged() {
            syncControlBars()
        }
        function onNotificationStandbyChanged() {
            syncControlBars()
        }
        function onSessionActiveChanged() {
            syncControlBars()
        }
        function onConfigChanged() {
            runRoot.refreshActiveRules()
            runRoot.refreshSummary()
        }
        function onMacroPhaseChanged() {
            syncControlBars()
            refreshStatusBar()
        }
        function onMacroStateChanged() {
            syncControlBars()
            runRoot.refreshState()
            runRoot.refreshSummary()
            refreshStatusBar()
        }
        function onRunSummaryChanged() {
            runRoot.refreshSummary()
        }
        function onMacroLogChanged() {
            runRoot.refreshActivityLog()
        }
    }

    Timer {
        interval: 1000
        running: App.connected
        repeat: true
        onTriggered: {
            runRoot.nowMs = Date.now()
            runRoot.refreshStatusBar()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        PanelCard {
            Layout.fillWidth: true
            title: "Session"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10

                RunTargetSelectors {
                    Layout.fillWidth: true
                    compact: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.fillWidth: true
                        text: App.runTargetLabel
                            ? App.runTargetLabel
                            : "Add an account, server channel, and preset to run."
                        color: Theme.fgMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }

                    PresetRulePill {
                        label: "Claim"
                        ruleActive: runRoot.blockEnabled("character_claim")
                    }
                    PresetRulePill {
                        label: "Kakera"
                        ruleActive: runRoot.blockEnabled("kakera_reaction")
                    }
                    PresetRulePill {
                        label: "Spheres"
                        ruleActive: runRoot.blockEnabled("sphere_reaction")
                    }
                }
            }
        }

        RunStatusBar {
            id: statusBar
            Layout.fillWidth: true
            rollsValue: runRoot.rollsLeftText()
            claimValue: App.macroClaimStatus
            powerValue: runRoot.powerText()
            dkValue: runRoot.dkText()
            resetValue: runRoot.resetText()
            phase: App.macroPhase
            rollsTone: runRoot.rollsTone()
            claimTone: runRoot.claimTone()
            powerTone: runRoot.powerTone()
            dkTone: runRoot.dkTone()
        }

        Perk8PowerSaveStatus {
            Layout.fillWidth: true
            status: runRoot.runSummary.power_save || null
        }

        Perk9AdaptiveStatus {
            Layout.fillWidth: true
            status: runRoot.runSummary.perk9_adaptive || null
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160
            spacing: 16

            PanelCard {
                title: "Controls"
                Layout.preferredWidth: 268
                Layout.maximumWidth: 288
                Layout.minimumWidth: 220
                Layout.fillWidth: false
                Layout.fillHeight: true
                fillContentVertically: true

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    MacroControlBar {
                        id: connectionBar
                        Layout.fillWidth: true
                        connectionOnly: true
                        onConnectClicked: App.connect()
                        onDisconnectClicked: App.disconnect()
                        onStopClicked: App.stopMacro()
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Theme.border
                    }

                    ScrollView {
                        id: controlsScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        MacroControlBar {
                            id: actionBar
                            width: controlsScroll.availableWidth
                            actionsOnly: true
                            onRunTuClicked: App.runTu()
                            onRunUsCheckClicked: App.runUsCheck()
                            onStartClicked: App.startMacro()
                            onStopClicked: App.stopMacro()
                            onPlayOhClicked: App.playOhSphere()
                            onPlayOcClicked: App.playOcSphere()
                            onPlayOqClicked: App.playOqSphere()
                            onPlayOtClicked: App.playOtSphere()
                            onPlayAllMinigamesClicked: App.playAllMinigames()
                            onPlayUsClicked: App.startUsMode()
                        }
                    }
                }
            }

            PanelCard {
                title: "Activity"
                fillContentVertically: true
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 260
                Layout.minimumHeight: 120

                ActivityLogPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    entries: runRoot.activityEntries
                }
            }
        }
    }

    Component.onCompleted: {
        refreshState()
        refreshActivityLog()
        refreshActiveRules()
        refreshSummary()
        syncControlBars()
        refreshStatusBar()
    }
}
