import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Filterable, color-coded activity log for the Run tab (selectable for copy/paste).
ColumnLayout {
    id: root
    spacing: 10
    Layout.fillWidth: true
    Layout.fillHeight: true

    property var entries: []
    property string filter: "all"
    property bool stickToBottom: true

    function severityColor(severity) {
        if (severity === "claim")
            return Theme.success
        if (severity === "click")
            return Theme.accentPrimary
        if (severity === "skip")
            return Theme.fgMuted
        if (severity === "error")
            return Theme.error
        return Theme.fgSecondary
    }

    function filteredEntries() {
        if (root.filter === "all")
            return root.entries
        return root.entries.filter(function(entry) {
            return entry.severity === root.filter
        })
    }

    function countForFilter(id) {
        if (id === "all")
            return root.entries.length
        var n = 0
        for (var i = 0; i < root.entries.length; i++) {
            if (root.entries[i].severity === id)
                n++
        }
        return n
    }

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
    }

    function buildLogHtml() {
        var rows = filteredEntries()
        if (rows.length === 0) {
            var empty = root.entries.length === 0
                ? "No activity yet."
                : "No lines match this filter."
            return '<span style="color:' + Theme.fgMuted + '">' + empty + "</span>"
        }
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var entry = rows[i]
            var color = severityColor(entry.severity).toString()
            var prefix = ""
            if (entry.ts && entry.ts.length >= 19)
                prefix = "[" + entry.ts.substring(11, 19) + "] "
            parts.push('<span style="color:' + color + '">' + escapeHtml(prefix + entry.text) + "</span>")
        }
        return parts.join("<br>")
    }

    function scrollToBottom() {
        Qt.callLater(function() {
            var maxY = Math.max(0, logText.contentHeight - logScroll.height + logText.topPadding + logText.bottomPadding)
            logScroll.contentItem.contentY = maxY
        })
    }

    onEntriesChanged: {
        if (root.stickToBottom)
            scrollToBottom()
    }

    onFilterChanged: {
        if (root.stickToBottom)
            scrollToBottom()
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 6

        Repeater {
            model: [
                { id: "all", label: "All" },
                { id: "claim", label: "Claim" },
                { id: "click", label: "Click" },
                { id: "skip", label: "Skip" },
                { id: "error", label: "Error" },
                { id: "info", label: "Info" }
            ]
            delegate: Rectangle {
                required property var modelData

                implicitHeight: 28
                implicitWidth: chipLabel.implicitWidth + 18
                radius: 14
                color: root.filter === modelData.id ? Theme.bgLight : Theme.bgDark
                border.color: root.filter === modelData.id ? Theme.accentPrimary : Theme.border
                border.width: 1

                Label {
                    id: chipLabel
                    anchors.centerIn: parent
                    text: modelData.label + " (" + root.countForFilter(modelData.id) + ")"
                    color: root.filter === modelData.id ? Theme.fgPrimary : Theme.fgMuted
                    font.pixelSize: 11
                    font.weight: root.filter === modelData.id ? Font.DemiBold : Font.Normal
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.filter = modelData.id
                }
            }
        }

        Item { Layout.fillWidth: true }

        Label {
            text: "Drag to select · Ctrl+C to copy"
            color: Theme.fgMuted
            font.pixelSize: 10
        }
    }

    ScrollView {
        id: logScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        TextEdit {
            id: logText
            width: logScroll.availableWidth
            readOnly: true
            selectByMouse: true
            selectByKeyboard: true
            wrapMode: TextEdit.Wrap
            textFormat: TextEdit.RichText
            text: root.buildLogHtml()
            color: Theme.fgSecondary
            selectionColor: Theme.accentPrimary
            selectedTextColor: Theme.bgDark
            font.family: "Consolas, 'Courier New', monospace"
            font.pixelSize: 13
            topPadding: 12
            bottomPadding: 12
            leftPadding: 12
            rightPadding: 12

            onContentHeightChanged: {
                if (root.stickToBottom)
                    root.scrollToBottom()
            }
        }

        Connections {
            target: logScroll.contentItem
            function onContentYChanged() {
                var flick = logScroll.contentItem
                if (!flick)
                    return
                var maxY = Math.max(
                    0,
                    logText.contentHeight - logScroll.height + logText.topPadding + logText.bottomPadding
                )
                if (flick.contentY < maxY - 24)
                    root.stickToBottom = false
                else if (flick.contentY >= maxY - 4)
                    root.stickToBottom = true
            }
        }

        background: Rectangle {
            radius: 8
            color: Theme.inputBg
            border.color: Theme.border
            border.width: 1
        }
    }
}
