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

        ColumnLayout {
            width: scroll.availableWidth
            spacing: 0
            // Ensure ScrollView content height reflects all page children.
            height: implicitHeight

            ColumnLayout {
                id: contentHost
                Layout.fillWidth: true
                spacing: contentSpacing
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: bottomPadding
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
