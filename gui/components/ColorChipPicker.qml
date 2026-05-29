import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Item {
    id: picker
    implicitHeight: layout.implicitHeight
    Layout.fillWidth: true

    property string title: "Colors"
    // [{ id, label, color, icon? }] — `icon` is an image URL; when present it
    // replaces the colored dot.
    property var options: []
    property var selected: []
    signal selectionChanged(var ids)

    function isSelected(id) {
        return selected.indexOf(id) !== -1
    }

    function toggle(id) {
        var next = selected.slice()
        var idx = next.indexOf(id)
        if (idx === -1)
            next.push(id)
        else
            next.splice(idx, 1)
        selected = next
        selectionChanged(next)
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        spacing: 6

        Label {
            visible: picker.title.length > 0
            text: picker.title
            color: Theme.fgSecondary
            font.pixelSize: 11
            Layout.fillWidth: true
        }

        Flow {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: picker.options
                delegate: Rectangle {
                    id: chip
                    readonly property bool selected: picker.isSelected(modelData.id)
                    readonly property bool hasIcon: !!modelData.icon

                    width: chipRow.implicitWidth + 16
                    height: 28
                    radius: 14
                    color: selected ? Theme.accentPrimary : Theme.bgDark
                    border.color: selected ? Theme.accentPrimary : Theme.border
                    border.width: 1

                    Row {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 6

                        Image {
                            visible: chip.hasIcon
                            anchors.verticalCenter: parent.verticalCenter
                            source: modelData.icon || ""
                            sourceSize.width: 18
                            sourceSize.height: 18
                            width: 18
                            height: 18
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                        }

                        Rectangle {
                            visible: !chip.hasIcon
                            anchors.verticalCenter: parent.verticalCenter
                            width: 12
                            height: 12
                            radius: 6
                            color: modelData.color || Theme.fgMuted
                            border.color: Theme.border
                        }

                        Text {
                            text: modelData.label
                            color: chip.selected ? Theme.bgDark : Theme.fgPrimary
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: picker.toggle(modelData.id)
                    }
                }
            }
        }
    }
}
