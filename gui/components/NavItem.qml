import QtQuick
import QtQuick.Controls
import gui 1.0

Button {
    id: nav
    property bool navActive: false

    width: parent ? parent.width : 168
    height: 38
    flat: true
    hoverEnabled: true
    padding: 0
    leftPadding: 12

    background: Rectangle {
        radius: Theme.radiusMd
        color: nav.navActive ? Theme.bgLight : (nav.hovered ? Theme.bgHover : "transparent")
    }

    contentItem: Text {
        text: nav.text
        color: nav.navActive ? Theme.fgPrimary : Theme.fgSecondary
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
