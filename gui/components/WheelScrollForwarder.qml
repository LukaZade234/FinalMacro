import QtQuick
import QtQuick.Controls

// Catches wheel events over non-scrollable controls and scrolls the nearest target.
// MouseArea with scrollGestureEnabled handles VNC / xpra wheel events reliably.
Item {
    id: root

    property var flickable: null
    property Item nestedSearchRoot: null
    // Match ThemedScrollView.wheelRotationScale (60 px per ±120° notch).
    property real pixelsPerWheelStep: 60

    function wheelDelta(source) {
        var angleY = 0
        var pixelY = 0
        if (source.angleDelta !== undefined)
            angleY = source.angleDelta.y || 0
        if (source.pixelDelta !== undefined)
            pixelY = source.pixelDelta.y || 0
        if (angleY !== 0)
            return angleY * pixelsPerWheelStep / 120
        if (pixelY !== 0)
            return pixelY * 10
        // Some VNC servers emit wheel clicks with no delta fields.
        return pixelsPerWheelStep
    }

    function scrollFlickable(flick, source) {
        if (!flick || flick.contentHeight <= flick.height)
            return false
        var dy = wheelDelta(source)
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
            if (item.contentY !== undefined && item.contentHeight !== undefined
                && item.model === undefined)
                return item
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

    function handleWheel(vx, vy, source) {
        var nested = nestedFlickableAt(vx, vy)
        if (nested && scrollFlickable(nested, source))
            return true
        var page = findPageFlickable()
        return page && page !== nested && scrollFlickable(page, source)
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        scrollGestureEnabled: true
        hoverEnabled: false

        onWheel: function(wheel) {
            if (root.handleWheel(wheel.x, wheel.y, wheel))
                wheel.accepted = true
        }
    }
}
