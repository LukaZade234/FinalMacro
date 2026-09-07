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
    scale rather than staying rounded in the squared-off designs. Under
    `Theme.flatPanels` it loses the pill entirely and marks the active tab with
    an accent underline — the same mark the Quiet nav uses, so a page's sections
    and the app's pages read as the same kind of choice.
*/
Button {
    id: tab

    property bool tabActive: false
    property bool stretch: true

    Layout.fillWidth: stretch
    height: 34
    padding: 0
    leftPadding: Theme.flatPanels ? 2 : 14
    rightPadding: Theme.flatPanels ? 2 : 14
    flat: true
    hoverEnabled: true

    background: Item {
        Rectangle {
            visible: !Theme.flatPanels
            anchors.fill: parent
            radius: Theme.radiusMd
            color: tab.tabActive ? Theme.raised : (tab.hovered ? Theme.hover : "transparent")
            border.color: tab.tabActive ? Theme.line : "transparent"
            border.width: Theme.borderWidth
        }

        Rectangle {
            visible: Theme.flatPanels && tab.tabActive
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.accent
        }
    }

    contentItem: Text {
        text: tab.text
        color: tab.tabActive ? Theme.fg : (tab.hovered ? Theme.dim : Theme.mute)
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeSmall
        font.weight: tab.tabActive ? Font.DemiBold : Font.Normal
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
    }
}
