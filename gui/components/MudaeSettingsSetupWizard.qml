import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Dialog {
    id: wizard
    modal: true
    title: "New server setup"
    standardButtons: Dialog.NoButton
    width: 520
    height: 420

    property string channelProfileId: ""
    property string presetId: ""
    property int step: 0

    function refreshDiff() {
        if (!channelProfileId || !presetId)
            return
        try {
            diffBox.text = App.diffMudaeSettingsPreset(channelProfileId, presetId)
        } catch (e) {
            diffBox.text = "{}"
        }
    }

    onOpened: {
        step = 0
        refreshDiff()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Label {
            Layout.fillWidth: true
            text: step === 0 ? "Step 1 / 4 — Connect and fetch"
                : step === 1 ? "Step 2 / 4 — Preset selected"
                : step === 3 ? "Step 3 / 4 — Review diff"
                : "Step 4 / 4 — Apply"
            font.pixelSize: 14
            font.weight: Font.DemiBold
            color: Theme.fgPrimary
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: wizard.step

            ColumnLayout {
                spacing: 8
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Set this channel on Run → Run target, connect, then fetch $settings and $bonus so the diff is accurate."
                    color: Theme.fgSecondary
                }
                RowLayout {
                    ThemedButton {
                        text: "Fetch $settings"
                        enabled: App.connected
                        onClicked: App.fetchSettings()
                    }
                    ThemedButton {
                        text: "Fetch $bonus"
                        enabled: App.connected
                        onClicked: App.fetchBonus()
                    }
                }
            }

            Label {
                wrapMode: Text.WordWrap
                text: "Using the preset selected in the panel. Adjust groups there if you only want part of the setup."
                color: Theme.fgSecondary
            }

            ThemedScrollView {
                clip: true
                TextArea {
                    id: diffBox
                    readOnly: true
                    wrapMode: TextArea.Wrap
                    font.family: "Consolas, monospace"
                    font.pixelSize: 10
                }
            }

            ColumnLayout {
                spacing: 8
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Run dry run first if you want to preview commands without sending them."
                    color: Theme.fgSecondary
                }
                ThemedButton {
                    text: "Dry run"
                    enabled: App.connected && !App.settingsApplyRunning
                    onClicked: App.applyMudaeSettingsPreset(wizard.channelProfileId, wizard.presetId, true)
                }
                ThemedButton {
                    text: "Apply now"
                    accent: true
                    enabled: App.connected && !App.settingsApplyRunning
                    onClicked: App.applyMudaeSettingsPreset(wizard.channelProfileId, wizard.presetId, false)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ThemedButton {
                text: "Back"
                enabled: wizard.step > 0
                onClicked: wizard.step -= 1
            }
            Item { Layout.fillWidth: true }
            ThemedButton {
                text: wizard.step >= 3 ? "Close" : "Next"
                accent: wizard.step >= 3
                onClicked: {
                    if (wizard.step >= 3) {
                        wizard.close()
                        return
                    }
                    if (wizard.step === 2)
                        refreshDiff()
                    wizard.step += 1
                }
            }
        }
    }
}
