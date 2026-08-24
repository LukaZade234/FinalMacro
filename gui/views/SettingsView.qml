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

    function updateStatusIsError() {
        return App.updateError !== ""
    }

    function updateStatusText() {
        if (App.updateChecking)
            return "Checking…"
        if (App.updateError !== "") {
            if (App.updateError === "Not a git checkout")
                return "Not a git checkout — clone the repo with git to enable update checks."
            return "Check failed: " + App.updateError
        }
        if (App.updatePending)
            return App.updateBehindCount + " change" + (App.updateBehindCount === 1 ? "" : "s") + " available on " + App.updateBranch
                + (App.updateAvailable ? "" : " · banner dismissed")
        if (App.updateLastCheckedEpoch > 0) {
            var d = new Date(App.updateLastCheckedEpoch * 1000)
            return "Up to date · last checked " + d.toLocaleTimeString(Qt.locale(), "hh:mm")
        }
        return "Not checked yet"
    }

    function indexById(list, id) {
        if (!list)
            return 0
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === id)
                return i
        }
        return 0
    }

    readonly property var layoutNames: {
        var list = Theme.layoutList || []
        var out = []
        for (var i = 0; i < list.length; i++)
            out.push(list[i].name)
        return out
    }

    readonly property var paletteNames: {
        var list = Theme.paletteList || []
        var out = []
        for (var i = 0; i < list.length; i++)
            out.push(list[i].name)
        return out
    }

    ScrollablePage {
        anchors.fill: parent

        PanelCard {
            Layout.fillWidth: true
            title: "Appearance"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 12

                Label {
                    Layout.fillWidth: true
                    text: "Pick the layout and colours for the whole app. Each design has its own Run page and navigation; the other pages follow the same shapes and fonts."
                    color: Theme.fgMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.preferredWidth: 100
                        text: "Design"
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                    }

                    ThemedComboBox {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 220
                        model: settingsRoot.layoutNames
                        currentIndex: settingsRoot.indexById(Theme.layoutList, App.uiLayout)
                        onActivated: function(i) {
                            if (Theme.layoutList && Theme.layoutList[i])
                                App.setUiLayout(Theme.layoutList[i].id)
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    Layout.leftMargin: 110
                    text: {
                        var i = settingsRoot.indexById(Theme.layoutList, App.uiLayout)
                        return Theme.layoutList && Theme.layoutList[i] ? Theme.layoutList[i].description : ""
                    }
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 2
                    spacing: 10

                    Label {
                        Layout.preferredWidth: 100
                        text: "Colour theme"
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                    }

                    ThemedComboBox {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 220
                        model: settingsRoot.paletteNames
                        currentIndex: settingsRoot.indexById(Theme.paletteList, App.uiPalette)
                        onActivated: function(i) {
                            if (Theme.paletteList && Theme.paletteList[i])
                                App.setUiPalette(Theme.paletteList[i].id)
                        }
                    }

                    ThemedButton {
                        text: "Match design"
                        onClicked: App.resetUiPalette()
                    }
                }

                Item {
                    Layout.fillWidth: true
                    implicitHeight: paletteFlow.implicitHeight
                    Layout.preferredHeight: implicitHeight

                    Flow {
                        id: paletteFlow
                        width: parent.width
                        spacing: 8

                        Repeater {
                            model: Theme.paletteList ? Theme.paletteList.length : 0

                            delegate: Rectangle {
                                id: paletteCard

                                readonly property var item: Theme.paletteList[index]
                                readonly property bool active: App.uiPalette === item.id

                                width: 132
                                height: 44
                                radius: Theme.radiusMd
                                color: item.surface
                                border.width: active ? 2 : 1
                                border.color: active ? item.accent
                                    : (paletteHover.containsMouse ? Theme.fgMuted : item.line)

                                Row {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    spacing: 8

                                    Item {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 26
                                        height: 16

                                        Rectangle {
                                            x: 0
                                            width: 16
                                            height: 16
                                            radius: 8
                                            color: paletteCard.item.accent
                                        }
                                        Rectangle {
                                            x: 10
                                            width: 16
                                            height: 16
                                            radius: 8
                                            color: paletteCard.item.accent2
                                            border.width: 1
                                            border.color: paletteCard.item.surface
                                        }
                                    }

                                    Label {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: paletteCard.item.name
                                        color: paletteCard.item.fg
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                    }
                                }

                                MouseArea {
                                    id: paletteHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: App.setUiPalette(paletteCard.item.id)
                                }
                            }
                        }
                    }
                }
            }
        }

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
            title: "System tray"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "Keep the macro running in the background when you close the window."
                    color: Theme.fgMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.fillWidth: true
                        text: "Minimize to tray when closing the window"
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }

                    ThemedSwitch {
                        checked: App.minimizeToTray
                        enabled: App.trayAvailable
                        onToggled: App.setMinimizeToTray(checked)
                    }
                }

                Label {
                    Layout.fillWidth: true
                    visible: App.trayAvailable
                    text: "Click the tray icon to restore the window. Right-click for Quit."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    visible: !App.trayAvailable
                    text: "System tray is not available on this desktop, so this option is disabled."
                    color: Theme.warning
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Updates"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "FinalMacro checks the git remote for new commits. Only works for a `git clone` checkout — a downloaded ZIP has no way to check. Edits to `data/settings.json` reload automatically while the app is open."
                    color: Theme.fgMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.fillWidth: true
                        text: "Automatically check for updates"
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }

                    ThemedSwitch {
                        checked: App.autoUpdateCheckEnabled
                        onToggled: App.setAutoUpdateCheckEnabled(checked)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ThemedButton {
                        text: App.updateChecking ? "Checking…" : "Check now"
                        loading: App.updateChecking
                        enabled: !App.updateChecking
                        onClicked: App.checkForUpdates(true)
                    }

                    ThemedButton {
                        text: "Reload settings"
                        onClicked: App.reloadSettingsFromDisk()
                    }

                    Label {
                        Layout.fillWidth: true
                        text: settingsRoot.updateStatusText()
                        color: settingsRoot.updateStatusIsError() ? Theme.warning : Theme.fgMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
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
