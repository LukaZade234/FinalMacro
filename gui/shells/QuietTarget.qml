import QtQuick
import QtQuick.Controls

import gui 1.0

/*
    Quiet's picker: a small tracked key over the current value, underlined by a
    hairline. The other shells put this in a filled, bordered tile — here the
    rule *is* the control, which is the same trade the panels make.

    `highlight` marks the preset, the one target that changes behaviour rather
    than just where the macro points.
*/
Item {
    id: selector

    property string label: ""
    property string value: ""
    property var options: []
    property int currentIndex: -1
    property bool highlight: false
    // A target that cannot be changed here — drawn without the caret so it does
    // not invite a click that does nothing.
    property bool readOnly: false

    signal picked(int index)

    implicitHeight: 44
    implicitWidth: Math.max(keyLabel.implicitWidth, valueRow.implicitWidth) + 2

    Label {
        id: keyLabel
        anchors.left: parent.left
        anchors.top: parent.top
        text: Theme.sectionLabel(selector.label)
        color: Theme.mute
        font.family: Theme.monoFamily
        font.pixelSize: Theme.sizeMicro
        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
    }

    Row {
        id: valueRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: rule.top
        anchors.bottomMargin: 5
        spacing: 5

        Label {
            width: Math.min(implicitWidth, valueRow.width - (selector.readOnly ? 0 : 14))
            text: selector.value || "—"
            color: selector.highlight ? Theme.accent : Theme.fg
            font.pixelSize: Theme.sizeLarge
            font.weight: Font.Medium
            elide: Text.ElideRight
        }

        Label {
            visible: !selector.readOnly
            anchors.baseline: undefined
            text: "▾"
            color: Theme.mute
            font.pixelSize: Theme.sizeSmall
        }
    }

    Rectangle {
        id: rule
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: selector.highlight ? Theme.fade(Theme.accent, 0.5)
                                  : (hover.containsMouse && !selector.readOnly
                                     ? Theme.mute : Theme.line)
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: !selector.readOnly
        enabled: !selector.readOnly && selector.options.length > 0
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: menu.open()
    }

    Menu {
        id: menu
        y: selector.height

        Repeater {
            model: selector.options
            delegate: MenuItem {
                required property string modelData
                required property int index
                text: modelData
                onTriggered: selector.picked(index)
            }
        }
    }
}
