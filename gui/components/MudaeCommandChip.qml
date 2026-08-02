import QtQuick
import QtQuick.Controls
import gui 1.0

// Compact badge for a Mudae command name (e.g. $setrolls).
Rectangle {
    id: chip
    property string command: ""

    implicitWidth: cmdText.implicitWidth + 16
    implicitHeight: 26
    radius: 5
    color: Qt.rgba(Theme.accentPrimary.r, Theme.accentPrimary.g, Theme.accentPrimary.b, 0.12)
    border.color: Theme.accentPrimary
    border.width: 1

    Text {
        id: cmdText
        anchors.centerIn: parent
        text: chip.command || ""
        font.family: "Consolas, monospace"
        font.pixelSize: 11
        font.weight: Font.DemiBold
        color: Theme.accentPrimary
    }
}
