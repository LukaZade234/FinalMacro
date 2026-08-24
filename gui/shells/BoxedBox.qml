import QtQuick

import gui 1.0

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

    Item {
        id: body
        anchors.fill: parent
        anchors.leftMargin: box.contentPadding
        anchors.rightMargin: box.contentPadding
        anchors.topMargin: box.contentPadding
        anchors.bottomMargin: box.contentPadding - 2
        clip: true
    }
}
