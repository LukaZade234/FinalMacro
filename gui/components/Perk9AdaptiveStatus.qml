pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import gui 1.0

// Live adaptive perk-9 strip, sibling of the smart saver. Hidden when the
// preset toggle is off.
Item {
    id: root

    property var status: null
    property bool collapsed: false

    readonly property bool on: !!(status && status.enabled)
    readonly property bool showBody: on && !collapsed

    implicitHeight: col.implicitHeight
    implicitWidth: col.implicitWidth
    Layout.fillWidth: true
    Layout.preferredHeight: col.implicitHeight

    function clicksText() {
        if (!status)
            return "—"
        return status.clicks_used + " / " + (status.clicks_max || "?")
    }

    function spawnsText() {
        if (!status)
            return "—"
        var seen = status.spawns_seen || 0
        if (status.spawns_total)
            return seen + " / " + status.spawns_total
        return String(seen)
    }

    function leftText() {
        if (!status || status.spawns_left === null || status.spawns_left === undefined)
            return "unknown"
        return String(status.spawns_left)
    }

    function barText() {
        if (!status || status.threshold === null || status.threshold === undefined)
            return "—"
        return "≥ " + status.threshold + " SP"
    }

    function looserText() {
        if (!status || !status.looser_at)
            return "no further change today"
        return "at " + status.looser_at + " spawns left"
    }

    function stricterText() {
        if (!status || !status.stricter_at)
            return ""
        return "with " + status.stricter_at + " click"
            + (status.stricter_at === 1 ? "" : "s") + " left"
    }

    ColumnLayout {
        id: col
        width: parent.width
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: "Adaptive perk 9"
                color: Theme.fgMuted
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }

            Item { Layout.fillWidth: true }

            Text {
                text: root.on ? "on" : "off"
                color: root.on ? Theme.success : Theme.fgMuted
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }

            PanelCollapseButton {
                visible: root.on
                collapsed: root.collapsed
                onToggled: root.collapsed = !root.collapsed
            }
        }

        Flow {
            Layout.fillWidth: true
            visible: root.showBody
            spacing: 6

            StatusChip {
                label: "Clicks"
                value: root.clicksText()
                tone: (root.status && root.status.clicks_left === 0) ? "warn" : "active"
            }
            StatusChip {
                label: "Spawns"
                value: root.spawnsText()
            }
            StatusChip {
                label: "Left today"
                value: root.leftText()
            }
            StatusChip {
                label: "Bar"
                value: root.barText()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.showBody && !!(root.status && root.status.allowed
                && root.status.allowed.length)

            Text {
                Layout.preferredWidth: 92
                text: "Clicking now"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Row {
                Layout.fillWidth: true
                spacing: 3

                Repeater {
                    model: (root.status && root.status.allowed) ? root.status.allowed : []

                    delegate: ThemeSphere {
                        required property string modelData

                        size: 16
                        sphereId: modelData
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.showBody && !!(root.status && root.status.stricter_drops
                && root.status.stricter_drops.length)

            Text {
                Layout.preferredWidth: 92
                text: "Drops"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Row {
                spacing: 3

                Repeater {
                    model: (root.status && root.status.stricter_drops)
                        ? root.status.stricter_drops : []

                    delegate: ThemeSphere {
                        required property string modelData

                        size: 16
                        sphereId: modelData
                        opacity: 0.6
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.stricterText()
                color: Theme.fgMuted
                font.pixelSize: 10
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.showBody && !!(root.status && root.status.looser_adds
                && root.status.looser_adds.length)

            Text {
                Layout.preferredWidth: 92
                text: "Opens up"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Row {
                spacing: 3

                Repeater {
                    model: (root.status && root.status.looser_adds)
                        ? root.status.looser_adds : []

                    delegate: ThemeSphere {
                        required property string modelData

                        size: 16
                        sphereId: modelData
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.looserText()
                color: Theme.fgMuted
                font.pixelSize: 10
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.showBody && !!(root.status && root.status.history
                && root.status.history.length)

            Text {
                Layout.preferredWidth: 92
                text: "Clicked"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Row {
                Layout.fillWidth: true
                spacing: 3

                Repeater {
                    model: (root.status && root.status.history) ? root.status.history : []

                    delegate: ThemeSphere {
                        required property string modelData

                        size: 16
                        sphereId: modelData
                        // Face-down marks a click this session never saw the
                        // colour of, so the row is not silently wrong.
                        opacity: modelData === "spU" ? 0.55 : 1.0
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: root.showBody && !!(root.status && root.status.unknown_clicks)
            text: (root.status ? root.status.unknown_clicks : 0)
                + " earlier click(s) were already used before tracking started"
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }
    }
}
