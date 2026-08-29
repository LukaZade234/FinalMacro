import QtQuick
import gui 1.0

// Section label with an on/off word and a fold chevron in the right corner.
// Sized for the shells' `Theme.sectionLabel` headers.
Item {
    id: root

    property string title: ""
    property bool on: false
    property bool collapsed: false
    property int gap: 7

    signal toggled()

    implicitHeight: label.implicitHeight + gap

    Text {
        id: label
        anchors.left: parent.left
        anchors.top: parent.top
        text: Theme.sectionLabel(root.title)
        color: Theme.mute
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeMicro
        font.weight: Font.DemiBold
        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
    }

    Text {
        id: state
        anchors.right: fold.visible ? fold.left : parent.right
        anchors.rightMargin: fold.visible ? 6 : 0
        anchors.verticalCenter: label.verticalCenter
        text: root.on ? "on" : "off"
        color: root.on ? Theme.good : Theme.mute
        font.family: Theme.monoFamily
        font.pixelSize: Theme.sizeMicro
        font.weight: Font.DemiBold
    }

    PanelCollapseButton {
        id: fold
        anchors.right: parent.right
        anchors.verticalCenter: label.verticalCenter
        visible: root.on
        collapsed: root.collapsed
        tint: Theme.mute
        onToggled: root.toggled()
    }
}
