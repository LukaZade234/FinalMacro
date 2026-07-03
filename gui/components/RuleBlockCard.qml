import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Rectangle {
    id: card
    radius: 10
    color: Theme.bgMedium
    border.color: Theme.border
    border.width: 1

    property string title: ""
    property string subtitle: ""
    property bool enabled_: false
    property bool expanded: true
    property bool showEnableToggle: true
    default property alias content: bodyLayout.data

    signal enabledToggled(bool value)

    implicitHeight: outer.implicitHeight + 24
    implicitWidth: 300

    ColumnLayout {
        id: outer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: card.title
                color: Theme.fgPrimary
                font.pixelSize: 13
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }

            ThemedSwitch {
                id: enableSwitch
                visible: card.showEnableToggle
                checked: card.enabled_
                onToggled: card.enabledToggled(checked)
            }

            ToolButton {
                text: card.expanded ? "▾" : "▸"
                // The body is only shown while the card is enabled, so the
                // expander has nothing to do when the card is off.
                visible: card.showEnableToggle ? card.enabled_ : true
                onClicked: card.expanded = !card.expanded
                contentItem: Text {
                    text: parent.text
                    color: Theme.fgSecondary
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        Label {
            visible: card.subtitle.length > 0
            text: card.subtitle
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        ColumnLayout {
            id: bodyLayout
            Layout.fillWidth: true
            visible: card.showEnableToggle ? (card.expanded && card.enabled_) : card.expanded
            spacing: 8
        }
    }
}
