import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Filterable, color-coded activity log for the Run tab.
ColumnLayout {
    id: root
    spacing: 8
    Layout.fillWidth: true
    Layout.fillHeight: true

    property var entries: []
    property string filter: "all"

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

                implicitHeight: 24
                implicitWidth: chipLabel.implicitWidth + 16
                radius: 12
                color: root.filter === modelData.id ? Theme.bgLight : Theme.bgDark
                border.color: root.filter === modelData.id ? Theme.accentPrimary : Theme.border
                border.width: 1

                Label {
                    id: chipLabel
                    anchors.centerIn: parent
                    text: modelData.label + " (" + root.countForFilter(modelData.id) + ")"
                    color: root.filter === modelData.id ? Theme.fgPrimary : Theme.fgMuted
                    font.pixelSize: 10
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
    }

    ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        ListView {
            id: logList
            width: parent.width
            clip: true
            spacing: 2
            model: root.filteredEntries()
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                required property var modelData
                width: logList.width
                implicitHeight: lineText.implicitHeight + 4

                Label {
                    id: lineText
                    width: parent.width
                    text: modelData.text
                    color: root.severityColor(modelData.severity)
                    font.family: "Consolas, monospace"
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
            }

            Label {
                anchors.centerIn: parent
                visible: logList.count === 0
                text: root.entries.length === 0
                    ? "No activity yet."
                    : "No lines match this filter."
                color: Theme.fgMuted
                font.pixelSize: 11
            }
        }

        background: Rectangle {
            radius: 6
            color: Theme.bgDark
            border.color: Theme.border
        }
    }
}
