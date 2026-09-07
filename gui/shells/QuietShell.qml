import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import gui 1.0
import "../components"
import "../views"

/*
    Quiet — no rail, no title bar, no cards.

    The nav is a row of text with the brand at its left and the connection state
    at its right, and that is the entire chrome. Everything a rail or a top bar
    would have carried is either on the page already or not worth the pixels.

    The pages below are the shared views, unchanged. They read quiet because
    `Theme.flatPanels` turns every `PanelCard` into a hairline and a label —
    Report keeps all ten tiles and every chart, Presets keeps its five sections,
    Debug keeps its two panes.
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
        { label: "Mudae", title: "Mudae" },
        { label: "Spheres", title: "Spheres" },
        { label: "Advisor", title: "Advisor" },
        { label: "Statistics", title: "Statistics" },
        { label: "Debug", title: "Debug" },
        { label: "Settings", title: "Settings" }
    ]

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 32
        anchors.rightMargin: 32
        anchors.topMargin: 20
        anchors.bottomMargin: 22
        spacing: 0

        // ---- nav -------------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            spacing: 18

            RowLayout {
                spacing: 8

                GemMark { size: 12 }

                Label {
                    text: "FinalMacro"
                    color: Theme.fg
                    font.pixelSize: Theme.sizeBody
                    font.weight: Font.DemiBold
                }
            }

            Repeater {
                model: shell.pages

                delegate: Item {
                    required property var modelData
                    required property int index

                    readonly property bool current: shell.currentPage === index

                    implicitWidth: navLabel.implicitWidth
                    implicitHeight: navLabel.implicitHeight + 7

                    Label {
                        id: navLabel
                        anchors.top: parent.top
                        anchors.left: parent.left
                        text: modelData.label
                        color: parent.current ? Theme.fg
                             : (navHover.containsMouse ? Theme.dim : Theme.mute)
                        font.pixelSize: Theme.sizeBody
                        font.weight: parent.current ? Font.DemiBold : Font.Normal
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }

                    // The accent underline is the only marker of where you are.
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        visible: parent.current
                        color: Theme.accent
                    }

                    MouseArea {
                        id: navHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: shell.navigate(index)
                    }
                }
            }

            Item { Layout.fillWidth: true }

            RowLayout {
                spacing: 7

                Rectangle {
                    Layout.preferredWidth: 5
                    Layout.preferredHeight: 5
                    radius: 2.5
                    color: App.connected ? (App.notificationStandby ? Theme.warn : Theme.good)
                                         : Theme.mute

                    SequentialAnimation on opacity {
                        running: App.connected && !App.notificationStandby
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.3; duration: 1100 }
                        NumberAnimation { to: 1.0; duration: 1100 }
                    }
                }

                Label {
                    text: App.statusText
                    color: App.connected ? (App.notificationStandby ? Theme.warn : Theme.good)
                                         : Theme.mute
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    elide: Text.ElideLeft
                    Layout.maximumWidth: 340
                }
            }
        }

        PageHost {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 18
            pageIndex: shell.currentPage
            runComponent: runPage
        }
    }

    Component {
        id: runPage
        QuietRunPage { anchors.fill: parent }
    }
}
