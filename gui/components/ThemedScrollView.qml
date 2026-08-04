import QtQuick
import QtQuick.Controls
import gui 1.0

// ScrollView tuned for remote desktops (xpra/VNC): always allow wheel + drag on
// the inner Flickable so nested panels scroll reliably.
ScrollView {
    id: control
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical.policy: ScrollBar.AsNeeded

    // ~60 px per wheel notch (Qt default is ~15 px via rotationScale 15).
    readonly property int wheelRotationScale: 60
    readonly property bool contentIsListView: contentItem && contentItem.model !== undefined

    function enableRemoteScroll() {
        if (!contentItem)
            return
        contentItem.interactive = true
        // ListView scrolls itself; wrapping it in ScrollView breaks row layout.
        contentItem.wheelEnabled = contentIsListView
    }

    Component.onCompleted: enableRemoteScroll()
    onContentItemChanged: enableRemoteScroll()

    WheelHandler {
        target: control.contentItem
        orientation: Qt.Vertical
        rotationScale: control.wheelRotationScale
        enabled: control.contentItem !== null && !control.contentIsListView
    }
}
