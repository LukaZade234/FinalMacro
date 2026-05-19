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

    function refreshState() {
        try {
            stateData = JSON.parse(App.macroStateJson)
        } catch (e) {
            stateData = {}
        }
    }

    function macroIsRunning() {
        var p = App.macroPhase
        return p === "Rolling" || p === "Checking $tu" || p === "Post-roll" || p === "Stopping"
    }

    function rollsLeftText() {
        if (App.macroRollsLeft >= 0)
            return App.macroRollsLeft.toString()
        return "—"
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
        function onMacroPhaseChanged() {
            controlBar.macroRunning = runRoot.macroIsRunning()
            phaseChip.value = App.macroPhase
            phaseChip.highlighted = runRoot.macroIsRunning()
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
            activityLog.text = App.macroActivityLog || "No activity yet."
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: 12

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
                id: phaseChip
                label: "Phase"
                value: App.macroPhase
                highlighted: runRoot.macroIsRunning()
            }
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
            Layout.fillHeight: true
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
                    }
                }

                PanelCard {
                    title: "Preset"
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Label {
                        Layout.fillWidth: true
                        text: "Roll/claim options are edited under Presets. The active preset is selected above."
                        color: Theme.fgMuted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
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
                    Layout.minimumHeight: 160

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        TextArea {
                            id: activityLog
                            readOnly: true
                            wrapMode: TextArea.Wrap
                            color: Theme.fgSecondary
                            font.family: "Consolas, monospace"
                            font.pixelSize: 11
                            text: App.macroActivityLog || "No activity yet."
                            background: Rectangle {
                                radius: 6
                                color: Theme.bgDark
                                border.color: Theme.border
                            }
                        }
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        refreshState()
        controlBar.connected = App.connected
        controlBar.macroRunning = macroIsRunning()
        phaseStepper.currentPhase = App.macroPhase
        activityLog.text = App.macroActivityLog || "No activity yet."
    }
}
