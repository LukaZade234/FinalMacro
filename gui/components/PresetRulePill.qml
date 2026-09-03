import QtQuick
import QtQuick.Controls
import gui 1.0

/*
    A tiny on/off pill for a preset rule block.

    The flag is `ruleActive`, not `enabled`: `Item.enabled` already exists and
    gates input for an item and everything under it, so redeclaring it shadowed
    the base property and forced the whole pill into Qt's disabled state
    whenever a rule was off.
*/
Rectangle {
    id: pill
    property string label: ""
    property bool ruleActive: false

    implicitHeight: 26
    implicitWidth: row.implicitWidth + 16
    radius: Theme.radiusPill
    color: pill.ruleActive ? Qt.rgba(0.62, 0.81, 0.42, 0.14) : Theme.bgDark
    border.color: pill.ruleActive ? Theme.success : Theme.border
    border.width: 1

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Rectangle {
            width: 6
            height: 6
            radius: Theme.radiusXs
            anchors.verticalCenter: parent.verticalCenter
            color: pill.ruleActive ? Theme.success : Theme.bgHover
        }

        Text {
            text: pill.label
            color: pill.ruleActive ? Theme.success : Theme.fgMuted
            font.pixelSize: 10
            font.weight: Font.DemiBold
        }
    }
}
