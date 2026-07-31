import QtQuick
import QtQuick.Controls
import gui 1.0

Rectangle {
    id: pill
    property string phase: "Idle"

    readonly property bool active: phase !== "Idle"

    implicitHeight: 28
    implicitWidth: Math.max(88, label.implicitWidth + 20)
    radius: 14
    color: pill.active ? Qt.rgba(0.48, 0.64, 0.97, 0.16) : Theme.bgDark
    border.color: pill.active ? Theme.accentPrimary : Theme.border
    border.width: 1

    Text {
        id: label
        anchors.centerIn: parent
        text: pill.phase
        color: pill.active ? Theme.accentPrimary : Theme.fgMuted
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
}
