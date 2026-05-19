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

    Flickable {
        id: flick
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        contentWidth: width
        contentHeight: settingsColumn.height + 32
        ScrollBar.vertical: ScrollBar {
            parent: flick
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            policy: ScrollBar.AsNeeded
        }

        Column {
            id: settingsColumn
            width: flick.width - 8
            x: 4
            topPadding: 8
            bottomPadding: 24
            spacing: 16

            PanelCard {
                width: parent.width
                title: "Configuration"
                titleSize: 14

                ColumnLayout {
                    width: parent.width - 30
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
                width: parent.width
                title: "Import from MudaeBot"
                titleSize: 14

                ColumnLayout {
                    width: parent.width - 30
                    spacing: 8

                    Label {
                        Layout.fillWidth: true
                        text: "Reads MudaeBot---Copy/Account_info.json and presets.json (MacroConfig fields only). Existing entries are merged."
                        color: Theme.fgMuted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }

                    Button {
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
}
