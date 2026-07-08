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
        { label: "Soulmates", title: "Soulmates" },
        { label: "Kakera", title: "Kakera" },
        { label: "Spheres", title: "Spheres" },
        { label: "Keys", title: "Keys" }
    ]

    readonly property var sectionSources: [
        "SoulmatesView.qml",
        "KakeraView.qml",
        "SpheresView.qml",
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

                    implicitHeight: 30
                    implicitWidth: chipLabel.implicitWidth + 20
                    radius: 15
                    color: statsRoot.sectionIndex === index
                           ? Theme.accentPrimary : Theme.bgDark
                    border.color: statsRoot.sectionIndex === index
                                  ? Theme.accentPrimary : Theme.border
                    border.width: 1

                    Label {
                        id: chipLabel
                        anchors.centerIn: parent
                        text: modelData.label
                        color: statsRoot.sectionIndex === index
                               ? Theme.bgDark : Theme.fgSecondary
                        font.pixelSize: 11
                        font.weight: statsRoot.sectionIndex === index
                                     ? Font.DemiBold : Font.Normal
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
                text: sections[sectionIndex].title + " statistics"
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
