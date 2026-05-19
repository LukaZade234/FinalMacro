import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "components"
import "views"

ApplicationWindow {
    id: win
    width: 1100
    height: 750
    minimumWidth: 900
    minimumHeight: 600
    visible: true
    title: "FinalMacro"
    color: Theme.bgDark

    property int currentPage: 0

    readonly property var pages: [
        { label: "Run", title: "Run" },
        { label: "Accounts", title: "Accounts" },
        { label: "Servers", title: "Servers" },
        { label: "Presets", title: "Presets" },
        { label: "Debug", title: "Debug" },
        { label: "Settings", title: "Settings" }
    ]

    function pageTitleAt(index) {
        if (index < 0 || index >= pages.length)
            return ""
        return pages[index].title
    }

    Connections {
        target: App
        function onConnectedChanged(connected) {
            topBar.statusOnline = connected
        }
        function onStatusChanged(text) {
            topBar.statusText = text
        }
        function onMacroPhaseChanged() {
            topBar.macroPhaseText = App.macroPhase
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            id: sidebar
            Layout.preferredWidth: 250
            Layout.maximumWidth: 250
            Layout.fillHeight: true
            currentIndex: win.currentPage
            navModel: win.pages
            onNavigated: function(index) {
                win.currentPage = index
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12
            clip: true

            TopBar {
                id: topBar
                Layout.fillWidth: true
                Layout.leftMargin: 24
                Layout.rightMargin: 24
                Layout.topMargin: 16
                pageTitle: win.pageTitleAt(win.currentPage)
                statusText: App.statusText
                statusOnline: App.connected
                showMacroPhase: win.currentPage === 0
                macroPhaseText: App.macroPhase
            }

            Loader {
                id: pageLoader
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 24
                Layout.rightMargin: 24
                Layout.bottomMargin: 16
                clip: true

                property int pageIndex: win.currentPage

                sourceComponent: {
                    switch (pageIndex) {
                    case 1: return accountsPage
                    case 2: return serversPage
                    case 3: return presetsPage
                    case 4: return debugPage
                    case 5: return settingsPage
                    default: return runPage
                    }
                }

                Component {
                    id: runPage
                    RunView { anchors.fill: parent }
                }
                Component {
                    id: accountsPage
                    AccountsView { anchors.fill: parent }
                }
                Component {
                    id: serversPage
                    ServersView { anchors.fill: parent }
                }
                Component {
                    id: presetsPage
                    PresetsView { anchors.fill: parent }
                }
                Component {
                    id: debugPage
                    ParseLabView { anchors.fill: parent }
                }
                Component {
                    id: settingsPage
                    SettingsView { anchors.fill: parent }
                }
            }
        }
    }
}
