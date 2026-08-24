import QtQuick
import QtQuick.Layouts

import gui 1.0

/*
    Collapsed icon rail that grows on hover to show tab names.

    Occupies ``collapsedWidth`` in the parent layout so the page does not
    reflow; the bar overlays the content while expanded. Haul uses this
    today; other icon-rail shells can drop the same component in.
*/
Item {
    id: rail

    property int currentPage: 0
    property var items: []
    property int settingsIndex: -1
    property string settingsIcon: "settings"
    property string settingsTitle: "Settings"
    property int collapsedWidth: 56
    property int expandedWidth: 176

    signal navigate(int index)

    readonly property bool expanded: barHover.hovered || collapseTimer.running

    implicitWidth: collapsedWidth
    Layout.preferredWidth: collapsedWidth
    Layout.fillHeight: true
    z: 2

    Timer {
        id: collapseTimer
        interval: 160
        repeat: false
    }

    Rectangle {
        id: bar
        width: rail.expanded ? rail.expandedWidth : rail.collapsedWidth
        height: parent.height
        color: Theme.surface

        Behavior on width {
            NumberAnimation {
                duration: 160
                easing.type: Easing.OutCubic
            }
        }

        HoverHandler {
            id: barHover
            onHoveredChanged: {
                if (barHover.hovered)
                    collapseTimer.stop()
                else
                    collapseTimer.restart()
            }
        }

        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: Theme.line
        }

        Rectangle {
            visible: rail.expanded
            anchors.left: parent.right
            width: 16
            height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.fade(Theme.bg, 0.35) }
                GradientStop { position: 1; color: "transparent" }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.topMargin: 13
            anchors.bottomMargin: 13
            spacing: 5

            Item {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                Layout.bottomMargin: 12
                Layout.leftMargin: 14
                Layout.alignment: Qt.AlignLeft

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
                model: rail.items

                delegate: RailButton {
                    required property int index
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    iconName: modelData.icon
                    label: modelData.title
                    expanded: rail.expanded
                    active: rail.currentPage === index
                    onClicked: rail.navigate(index)
                }
            }

            Item { Layout.fillHeight: true }

            RailButton {
                visible: rail.settingsIndex >= 0
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                iconName: rail.settingsIcon
                label: rail.settingsTitle
                expanded: rail.expanded
                active: rail.currentPage === rail.settingsIndex
                onClicked: rail.navigate(rail.settingsIndex)
            }
        }
    }
}
