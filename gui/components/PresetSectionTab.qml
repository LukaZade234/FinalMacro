import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Button {
    id: tab
    property bool tabActive: false

    Layout.fillWidth: true
    height: 34
    padding: 0
    leftPadding: 14
    rightPadding: 14
    flat: true
    hoverEnabled: true

    background: Rectangle {
        radius: 8
        color: tab.tabActive ? Theme.bgLight : (tab.hovered ? Theme.bgHover : "transparent")
        border.color: tab.tabActive ? Theme.border : "transparent"
        border.width: 1
    }

    contentItem: Text {
        text: tab.text
        color: tab.tabActive ? Theme.fgPrimary : Theme.fgSecondary
        font.pixelSize: 12
        font.weight: tab.tabActive ? Font.DemiBold : Font.Normal
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
    }
}
