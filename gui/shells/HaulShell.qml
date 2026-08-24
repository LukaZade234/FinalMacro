import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import gui 1.0

/*
    Haul — app shell.

    A 56px icon rail on the left, everything else in a padded content area.
    Settings sits at the bottom of the rail, as in the mockup.
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

        // ---- rail ----------------------------------------------------------

        Rectangle {
            Layout.preferredWidth: 56
            Layout.fillHeight: true
            color: Theme.surface

            Rectangle {
                anchors.right: parent.right
                width: 1
                height: parent.height
                color: Theme.line
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 13
                anchors.bottomMargin: 13
                spacing: 5

                // app mark
                Item {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    Layout.bottomMargin: 12

                    GradientPanel {
                        anchors.fill: parent
                        radius: 9
                        colorFrom: Theme.accent
                        colorTo: Theme.accent2
                    }

                    GemMark {
                        anchors.centerIn: parent
                        size: 12
                        color: Theme.bg
                    }
                }

                Repeater {
                    model: shell.navItems

                    delegate: RailButton {
                        required property int index
                        required property var modelData

                        Layout.alignment: Qt.AlignHCenter
                        iconName: modelData.icon
                        tooltip: modelData.title
                        active: shell.currentPage === index
                        onClicked: shell.navigate(index)
                    }
                }

                Item { Layout.fillHeight: true }

                RailButton {
                    Layout.alignment: Qt.AlignHCenter
                    iconName: "settings"
                    tooltip: "Settings"
                    active: shell.currentPage === 7
                    onClicked: shell.navigate(7)
                }
            }
        }

        // ---- content -------------------------------------------------------

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
