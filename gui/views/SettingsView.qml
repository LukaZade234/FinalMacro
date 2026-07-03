import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: settingsRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    ScrollablePage {
        anchors.fill: parent

        PanelCard {
            Layout.fillWidth: true
            title: "Configuration"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10

                Label {
                    Layout.fillWidth: true
                    text: "Accounts, servers/channels, and presets are managed in their own tabs. Run combines all three into a single target."
                    color: Theme.fgMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: "• Accounts — Discord tokens and enabled channels\n• Servers — channel IDs and Mudae $settings / $bonus\n• Presets — roll and claim behavior\n• Run — pick account + channel + preset, then Connect"
                    color: Theme.fgSecondary
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Import from MudaeBot"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "Reads MudaeBot---Copy/Account_info.json and presets.json (MacroConfig fields only). Existing entries are merged."
                    color: Theme.fgMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                ThemedButton {
                    text: "Import legacy config"
                    onClicked: importStatus.text = App.importLegacyConfig()
                }

                Label {
                    id: importStatus
                    Layout.fillWidth: true
                    text: ""
                    color: Theme.fgSecondary
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
