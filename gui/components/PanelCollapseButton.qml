import QtQuick
import gui 1.0

// Chevron in a panel's top corner: click to fold the panel down to its title
// line. Shared by the Run status panels so all four shells behave the same.
Item {
    id: root

    property bool collapsed: false
    property color tint: Theme.fgMuted

    signal toggled()

    implicitWidth: 16
    implicitHeight: 16

    Canvas {
        id: mark
        anchors.centerIn: parent
        width: 9
        height: 9
        rotation: root.collapsed ? -90 : 0
        opacity: hover.containsMouse ? 1.0 : 0.65

        Behavior on rotation {
            NumberAnimation { duration: 110; easing.type: Easing.OutQuad }
        }

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = root.tint
            ctx.lineWidth = 1.4
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            ctx.moveTo(1, 3)
            ctx.lineTo(width / 2, height - 2.5)
            ctx.lineTo(width - 1, 3)
            ctx.stroke()
        }
    }

    // Repaint on theme change; rotation alone does not invalidate the canvas.
    Connections {
        target: Theme
        function onPaletteIdChanged() { mark.requestPaint() }
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        anchors.margins: -4
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled()
    }
}
