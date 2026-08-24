import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import gui 1.0

/*
    Haul — app shell.

    Icon rail on the left (expands on hover to show tab names), everything
    else in a padded content area. Settings sits at the bottom of the rail.
*/
Item {
    id: shell

    property int currentPage: 0
    signal navigate(int index)

    readonly property var navItems: [
        { icon: "run", title: "Run" },
        { icon: "accounts", title: "Accounts" },
        { icon: "servers", title: "Servers" },
        { icon: "presets", title: "Presets" },
        { icon: "statistics", title: "Statistics" },
        { icon: "debug", title: "Debug" },
        { icon: "utilities", title: "Utilities" }
    ]

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        IconRail {
            currentPage: shell.currentPage
            items: shell.navItems
            settingsIndex: 7
            onNavigate: function(index) { shell.navigate(index) }
        }

        PageHost {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 16
            Layout.bottomMargin: 16
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            pageIndex: shell.currentPage
            runComponent: haulRunPage
        }
    }

    Component {
        id: haulRunPage
        HaulRunPage { anchors.fill: parent }
    }
}
