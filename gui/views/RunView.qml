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
        return base
    }

    function powerText() {
        if (App.macroPowerPercent >= 0)
            return App.macroPowerPercent + "%"
        return "—"
    }

    function resetText() {
        var m = stateData.rolls_reset_minutes
        if (m !== undefined && m !== null)
            return m + "m"
        return "—"
    }

    Connections {
        target: App
        function onConnectedChanged() {
            controlBar.connected = App.connected
        }
        function onConfigChanged() {
            runRoot.refreshActiveRules()
        }
        function onMacroPhaseChanged() {
            controlBar.macroRunning = runRoot.macroIsRunning()
            phaseStepper.currentPhase = App.macroPhase
        }
        function onMacroStateChanged() {
            runRoot.refreshState()
            rollsChip.value = runRoot.rollsLeftText()
            claimChip.value = App.macroClaimStatus
            powerChip.value = runRoot.powerText()
            resetChip.value = runRoot.resetText()
        }
        function onMacroLogChanged() {
            runRoot.refreshActivityLog()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        PanelCard {
            Layout.fillWidth: true
            title: "Run target"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6

                RunTargetSelectors {
                    Layout.fillWidth: true
                }

                Label {
                    Layout.fillWidth: true
                    text: App.runTargetLabel
                        ? App.runTargetLabel
                        : "Add an account (Accounts), channels (Servers), and a preset (Presets)."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            StatusChip {
                id: rollsChip
                label: "Rolls"
                value: runRoot.rollsLeftText()
            }
            StatusChip {
                id: claimChip
                label: "Claim"
                value: App.macroClaimStatus
            }
            StatusChip {
                id: powerChip
                label: "Power"
                value: runRoot.powerText()
            }
            StatusChip {
                id: resetChip
                label: "Reset"
                value: runRoot.resetText()
            }
            Item { Layout.fillWidth: true }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 560
            spacing: 16

            ColumnLayout {
                Layout.preferredWidth: 340
                Layout.maximumWidth: 380
                Layout.fillWidth: false
                Layout.fillHeight: true
                spacing: 12

                PanelCard {
                    title: "Controls"
                    Layout.fillWidth: true

                    MacroControlBar {
                        id: controlBar
                        Layout.fillWidth: true
                        connected: App.connected
                        macroRunning: runRoot.macroIsRunning()
                        onConnectClicked: App.connect()
                        onDisconnectClicked: App.disconnect()
                        onRunTuClicked: App.runTu()
                        onStartClicked: App.startMacro()
                        onStopClicked: App.stopMacro()
                        onPlayOhClicked: App.playOhSphere()
                        onPlayOcClicked: App.playOcSphere()
                        onPlayOqClicked: App.playOqSphere()
                        onPlayUsClicked: App.startUsMode()
                    }
                }

                PanelCard {
                    title: "Preset"
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Repeater {
                            model: [
                                { label: "Character claim", block: "character_claim" },
                                { label: "Kakera reaction", block: "kakera_reaction" },
                                { label: "Sphere reaction", block: "sphere_reaction" }
                            ]
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: runRoot.blockEnabled(modelData.block) ? Theme.success : Theme.bgHover
                                }
                                Label {
                                    text: modelData.label
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: runRoot.blockEnabled(modelData.block) ? "On" : "Off"
                                    color: runRoot.blockEnabled(modelData.block) ? Theme.success : Theme.fgMuted
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: "Edit these under Presets. The active preset is selected above."
                            color: Theme.fgMuted
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                PanelCard {
                    title: "Pipeline"
                    Layout.fillWidth: true

                    PhaseStepper {
                        id: phaseStepper
                        Layout.fillWidth: true
                        currentPhase: App.macroPhase
                    }
                }

                PanelCard {
                    title: "Activity"
                    fillContentVertically: true
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 420

                    ActivityLogPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        entries: runRoot.activityEntries
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        refreshState()
        refreshActivityLog()
        refreshActiveRules()
        controlBar.connected = App.connected
        controlBar.macroRunning = macroIsRunning()
        phaseStepper.currentPhase = App.macroPhase
    }
}
