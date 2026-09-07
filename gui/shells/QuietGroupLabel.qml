import QtQuick
import QtQuick.Controls
import gui 1.0

// The tracked micro-label that names a group of actions ("Checks", "Minigames").
Item {
    property alias text: label.text

    implicitHeight: Theme.controlHeight
    implicitWidth: label.implicitWidth + 22

    Label {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: 14
        color: Theme.mute
        font.family: Theme.monoFamily
        font.pixelSize: Theme.sizeMicro
        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
        text: Theme.sectionLabel(text)
    }
}
