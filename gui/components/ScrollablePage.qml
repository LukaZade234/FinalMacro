import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Vertical scroll container for page content that may exceed the viewport.
Item {
    id: root
    clip: true

    Layout.fillWidth: true
    Layout.fillHeight: true

    property int contentSpacing: 12
    property int bottomPadding: 20
    readonly property real contentWidth: scroll.availableWidth

    default property alias content: contentHost.data

    ThemedScrollView {
        id: scroll
        anchors.fill: parent

        // Explicit height so content exceeds the viewport when children are tall
        // (ColumnLayout alone inside ScrollView often collapses to viewport height).
        Item {
            width: scroll.availableWidth
            height: contentHost.implicitHeight + root.bottomPadding

            ColumnLayout {
                id: contentHost
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: contentSpacing
            }
        }
    }

    WheelScrollForwarder {
        anchors.fill: parent
        z: 1
        flickable: scroll.contentItem
        nestedSearchRoot: scroll.contentItem
    }
}
