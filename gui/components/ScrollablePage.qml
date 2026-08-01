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
    readonly property real contentWidth: flick.width

    default property alias content: contentHost.data

    Flickable {
        id: flick
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: contentHost.implicitHeight + bottomPadding

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        ColumnLayout {
            width: flick.width
            spacing: 0

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
}
