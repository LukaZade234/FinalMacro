import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    One panel, in whichever shape the loaded design asks for.

    Most designs draw a filled, bordered, rounded card. **Quiet** draws no box
    at all: a single hairline rule across the top and a small tracked label,
    with the content sitting directly on the window. That is the whole of the
    Quiet restyle, and it lives here rather than in a parallel set of views so
    every page the app already has inherits it untouched — Report keeps its ten
    tiles and every chart, Presets keeps its sections, Debug keeps its two
    panes. Only the chrome around them changes.

    `Theme.flatPanels` picks between the two, and a flat panel also drops its
    own `contentMargins` — with no card edge there is nothing to inset from, so
    the content lines up with the page and the gap between panels separates.
*/
Item {
    id: root
    default property alias content: contentLayout.data
    property string title: ""
    // A flat panel has no edge to inset from: its content lines up with the
    // page, and the gap between panels does the separating. Only PanelCard may
    // assume this — other widgets keep `Theme.cardPadding` because they still
    // draw a box of their own.
    property int contentMargins: Theme.flatPanels ? 0 : Theme.cardPadding
    property int titleSize: Theme.sizeXLarge
    property bool fillContentVertically: false
    // One control in the header, trailing the title — a switch, mainly. Rare
    // enough that it is a named slot rather than a second default property.
    property alias headerAccessory: accessoryRow.data

    // A flat panel's rule and label take vertical room the boxed one spent on
    // padding, so the two end up costing about the same.
    readonly property int topRule: Theme.flatPanels && title !== "" ? 11 : 0

    implicitHeight: innerLayout.implicitHeight + contentMargins * 2 + topRule
    implicitWidth: innerLayout.implicitWidth + contentMargins * 2

    clip: true

    Rectangle {
        visible: !Theme.flatPanels
        anchors.fill: parent
        radius: Theme.radiusLg
        color: Theme.bgMedium
        border.color: Theme.border
        border.width: 1
    }

    // The Boxed design rules its panels with a double border; the inner rule is
    // drawn separately since Rectangle only has a single stroke.
    Rectangle {
        visible: Theme.doubleBorder && !Theme.flatPanels
        anchors.fill: parent
        anchors.margins: 2
        radius: Theme.radiusLg
        color: "transparent"
        border.color: Theme.border
        border.width: 1
    }

    // Quiet's entire panel chrome: one rule, above the label.
    Rectangle {
        visible: Theme.flatPanels && root.title !== ""
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: Theme.border
    }

    ColumnLayout {
        id: innerLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: contentMargins + root.topRule
        anchors.leftMargin: contentMargins
        anchors.rightMargin: contentMargins
        anchors.bottomMargin: contentMargins
        anchors.bottom: root.fillContentVertically ? parent.bottom : undefined
        spacing: Theme.flatPanels ? 10 : 12

        RowLayout {
            Layout.fillWidth: true
            visible: root.title !== "" || accessoryRow.children.length > 0
            spacing: 10

            Label {
                visible: root.title !== ""
                text: Theme.flatPanels ? Theme.sectionLabel(root.title) : root.title
                // Quiet's panel title is a micro-label, not a heading: the
                // content is what should carry weight, not the frame around it.
                color: Theme.flatPanels ? Theme.fgMuted : Theme.fgPrimary
                font.family: Theme.flatPanels ? Theme.monoFamily : Theme.fontFamily
                font.pixelSize: Theme.flatPanels ? Theme.sizeMicro : titleSize
                font.weight: Font.DemiBold
                font.letterSpacing: Theme.flatPanels ? Theme.tracking(Theme.sizeMicro) : 0
                Layout.fillWidth: true
            }

            // Empty unless a caller fills `headerAccessory` — a switch that
            // belongs beside the title rather than as its own content row.
            RowLayout {
                id: accessoryRow
                spacing: 6
            }
        }

        ColumnLayout {
            id: contentLayout
            Layout.fillWidth: true
            Layout.fillHeight: root.fillContentVertically
            spacing: 10
        }
    }
}
