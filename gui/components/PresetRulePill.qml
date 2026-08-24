import QtQuick
import QtQuick.Controls
import gui 1.0

Rectangle {
    id: pill
    property string label: ""
    property bool enabled: false

    implicitHeight: 26
    implicitWidth: row.implicitWidth + 16
    radius: Theme.radiusPill
    color: pill.enabled ? Qt.rgba(0.62, 0.81, 0.42, 0.14) : Theme.bgDark
    border.color: pill.enabled ? Theme.success : Theme.border
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
            color: pill.enabled ? Theme.success : Theme.bgHover
        }

        Text {
            text: pill.label
            color: pill.enabled ? Theme.success : Theme.fgMuted
            font.pixelSize: 10
            font.weight: Font.DemiBold
        }
    }
}
