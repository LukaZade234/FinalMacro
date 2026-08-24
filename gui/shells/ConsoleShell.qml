import QtQuick
import QtQuick.Layouts

import gui 1.0
import "../components"

/*
    Console — app shell.

    Design B: a 34px tab strip across the top with the connection state on the
    right, everything else below it. The Run page is full-bleed (its own bars run
    edge to edge); the other pages get the usual padding.
*/
Item {
    id: shell

    property int currentPage: 0
    signal navigate(int index)

    RunModel { id: run }

    readonly property var tabs: [
        "run", "accounts", "servers", "presets", "stats", "debug", "utilities", "settings"
    ]

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- tab strip -----------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            color: Theme.surface

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.line
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 2

                Row {
                    Layout.rightMargin: 14
                    spacing: 7

                    ThemeSphere {
                        anchors.verticalCenter: parent.verticalCenter
                        size: 20
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "finalmacro"
                        color: Theme.accent
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeBody
                        font.weight: Font.DemiBold
                    }
                }

                Repeater {
                    model: shell.tabs

                    delegate: Rectangle {
                        required property int index
                        required property string modelData

                        readonly property bool active: shell.currentPage === index

                        Layout.preferredWidth: tabText.implicitWidth + 20
                        Layout.preferredHeight: 22
                        radius: Theme.radiusMd
                        color: active ? Theme.accent
                            : (tabMouse.containsMouse ? Theme.raised : "transparent")

                        Text {
                            id: tabText
                            anchors.centerIn: parent
                            text: modelData
                            color: parent.active ? Theme.bg : Theme.mute
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            font.weight: parent.active ? Font.DemiBold : Font.Normal
                        }

                        MouseArea {
                            id: tabMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: shell.navigate(index)
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: run.statusLine
                    color: run.connected ? Theme.good : Theme.mute
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                }
            }
        }

        // ---- content -------------------------------------------------------

        PageHost {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: shell.currentPage === 0 ? 0 : 14
            pageIndex: shell.currentPage
            runComponent: consoleRunPage
        }
    }

    Component {
        id: consoleRunPage
        ConsoleRunPage { anchors.fill: parent }
    }
}
