import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Spheres — the sphere economy for one account.

    Current state and decisions: what you hold, what the ouroperk shop charges,
    and which upgrade pays back fastest. Sphere *history* stays on
    Statistics › Spheres; this page is not a second stats view.

    `$shop` lives here rather than on Mudae because it is not a setting — you
    cannot configure or copy it, it is the balance sheet of this economy.
*/
Item {
    id: spheresRoot
    clip: true

    property int sectionIndex: 0

    // `fetch` is the command the scope bar offers while that pill is open.
    // Upgrades offers none: it is computed from the sheets the other two
    // fetch, so there is nothing of its own to ask Mudae for.
    readonly property var sections: [
        { label: "Stock & shop", component: stockSection, fetch: "shop", fetchLabel: "$shop" },
        { label: "Upgrades", component: upgradesSection, fetch: "", fetchLabel: "" },
        { label: "Characters", component: charactersSection, fetch: "wishlist", fetchLabel: "$wl" }
    ]

    readonly property var currentSection: sections[sectionIndex]

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
            fetchCommand: spheresRoot.currentSection.fetch
            fetchLabel: spheresRoot.currentSection.fetchLabel
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: spheresRoot.sections

                delegate: PresetSectionTab {
                    required property var modelData
                    required property int index

                    text: modelData.label
                    stretch: false
                    tabActive: spheresRoot.sectionIndex === index
                    onClicked: spheresRoot.sectionIndex = index
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: "history lives on Statistics › Spheres"
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                elide: Text.ElideRight
            }
        }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            sourceComponent: spheresRoot.sections[spheresRoot.sectionIndex].component
        }
    }

    Component {
        id: stockSection
        SphereStockView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
        }
    }
    Component {
        id: upgradesSection
        SphereUpgradesView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
        }
    }
    Component {
        id: charactersSection
        SphereCharactersView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
        }
    }
}
