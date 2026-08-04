import QtQuick
import QtQuick.Controls

// Forwards wheel events over buttons/labels to the nearest scrollable ancestor.
// Use inside PanelCard only — do not overlay an entire ScrollView viewport.
MouseArea {
    id: root
    anchors.fill: parent
    acceptedButtons: Qt.NoButton
    hoverEnabled: false

    property var flickable: null
    property Item nestedSearchRoot: null
    // Match ThemedScrollView.wheelRotationScale (60 px per ±120° notch).
    property real pixelsPerWheelStep: 60

    function wheelDelta(wheel) {
        if (wheel.angleDelta.y !== 0)
            return wheel.angleDelta.y * pixelsPerWheelStep / 120
        if (wheel.pixelDelta.y !== 0)
            return wheel.pixelDelta.y * 10
        return 0
    }

    function scrollFlickable(flick, wheel) {
        if (!flick || flick.contentHeight <= flick.height)
            return false
        var dy = wheelDelta(wheel)
        if (dy === 0)
            return false
        var maxY = Math.max(0, flick.contentHeight - flick.height)
        var newY = Math.max(0, Math.min(maxY, flick.contentY - dy))
        if (newY === flick.contentY)
            return false
        flick.contentY = newY
        return true
    }

    function isScrollView(item) {
        return item
               && item !== root
               && item.contentItem
               && item.contentItem.contentY !== undefined
    }

    function isListView(item) {
        return item
               && item !== root
               && item.model !== undefined
               && item.contentY !== undefined
    }

    function isInside(item, vx, vy) {
        var mapped = item.mapFromItem(root, vx, vy)
        return mapped.x >= 0 && mapped.y >= 0
               && mapped.x <= item.width && mapped.y <= item.height
    }

    // Post-order walk so deeper targets (e.g. ListView) come after shallow ScrollViews.
    function collectScrollTargets(item, out) {
        if (!item)
            return
        var kids = item.children
        for (var i = 0; i < kids.length; i++)
            collectScrollTargets(kids[i], out)
        if (item === root)
            return
        if (isScrollView(item)) {
            var f = item.contentItem
            if (f && f.contentHeight > f.height)
                out.push(f)
        } else if (isListView(item)) {
            if (item.contentHeight > item.height)
                out.push(item)
        }
    }

    function findPageFlickable() {
        if (flickable)
            return flickable
        var item = parent
        while (item) {
            if (isScrollView(item))
                return item.contentItem
            item = item.parent
        }
        return null
    }

    function nestedFlickableAt(vx, vy) {
        var searchRoot = nestedSearchRoot || parent
        if (!searchRoot)
            return null
        var targets = []
        collectScrollTargets(searchRoot, targets)
        for (var i = targets.length - 1; i >= 0; i--) {
            var f = targets[i]
            if (isInside(f, vx, vy))
                return f
        }
        return null
    }

    onWheel: function(wheel) {
        var nested = nestedFlickableAt(wheel.x, wheel.y)
        if (nested && scrollFlickable(nested, wheel)) {
            wheel.accepted = true
            return
        }
        var page = findPageFlickable()
        if (page && page !== nested && scrollFlickable(page, wheel))
            wheel.accepted = true
    }
}
