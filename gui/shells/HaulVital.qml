import QtQuick

import gui 1.0

/*
    One `.vt` tile from the Haul vitals row: uppercase key, a large value with an
    optional smaller suffix, and either a progress track or a sub-caption.

    Set `fraction` to -1 to hide the track (used when the macro has no scale for
    the value yet, e.g. rolls before $settings has been read); the caption is
    shown in its place.
*/
Item {
    id: vital

    property string label: ""
    property string value: "—"
    property string suffix: ""
    property string caption: ""
    property real fraction: -1
    // "neutral" | "good" | "warn" | "accent"
    property string tone: "neutral"
    property bool phase: false
    property bool pulsing: false

    readonly property color toneColor: {
        switch (tone) {
        case "good": return Theme.good
        case "warn": return Theme.warn
        case "accent": return Theme.accent
        default: return Theme.fg
        }
    }

    implicitHeight: 78
    clip: true

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusLg - 4
        color: vital.phase ? Theme.blend(Theme.accent, Theme.surface, 0.09) : Theme.surface
        border.width: 1
        border.color: vital.phase ? Theme.fade(Theme.accent, 0.40) : Theme.line
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 13
        anchors.rightMargin: 13
        anchors.topMargin: 10
        spacing: 3

        Text {
            text: Theme.sectionLabel(vital.label)
            color: Theme.mute
            font.family: Theme.fontFamily
            font.pixelSize: Theme.sizeMicro
            font.weight: Font.DemiBold
            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
        }

        Row {
            width: parent.width
            spacing: 7

            Rectangle {
                visible: vital.phase
                width: 7
                height: 7
                radius: 3.5
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.accent

                SequentialAnimation on opacity {
                    running: vital.pulsing
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 750 }
                    NumberAnimation { to: 1.0; duration: 750 }
                }
            }

            Text {
                id: valueText
                text: vital.value
                color: vital.phase ? Theme.accent : vital.toneColor
                font.family: Theme.fontFamily
                font.pixelSize: Theme.sizeXLarge
                font.weight: Font.Bold
                font.letterSpacing: -0.02 * Theme.sizeXLarge
            }

            Text {
                anchors.baseline: valueText.baseline
                visible: vital.suffix !== ""
                text: vital.suffix
                color: Theme.mute
                font.family: Theme.fontFamily
                font.pixelSize: Theme.sizeBody
                font.weight: Font.Medium
            }
        }
    }

    Rectangle {
        visible: vital.fraction >= 0
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 13
        anchors.rightMargin: 13
        anchors.bottomMargin: 13
        height: 3
        radius: 2
        color: Theme.raised

        Rectangle {
            width: parent.width * Math.min(1, Math.max(0, vital.fraction))
            height: parent.height
            radius: parent.radius
            color: vital.tone === "neutral" ? Theme.accent : vital.toneColor

            Behavior on width {
                NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
            }
        }
    }

    Text {
        visible: vital.fraction < 0 && vital.caption !== ""
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 13
        anchors.rightMargin: 13
        anchors.bottomMargin: 9
        text: vital.caption
        color: Theme.mute
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeTiny
        elide: Text.ElideRight
    }
}
