import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

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
        var base = App.macroRollsLeft >= 0 ? App.macroRollsLeft.toString() : "—"
        var us = stateData.rolls_us_bonus
        if (us !== undefined && us !== null && us > 0)
            base += " (+" + us + " $us)"
        var stacked = stateData.us_stacked
        if (stacked !== undefined && stacked !== null)
            base += " · " + stacked + " stacked"
        return base
    }

    function powerText() {
        if (App.macroPowerPercent >= 0)
            return App.macroPowerPercent + "%"
        return "—"
    }

    function dkText() {
        if (App.macroDkStock >= 0)
            return App.macroDkStock.toString()
        return "—"
    }

    function resetText() {
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
        if (App.macroPowerPercent >= 0 && App.macroPowerPercent < 30)
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
        }
        function onMacroPhaseChanged() {
            syncControlBars()
            refreshStatusBar()
        }
        function onMacroStateChanged() {
            syncControlBars()
            runRoot.refreshState()
            refreshStatusBar()
        }
        function onMacroLogChanged() {
            runRoot.refreshActivityLog()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        UpdateBanner {
            Layout.fillWidth: true
        }

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
                        enabled: runRoot.blockEnabled("character_claim")
                    }
                    PresetRulePill {
                        label: "Kakera"
                        enabled: runRoot.blockEnabled("kakera_reaction")
                    }
                    PresetRulePill {
                        label: "Spheres"
                        enabled: runRoot.blockEnabled("sphere_reaction")
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

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 320
            spacing: 16

            PanelCard {
                title: "Controls"
                Layout.preferredWidth: 268
                Layout.maximumWidth: 288
                Layout.minimumWidth: 220
                Layout.fillWidth: false
                Layout.alignment: Qt.AlignTop

                ColumnLayout {
                    Layout.fillWidth: true
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

                    MacroControlBar {
                        id: actionBar
                        Layout.fillWidth: true
                        actionsOnly: true
                        onRunTuClicked: App.runTu()
                        onRunUsCheckClicked: App.runUsCheck()
                        onStartClicked: App.startMacro()
                        onStopClicked: App.stopMacro()
                        onPlayOhClicked: App.playOhSphere()
                        onPlayOcClicked: App.playOcSphere()
                        onPlayOqClicked: App.playOqSphere()
                        onPlayAllMinigamesClicked: App.playAllMinigames()
                        onPlayUsClicked: App.startUsMode()
                    }
                }
            }

            PanelCard {
                title: "Activity"
                Layout.fillWidth: true
                Layout.preferredHeight: 360
                Layout.minimumHeight: 200
                Layout.minimumWidth: 260

                ActivityLogPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 300
                    Layout.minimumHeight: 160
                    entries: runRoot.activityEntries
                }
            }
        }
    }

    Component.onCompleted: {
        refreshState()
        refreshActivityLog()
        refreshActiveRules()
        syncControlBars()
        refreshStatusBar()
    }
}
