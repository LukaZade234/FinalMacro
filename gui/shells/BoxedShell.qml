import QtQuick
import QtQuick.Layouts

import gui 1.0
import "../components"

/*
    Boxed — app shell.

    Design G: an accent title strip, a menu bar with Alt accelerators, the page
    itself on a tinted desktop, and an accent status line along the bottom.
*/
Item {
    id: shell

    property int currentPage: 0
    signal navigate(int index)

    RunModel { id: run }
    TargetModel { id: targets }

    // `accel` is the index of the underlined letter. Settings takes G rather
    // than the mockup's T so it does not collide with Stats.
    readonly property var menuItems: [
        { label: "Run", accel: 0 },
        { label: "Accounts", accel: 0 },
        { label: "Servers", accel: 0 },
        { label: "Presets", accel: 0 },
        { label: "Mudae", accel: 0 },
        { label: "Spheres", accel: 1 },
        { label: "Advisor", accel: 1 },
        { label: "Stats", accel: 1 },
        { label: "Debug", accel: 0 },
        { label: "Settings", accel: 6 }
    ]

    property string clock: Qt.formatTime(new Date(), "HH:mm:ss")

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: shell.clock = Qt.formatTime(new Date(), "HH:mm:ss")
    }

    Repeater {
        model: shell.menuItems

        delegate: Item {
            required property int index
            required property var modelData

            Shortcut {
                sequences: ["Alt+" + modelData.label.charAt(modelData.accel)]
                onActivated: shell.navigate(index)
            }
        }
    }

    Shortcut {
        sequence: "F2"
        enabled: run.connected && !run.macroRunning
        onActivated: App.startMacro()
    }
    Shortcut {
        sequence: "F5"
        enabled: run.connected
        onActivated: App.playAllMinigames()
    }
    Shortcut {
        sequence: "F9"
        enabled: !run.connecting && !run.disconnecting
        onActivated: run.connected ? App.disconnect() : App.connect()
    }
    Shortcut {
        sequence: "F10"
        enabled: run.macroRunning || run.engineRunning
        onActivated: App.stopMacro()
    }

    // The desktop behind the boxes carries a wash of the secondary accent.
    Rectangle {
        anchors.fill: parent
        color: Theme.blend(Theme.accent2, Theme.bg, 0.10)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- title strip ---------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            color: Theme.accent

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: "FinalMacro — " + shell.menuItems[shell.currentPage].label
                color: Theme.bg
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeSmall
                font.weight: Font.DemiBold
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                ThemeSphere {
                    anchors.verticalCenter: parent.verticalCenter
                    size: 14
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: targets.accountLabel
                    color: Theme.bg
                    opacity: 0.75
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    font.weight: Font.DemiBold
                }
            }
        }

        // ---- menu bar ------------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            color: Theme.surface

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.line
            }

            Row {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom

                Repeater {
                    model: shell.menuItems

                    delegate: Rectangle {
                        required property int index
                        required property var modelData

                        readonly property bool active: shell.currentPage === index

                        width: menuText.implicitWidth + 24
                        height: parent.height
                        color: active ? Theme.accent
                            : (menuMouse.containsMouse ? Theme.raised : "transparent")

                        Text {
                            id: menuText
                            anchors.centerIn: parent
                            textFormat: Text.StyledText
                            text: {
                                var label = modelData.label
                                var i = modelData.accel
                                var letter = "<u>" + label.charAt(i) + "</u>"
                                return label.slice(0, i) + letter + label.slice(i + 1)
                            }
                            color: parent.active ? Theme.bg : Theme.dim
                            linkColor: Theme.accent
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            font.weight: parent.active ? Font.DemiBold : Font.Normal
                        }

                        MouseArea {
                            id: menuMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: shell.navigate(index)
                        }
                    }
                }
            }

            Text {
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: run.statusLine
                color: run.connected ? Theme.good : Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeSmall
            }
        }

        // ---- desktop -------------------------------------------------------

        PageHost {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 13
            pageIndex: shell.currentPage
            runComponent: boxedRunPage
        }

        // ---- status line ---------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            color: Theme.accent

            Row {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 20

                Repeater {
                    model: [
                        { key: "F2", label: "Start hourly" },
                        { key: "F5", label: "Minigames" },
                        { key: "F9", label: run.connected ? "Disconnect" : "Connect" },
                        { key: "F10", label: "Stop" }
                    ]

                    delegate: Row {
                        required property var modelData
                        spacing: 5

                        Text {
                            text: modelData.key
                            color: Theme.bg
                            opacity: 0.7
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: modelData.label
                            color: Theme.bg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                ThemeSphere {
                    anchors.verticalCenter: parent.verticalCenter
                    size: 14
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: run.phase.toUpperCase() + " · " + shell.clock
                    color: Theme.bg
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    font.weight: Font.DemiBold
                }
            }
        }
    }

    Component {
        id: boxedRunPage
        BoxedRunPage { anchors.fill: parent }
    }
}
