import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Item {
    id: statsRoot
    clip: true
    anchors.fill: parent

    property int sectionIndex: 0

    readonly property var sections: [
        { label: "Report", title: "Daily" },
        { label: "Soulmates", title: "Soulmates" },
        { label: "Kakera", title: "Kakera" },
        { label: "Spheres", title: "Spheres" },
        { label: "Minigames", title: "Minigames" },
        { label: "Keys", title: "Keys" }
    ]

    readonly property var sectionSources: [
        "DailyReportView.qml",
        "SoulmatesView.qml",
        "KakeraView.qml",
        "SpheresView.qml",
        "MinigamesView.qml",
        "KeysView.qml"
    ]

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: statsRoot.sections

                delegate: Rectangle {
                    required property var modelData
                    required property int index

                    readonly property bool current: statsRoot.sectionIndex === index

                    implicitHeight: 30
                    implicitWidth: chipLabel.implicitWidth + (Theme.flatPanels ? 4 : 20)
                    // Quiet marks the open section with an underline instead of
                    // a filled pill, the same mark its nav uses.
                    radius: Theme.flatPanels ? 0 : 15
                    color: Theme.flatPanels ? "transparent"
                         : (current ? Theme.accentPrimary : Theme.bgDark)
                    border.color: Theme.flatPanels ? "transparent"
                                : (current ? Theme.accentPrimary : Theme.border)
                    border.width: Theme.flatPanels ? 0 : 1

                    Rectangle {
                        visible: Theme.flatPanels && parent.current
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: Theme.accent
                    }

                    Label {
                        id: chipLabel
                        anchors.centerIn: parent
                        text: modelData.label
                        color: Theme.flatPanels
                               ? (parent.current ? Theme.fg : Theme.mute)
                               : (parent.current ? Theme.bgDark : Theme.fgSecondary)
                        font.pixelSize: 11
                        font.weight: parent.current ? Font.DemiBold : Font.Normal
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: statsRoot.sectionIndex = index
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: sectionIndex === 0 ? "Daily report"
                          : sections[sectionIndex].title + " statistics"
                color: Theme.fgMuted
                font.pixelSize: 11
            }
        }

        Loader {
            id: sectionLoader
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            source: sectionSources[sectionIndex]

            onLoaded: {
                if (item)
                    item.anchors.fill = sectionLoader
            }
        }
    }
}
