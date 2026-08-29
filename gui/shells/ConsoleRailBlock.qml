import QtQuick

import gui 1.0
import "../components"

/*
    A titled group of label/value rows in the Console rail.
    `rows` is a list of { label, value, tone } where tone is "", "accent" or "good".
*/
Item {
    id: block

    property string title: ""
    property var rows: []
    // Optional fold-to-title-line control, used by the Run status panels.
    property bool collapsible: false
    property bool collapsed: false
    property string stateText: ""
    property bool stateOn: false

    signal toggled()

    implicitHeight: column.implicitHeight

    Column {
        id: column
        width: parent.width
        spacing: 0

        Item {
            width: column.width
            height: caption.implicitHeight + 7

            Text {
                id: caption
                anchors.left: parent.left
                anchors.top: parent.top
                text: Theme.sectionLabel(block.title)
                color: Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
            }

            Text {
                anchors.right: fold.visible ? fold.left : parent.right
                anchors.rightMargin: fold.visible ? 6 : 0
                anchors.verticalCenter: caption.verticalCenter
                visible: block.stateText !== ""
                text: block.stateText
                color: block.stateOn ? Theme.good : Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
                font.weight: Font.DemiBold
            }

            PanelCollapseButton {
                id: fold
                anchors.right: parent.right
                anchors.verticalCenter: caption.verticalCenter
                visible: block.collapsible
                collapsed: block.collapsed
                tint: Theme.mute
                onToggled: block.toggled()
            }
        }

        Repeater {
            model: block.collapsed ? [] : block.rows

            delegate: Item {
                required property var modelData

                width: column.width
                height: 22

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: Theme.dim
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                }

                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value
                    color: modelData.tone === "accent" ? Theme.accent
                        : (modelData.tone === "good" ? Theme.good : Theme.fg)
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
