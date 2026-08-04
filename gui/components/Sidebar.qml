import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Rectangle {
    id: sidebar
    property int currentIndex: 0
    property var navModel: []

    signal navigated(int index)

    color: Theme.bgMedium

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 60

            Column {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0

                Text {
                    text: "Final"
                    color: Theme.accentPrimary
                    font.pixelSize: 22
                    font.weight: Font.Bold
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "Macro"
                    color: Theme.fgSecondary
                    font.pixelSize: 13
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }

        ThemedScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                id: navColumn
                width: sidebar.width
                spacing: 4
                topPadding: 4
                bottomPadding: 8

                Repeater {
                    model: sidebar.navModel.length

                    delegate: NavItem {
                        width: navColumn.width - 20
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: sidebar.navModel[index].label
                        navActive: sidebar.currentIndex === index
                        onClicked: sidebar.navigated(index)
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 8
            spacing: 6

            Button {
                Layout.fillWidth: true
                implicitHeight: 36
                text: "Exit"
                background: Rectangle {
                    radius: 8
                    color: parent.down ? Qt.darker(Theme.error, 1.1) : Theme.error
                }
                contentItem: Text {
                    text: parent.text
                    color: "#ffffff"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.weight: Font.DemiBold
                }
                onClicked: Qt.quit()
            }
        }
    }
}
