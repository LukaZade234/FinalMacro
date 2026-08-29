import QtQuick

import gui 1.0
import "../components"

/*
    A `3px double` box with its caption notched into the top rule.

    QML has no double border style, so the rule is drawn as two hairlines with a
    one pixel gap between them. The caption paints the box fill behind itself,
    which is what masks the rule where the text sits.
*/
Item {
    id: box

    property string caption: ""
    property bool hot: false
    property int contentPadding: 14
    // Optional fold-to-caption control, notched into the top rule on the right.
    property bool collapsible: false
    property bool collapsed: false
    property string stateText: ""
    property bool stateOn: false

    signal toggled()

    default property alias content: body.data

    readonly property color ruleColor: hot ? Theme.accent : Theme.line

    Rectangle {
        anchors.fill: parent
        color: Theme.surface
        border.width: 1
        border.color: box.ruleColor
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 2
        color: "transparent"
        border.width: 1
        border.color: box.ruleColor
    }

    Rectangle {
        visible: box.caption !== ""
        x: 14
        y: -height / 2
        width: captionText.implicitWidth + 16
        height: captionText.implicitHeight
        color: Theme.surface

        Text {
            id: captionText
            anchors.centerIn: parent
            text: box.caption
            color: box.hot ? Theme.accent : Theme.dim
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeSmall
            font.weight: Font.DemiBold
        }
    }

    Rectangle {
        visible: box.collapsible || box.stateText !== ""
        x: parent.width - width - 14
        y: -height / 2
        width: foldRow.implicitWidth + 12
        height: Math.max(foldRow.implicitHeight, captionText.implicitHeight)
        color: Theme.surface

        Row {
            id: foldRow
            anchors.centerIn: parent
            spacing: 5

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: box.stateText !== ""
                text: box.stateText
                color: box.stateOn ? Theme.good : Theme.dim
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeSmall
                font.weight: Font.DemiBold
            }

            PanelCollapseButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: box.collapsible
                collapsed: box.collapsed
                tint: Theme.dim
                onToggled: box.toggled()
            }
        }
    }

    Item {
        id: body
        visible: !box.collapsed
        anchors.fill: parent
        anchors.leftMargin: box.contentPadding
        anchors.rightMargin: box.contentPadding
        anchors.topMargin: box.contentPadding
        anchors.bottomMargin: box.contentPadding - 2
        clip: true
    }
}
