import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "components"
import "views"

ApplicationWindow {
    id: win
    width: 1200
    height: 1000
    minimumWidth: 980
    minimumHeight: 680
    visible: true
    title: "FinalMacro"
    color: Theme.bgDark

    property int currentPage: 0
    property var activeWheelForwarder: null
    property var sidebarWheelForwarder: null

    function dispatchWheelScroll(globalX, globalY, angleDeltaY, pixelDeltaY) {
        var source = {
            angleDelta: { y: angleDeltaY },
            pixelDelta: { y: pixelDeltaY }
        }
        if (win.sidebarWheelForwarder) {
            var sidebarPoint = sidebar.mapFromGlobal(globalX, globalY)
            if (sidebarPoint.x >= 0 && sidebarPoint.y >= 0
                && sidebarPoint.x <= sidebar.width && sidebarPoint.y <= sidebar.height) {
                win.sidebarWheelForwarder.handleGlobalWheel(globalX, globalY, source)
                return
            }
        }
        if (win.activeWheelForwarder)
            win.activeWheelForwarder.handleGlobalWheel(globalX, globalY, source)
    }

    onClosing: function(close) {
        if (App.minimizeToTray) {
            close.accepted = false
            win.hide()
        }
    }

    readonly property var pages: [
        { label: "Run", title: "Run" },
        { label: "Accounts", title: "Accounts" },
        { label: "Servers", title: "Servers" },
        { label: "Presets", title: "Presets" },
        { label: "Statistics", title: "Statistics" },
        { label: "Debug", title: "Debug" },
        { label: "Utilities", title: "Utilities" },
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
        function onNotificationStandbyChanged() {
            topBar.notificationStandby = App.notificationStandby
        }
        function onStatusChanged(text) {
            topBar.statusText = text
        }
        function onWheelScrollRequested(globalX, globalY, angleDeltaY, pixelDeltaY) {
            win.dispatchWheelScroll(globalX, globalY, angleDeltaY, pixelDeltaY)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            id: sidebar
            Layout.preferredWidth: 188
            Layout.maximumWidth: 188
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
                notificationStandby: App.notificationStandby
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
                    case 4: return statisticsPage
                    case 5: return debugPage
                    case 6: return utilitiesPage
                    case 7: return settingsPage
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
                    id: statisticsPage
                    StatisticsView { anchors.fill: parent }
                }
                Component {
                    id: debugPage
                    ParseLabView { anchors.fill: parent }
                }
                Component {
                    id: utilitiesPage
                    UtilitiesView { anchors.fill: parent }
                }
                Component {
                    id: settingsPage
                    SettingsView { anchors.fill: parent }
                }
            }
        }
    }
}
