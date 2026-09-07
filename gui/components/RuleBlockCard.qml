import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    An enable-toggleable rule block: title + on/off switch + collapse chevron,
    then its own content. Presets' Claims / Kakera / Spheres sections are each
    one of these.

    Shares its chrome with `components/PanelCard.qml` rather than drawing its
    own: under `Theme.flatPanels` this is a hairline rule and a mono label like
    every other panel, instead of the curved box every other page already
    dropped.
*/
Item {
    id: card

    property string title: ""
    property string subtitle: ""
    property bool enabled_: false
    property bool expanded: true
    property bool showEnableToggle: true
    default property alias content: bodyLayout.data

    signal enabledToggled(bool value)

    readonly property int topRule: Theme.flatPanels ? 11 : 0
    readonly property int pad: Theme.flatPanels ? 0 : 12

    implicitHeight: outer.implicitHeight + pad * 2 + topRule
    Layout.fillWidth: true

    Rectangle {
        visible: !Theme.flatPanels
        anchors.fill: parent
        radius: Theme.panelRadius
        color: Theme.panelFill
        border.color: Theme.border
        border.width: Theme.panelBorder
    }

    Rectangle {
        visible: Theme.flatPanels
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: Theme.line
    }

    ColumnLayout {
        id: outer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: card.pad + card.topRule
        anchors.leftMargin: card.pad
        anchors.rightMargin: card.pad
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: Theme.flatPanels ? Theme.sectionLabel(card.title) : card.title
                color: Theme.flatPanels ? Theme.fgMuted : Theme.fgPrimary
                font.family: Theme.flatPanels ? Theme.monoFamily : Theme.fontFamily
                font.pixelSize: Theme.flatPanels ? Theme.sizeMicro : 13
                font.weight: Font.DemiBold
                font.letterSpacing: Theme.flatPanels ? Theme.tracking(Theme.sizeMicro) : 0
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
