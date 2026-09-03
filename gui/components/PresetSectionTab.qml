import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    A section tab inside a page.

    `stretch` (default true) spreads the tabs across a full-width strip, which is
    what Presets and Servers want. Hub pages that want content-sized pills — the
    `StatisticsView` idiom — set it false.

    Shape and type come from `Theme` so the tab takes each shell's radius and
    scale rather than staying rounded in the squared-off designs.
*/
Button {
    id: tab

    property bool tabActive: false
    property bool stretch: true

    Layout.fillWidth: stretch
    height: 34
    padding: 0
    leftPadding: 14
    rightPadding: 14
    flat: true
    hoverEnabled: true

    background: Rectangle {
        radius: Theme.radiusMd
        color: tab.tabActive ? Theme.raised : (tab.hovered ? Theme.hover : "transparent")
        border.color: tab.tabActive ? Theme.line : "transparent"
        border.width: Theme.borderWidth
    }

    contentItem: Text {
        text: tab.text
        color: tab.tabActive ? Theme.fg : Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeSmall
        font.weight: tab.tabActive ? Font.DemiBold : Font.Normal
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
    }
}
