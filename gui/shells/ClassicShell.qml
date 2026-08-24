import QtQuick
import QtQuick.Layouts

import gui 1.0
import "../components"
import "../views"

/*
    The original layout: fixed sidebar, page title bar, page below.
*/
Item {
    id: shell

    property int currentPage: 0
    signal navigate(int index)

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

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            id: sidebar
            Layout.preferredWidth: 188
            Layout.maximumWidth: 188
            Layout.fillHeight: true
            currentIndex: shell.currentPage
            navModel: shell.pages
            onNavigated: function(index) { shell.navigate(index) }
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
                pageTitle: shell.pageTitleAt(shell.currentPage)
                statusText: App.statusText
                statusOnline: App.connected
                notificationStandby: App.notificationStandby
            }

            PageHost {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 24
                Layout.rightMargin: 24
                Layout.bottomMargin: 16
                pageIndex: shell.currentPage
                runComponent: runPage
            }
        }
    }

    Component {
        id: runPage
        RunView { anchors.fill: parent }
    }
}
