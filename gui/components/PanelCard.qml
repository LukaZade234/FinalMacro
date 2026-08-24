import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Item {
    id: root
    default property alias content: contentLayout.data
    property string title: ""
    property int contentMargins: Theme.cardPadding
    property int titleSize: Theme.sizeXLarge
    property bool fillContentVertically: false

    implicitHeight: innerLayout.implicitHeight + contentMargins * 2
    implicitWidth: innerLayout.implicitWidth + contentMargins * 2

    clip: true

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusLg
        color: Theme.bgMedium
        border.color: Theme.border
        border.width: 1
    }

    // The Boxed design rules its panels with a double border; the inner rule is
    // drawn separately since Rectangle only has a single stroke.
    Rectangle {
        visible: Theme.doubleBorder
        anchors.fill: parent
        anchors.margins: 2
        radius: Theme.radiusLg
        color: "transparent"
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
