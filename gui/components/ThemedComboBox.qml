import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent ComboBox: dark field, themed dropdown list.
ComboBox {
    id: control

    implicitHeight: 32

    background: Rectangle {
        implicitWidth: 120
        radius: 6
        color: Theme.inputBg
        border.color: control.pressed || control.popup.visible ? Theme.accentPrimary : Theme.border
        border.width: 1
        opacity: control.enabled ? 1 : 0.5
    }

    contentItem: Text {
        leftPadding: 10
        rightPadding: 24
        text: control.displayText
        color: control.enabled ? Theme.fgPrimary : Theme.fgMuted
        font.pixelSize: 12
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Text {
        x: control.width - width - 8
        anchors.verticalCenter: parent.verticalCenter
        text: "\u25be"
        color: Theme.fgMuted
        font.pixelSize: 12
    }

    delegate: ItemDelegate {
        id: itemDelegate
        required property var modelData
        required property int index

        width: control.width
        height: 30
        highlighted: control.highlightedIndex === index

        contentItem: Text {
            text: control.textAt(index)
            color: Theme.fgPrimary
            font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            leftPadding: 6
        }

        background: Rectangle {
            radius: 4
            color: itemDelegate.highlighted ? Theme.bgLight : "transparent"
        }
    }

    popup: Popup {
        y: control.height + 2
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 260)
        padding: 4

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }

        background: Rectangle {
            radius: 6
            color: Theme.bgMedium
            border.color: Theme.border
            border.width: 1
        }
    }
}
