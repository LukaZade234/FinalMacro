pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import gui 1.0

// One labelled row of sphere artwork for the adaptive perk-9 strip. Shared by
// every shell so the four Run pages cannot drift on this.
RowLayout {
    id: root

    property string label: ""
    property var spheres: []
    property string note: ""
    property real sphereOpacity: 1.0
    property int sphereSize: 16
    property int labelWidth: 92

    visible: spheres && spheres.length > 0
    spacing: 6

    Text {
        Layout.preferredWidth: root.labelWidth
        Layout.alignment: Qt.AlignTop
        text: root.label
        color: Theme.fgMuted
        font.family: Theme.fontFamily
        font.pixelSize: 10
    }

    // Flow, not Row: a full click history is wider than the narrow shell rails.
    Flow {
        Layout.fillWidth: true
        spacing: 3

        Repeater {
            model: root.spheres

            delegate: ThemeSphere {
                required property string modelData

                size: root.sphereSize
                sphereId: modelData
                // Face-down entries are clicks whose colour was never seen.
                opacity: modelData === "spU" ? 0.55 : root.sphereOpacity
            }
        }

        Text {
            visible: root.note !== ""
            text: " " + root.note
            color: Theme.fgMuted
            font.family: Theme.fontFamily
            font.pixelSize: 10
            height: root.sphereSize
            verticalAlignment: Text.AlignVCenter
        }
    }
}
