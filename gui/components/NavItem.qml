import QtQuick
import QtQuick.Controls
import gui 1.0

Button {
    id: nav
    property bool navActive: false

    width: parent ? parent.width : 230
    height: 45
    flat: true
    hoverEnabled: true
    padding: 0
    leftPadding: 12

    background: Rectangle {
        radius: 8
        color: nav.navActive ? Theme.bgLight : (nav.hovered ? Theme.bgHover : "transparent")
    }

    contentItem: Text {
        text: nav.text
        color: nav.navActive ? Theme.fgPrimary : Theme.fgSecondary
        font.pixelSize: 14
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
