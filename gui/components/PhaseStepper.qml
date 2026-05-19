import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Item {
    id: root
    property string currentPhase: "Idle"

    readonly property var steps: [
        "Idle",
        "Checking $tu",
        "Rolling",
        "Post-roll",
        "Stopping"
    ]

    implicitHeight: stepRow.implicitHeight
    implicitWidth: stepRow.implicitWidth

    function stepIndex(phase) {
        var i = steps.indexOf(phase)
        return i >= 0 ? i : 0
    }

    readonly property int activeIndex: stepIndex(currentPhase)

    RowLayout {
        id: stepRow
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 6

        Repeater {
            model: root.steps.length

            delegate: RowLayout {
                spacing: 4

                ColumnLayout {
                    spacing: 4

                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 26
                        height: 26
                        radius: 13
                        color: index <= root.activeIndex ? Theme.accentPrimary : Theme.bgDark
                        border.color: index === root.activeIndex ? Theme.accentSecondary : Theme.border
                        border.width: index === root.activeIndex ? 2 : 1

                        Text {
                            anchors.centerIn: parent
                            text: (index + 1).toString()
                            color: index <= root.activeIndex ? Theme.bgDark : Theme.fgMuted
                            font.pixelSize: 10
                            font.weight: Font.Bold
                        }
                    }

                    Text {
                        text: root.steps[index]
                        color: index === root.activeIndex ? Theme.fgPrimary
                              : (index < root.activeIndex ? Theme.fgSecondary : Theme.fgMuted)
                        font.pixelSize: 9
                        Layout.preferredWidth: 68
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                }

                Text {
                    visible: index < root.steps.length - 1
                    text: "→"
                    color: Theme.fgMuted
                    font.pixelSize: 14
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 6
                }
            }
        }
    }
}
