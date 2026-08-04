import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Item {
    id: root
    default property alias content: contentLayout.data
    property string title: ""
    property int contentMargins: 15
    property int titleSize: 16
    property bool fillContentVertically: false

    implicitHeight: innerLayout.implicitHeight + contentMargins * 2
    implicitWidth: innerLayout.implicitWidth + contentMargins * 2

    clip: true

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Theme.bgMedium
        border.color: Theme.border
        border.width: 1
    }

    ColumnLayout {
        id: innerLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: contentMargins
        anchors.bottom: root.fillContentVertically ? parent.bottom : undefined
        spacing: 12

        Label {
            visible: root.title !== ""
            text: root.title
            color: Theme.fgPrimary
            font.pixelSize: titleSize
            font.weight: Font.DemiBold
            Layout.fillWidth: true
        }

        ColumnLayout {
            id: contentLayout
            Layout.fillWidth: true
            Layout.fillHeight: root.fillContentVertically
            spacing: 10
        }
    }
}
