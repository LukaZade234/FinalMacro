import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Mudae — the sheets, for one account on one server.

    A hub in the same shape as `StatisticsView`: a pill bar over a `Loader`, so
    every sub-page is a full view rather than a panel squeezed into a shared
    page.

    The three pills are grouped by what a sheet *is*, not by where it came from.
    `$settings` and `$ov` are settings you configure and copy between servers;
    `$bonus` is what those settings and your account's perks add up to, and sits
    beside them because it is how you check a setting actually landed. `$shop`
    is not a setting at all — it is the sphere economy, and lives on Spheres.
*/
Item {
    id: mudaeRoot
    clip: true

    property int sectionIndex: 0

    // `fetch` is the command the scope bar offers while that pill is open, so
    // the button always fetches the sheet you are looking at. `$ov` has no
    // parser yet, so it offers nothing rather than a button that cannot work.
    readonly property var sections: [
        { label: "$settings", component: settingsSection, fetch: "settings" },
        { label: "$ov", component: ovSection, fetch: "" },
        { label: "$bonus", component: bonusSection, fetch: "bonus" }
    ]

    readonly property string currentFetch: sections[sectionIndex].fetch

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
            fetchCommand: mudaeRoot.currentFetch
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: mudaeRoot.sections

                delegate: PresetSectionTab {
                    required property var modelData
                    required property int index

                    text: modelData.label
                    stretch: false
                    tabActive: mudaeRoot.sectionIndex === index
                    onClicked: mudaeRoot.sectionIndex = index
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: "server rules · personal settings · totals"
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                elide: Text.ElideRight
            }
        }

        Loader {
            id: sectionLoader
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            sourceComponent: mudaeRoot.sections[mudaeRoot.sectionIndex].component
        }
    }

    Component {
        id: settingsSection
        MudaeSettingsSheetView {
            channelProfileId: scope.channelProfileId
        }
    }

    Component {
        id: ovSection
        MudaeOvView {
            accountName: scope.accountName
        }
    }

    Component {
        id: bonusSection
        MudaeBonusView {
            channelProfileId: scope.channelProfileId
            accountId: scope.accountId
            accountName: scope.accountName
        }
    }
}
