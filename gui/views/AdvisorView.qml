import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor — calculators and lists that change how you roll.

    Each pill is a tool with its own inputs and its own page, not a one-line
    recommendation, so each gets a real view. Every page states its evidence:
    what it measured, over how much data, and what it is still assuming.
*/
Item {
    id: advisorRoot
    clip: true

    property int sectionIndex: 0

    readonly property var sections: [
        { label: "$bw", component: bwSection },
        { label: "Key EV", component: keySection },
        { label: "Wishlist", component: wishlistSection },
        { label: "Lists", component: listsSection },
        { label: "Formatter", component: formatterSection }
    ]

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        ScopeBar {
            id: scope
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: advisorRoot.sections

                delegate: PresetSectionTab {
                    required property var modelData
                    required property int index

                    text: modelData.label
                    stretch: false
                    tabActive: advisorRoot.sectionIndex === index
                    onClicked: advisorRoot.sectionIndex = index
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: "every answer shows its evidence"
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                elide: Text.ElideRight
            }
        }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            sourceComponent: advisorRoot.sections[advisorRoot.sectionIndex].component
        }
    }

    Component {
        id: bwSection
        BwAdvisoryView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
        }
    }
    Component {
        id: keySection
        KeyEvView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
        }
    }
    Component {
        id: wishlistSection
        AppWishlistView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
        }
    }
    Component { id: listsSection; MudaeListsView {} }
    Component { id: formatterSection; ListFormatterView {} }
}
