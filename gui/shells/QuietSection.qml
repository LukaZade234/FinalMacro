import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    One block of the Quiet side column: a hairline rule, a tracked label with an
    optional on/off state at its right, then the content. The same shape
    `PanelCard` takes when `Theme.flatPanels` is set, kept separate because the
    side column wants the state marker and a tighter rhythm.
*/
Item {
    id: section
    default property alias content: body.data

    property string title: ""
    property string status: ""
    property bool statusGood: false
    // The first block in a column has nothing above it to be ruled off from.
    property bool ruled: true

    implicitHeight: col.implicitHeight
    Layout.preferredHeight: col.implicitHeight

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 9

        Rectangle {
            visible: section.ruled
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.line
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: section.ruled ? 2 : 0
            spacing: 8

            Label {
                text: Theme.sectionLabel(section.title)
                color: Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
            }

            Item { Layout.fillWidth: true }

            Label {
                visible: section.status !== ""
                text: Theme.sectionLabel(section.status)
                color: section.statusGood ? Theme.good : Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
            }
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: 7
        }
    }
}
