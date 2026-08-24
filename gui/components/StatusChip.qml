import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Rectangle {
    id: chip
    property string label: ""
    property string value: "—"
    property bool highlighted: false
    property string tone: "neutral"  // neutral | good | warn | active

    readonly property bool toneGood: tone === "good"
    readonly property bool toneWarn: tone === "warn"
    readonly property bool toneActive: tone === "active" || highlighted

    implicitHeight: chipRow.implicitHeight + 16
    implicitWidth: Math.max(88, chipRow.implicitWidth + 24)
    radius: Theme.radiusMd
    color: chip.toneActive ? Qt.rgba(0.48, 0.64, 0.97, 0.12)
          : chip.toneGood ? Qt.rgba(0.62, 0.81, 0.42, 0.12)
          : chip.toneWarn ? Qt.rgba(0.88, 0.69, 0.41, 0.12)
          : Theme.bgDark
    border.color: chip.toneActive ? Theme.accentPrimary
                : chip.toneGood ? Theme.success
                : chip.toneWarn ? Theme.warning
                : Theme.border
    border.width: 1

    RowLayout {
        id: chipRow
        anchors.centerIn: parent
        spacing: 6

        Text {
            text: chip.label + ":"
            color: Theme.fgMuted
            font.pixelSize: 11
        }
        Text {
            text: chip.value
            color: chip.toneActive ? Theme.accentPrimary
                  : chip.toneGood ? Theme.success
                  : chip.toneWarn ? Theme.warning
                  : Theme.fgPrimary
            font.pixelSize: 12
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
    }
}
