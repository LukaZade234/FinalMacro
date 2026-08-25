import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Compact sphere type for log tables (icon + optional label).
Item {
    id: root
    property string sphereId: ""
    property bool showLabel: false
    property string tooltip: ""

    readonly property string iconSource: SphereAssets.iconUrl(sphereId)
    readonly property bool hasIcon: iconSource !== ""

    implicitWidth: row.implicitWidth
    implicitHeight: row.implicitHeight

    ToolTip {
        visible: badgeMouse.containsMouse && (sphereId !== "" && sphereId !== undefined)
        text: root.tooltip !== "" ? root.tooltip : SphereAssets.label(sphereId)
        delay: 400
    }

    RowLayout {
        id: row
        anchors.fill: parent
        spacing: 4

        Image {
            visible: root.hasIcon
            source: root.iconSource
            sourceSize.width: 18
            sourceSize.height: 18
            width: 18
            height: 18
            fillMode: Image.PreserveAspectFit
            smooth: true
        }

        Rectangle {
            visible: !root.hasIcon && sphereId
            width: 12
            height: 12
            radius: 6
            color: SphereAssets.color(sphereId)
            border.color: Theme.border
        }

        Label {
            visible: showLabel
            text: SphereAssets.label(sphereId)
            color: Theme.fgMuted
            font.pixelSize: 11
            elide: Text.ElideRight
            Layout.fillWidth: showLabel
        }
    }

    MouseArea {
        id: badgeMouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
    }
}
