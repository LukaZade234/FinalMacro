import QtQuick
import QtQuick.Layouts
import gui 1.0

// Live smart-saver strip. Hidden entirely when the preset toggle is off.
Item {
    id: root

    property var status: null

    readonly property bool on: !!(status && status.enabled)

    visible: on
    implicitHeight: on ? col.implicitHeight : 0
    implicitWidth: col.implicitWidth
    Layout.fillWidth: true
    Layout.preferredHeight: on ? col.implicitHeight : 0
    Layout.maximumHeight: on ? 400 : 0

    function yn(flag, yes, no) {
        return flag ? yes : no
    }

    function spendText() {
        if (!status || status.spendable_percent === null || status.spendable_percent === undefined)
            return "—"
        var spend = Number(status.spendable_percent)
        var bar = Number(status.power_percent)
        if (isFinite(bar) && spend >= bar - 0.5)
            return "all (" + Math.round(spend) + "%)"
        return Math.round(spend) + "%"
    }

    ColumnLayout {
        id: col
        width: parent.width
        spacing: 6

        Text {
            text: "Smart saver"
            color: Theme.fgMuted
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }

        Flow {
            Layout.fillWidth: true
            spacing: 6

            StatusChip {
                label: "Perk-8 priority"
                value: root.yn(root.status && root.status.perk8_priority, "on", "off")
                tone: (root.status && root.status.perk8_priority) ? "active" : "neutral"
            }
            StatusChip {
                label: "Normal clicks"
                value: root.yn(root.status && root.status.normal_clicks, "allowed", "held")
                tone: (root.status && root.status.normal_clicks) ? "good" : "warn"
            }
            StatusChip {
                label: "Saving power"
                value: root.yn(root.status && root.status.power_blocked, "blocking reacts", "open")
                tone: (root.status && root.status.power_blocked) ? "warn" : "good"
            }
            StatusChip {
                label: "Kakera"
                value: root.yn(root.status && root.status.kakera_free, "free", "limited")
                tone: (root.status && root.status.kakera_free) ? "good" : "active"
            }
            StatusChip {
                label: "Can spend"
                value: root.spendText()
            }
        }
    }
}
