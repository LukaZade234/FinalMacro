import QtQuick

import gui 1.0

// Vertical rule between control-bar groups. Wrapped in a full-height Item
// because Flow refuses to lay out children that use anchors.
Item {
    implicitWidth: 7
    implicitHeight: 38

    Rectangle {
        anchors.centerIn: parent
        width: 1
        height: 24
        color: Theme.line
    }
}
