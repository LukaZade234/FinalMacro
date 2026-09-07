import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// A label, its value and a 3px rule under them. Quiet's whole progress vocabulary.
Item {
    id: meter

    property string label: ""
    property string value: ""
    property real fraction: -1
    property bool accentValue: false
    property color barColor: Theme.accent

    implicitHeight: col.implicitHeight
    Layout.preferredHeight: col.implicitHeight

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 5

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Label {
                Layout.fillWidth: true
                text: meter.label
                color: Theme.dim
                font.pixelSize: Theme.sizeSmall
                elide: Text.ElideRight
            }

            Label {
                text: meter.value
                color: meter.accentValue ? Theme.accent : Theme.fg
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeSmall
                font.weight: Font.Medium
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 3
            visible: meter.fraction >= 0
            radius: 1.5
            color: Theme.line

            Rectangle {
                width: parent.width * Math.max(0, Math.min(1, meter.fraction))
                height: parent.height
                radius: parent.radius
                color: meter.barColor
            }
        }
    }
}
