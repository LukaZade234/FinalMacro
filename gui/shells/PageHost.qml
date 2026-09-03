import QtQuick

import "../views"

/*
    Loads the view for a page index.

    Every design shares the same ten pages and the same view files; only the
    Run page differs, so each shell passes its own `runComponent`.

    The index is the contract between here and every shell's nav array, plus
    `ShellSwitcher.settingsPageIndex`, `IconRail.settingsIndex` and
    `scripts/ui_preview.py`. Inserting a page means updating all of them.
*/
Loader {
    id: host

    property int pageIndex: 0
    property Component runComponent: null

    clip: true

    sourceComponent: {
        switch (pageIndex) {
        case 1: return accountsPage
        case 2: return serversPage
        case 3: return presetsPage
        case 4: return mudaePage
        case 5: return spheresPage
        case 6: return advisorPage
        case 7: return statisticsPage
        case 8: return debugPage
        case 9: return settingsPage
        default: return host.runComponent
        }
    }

    Component {
        id: mudaePage
        MudaeView { anchors.fill: parent }
    }

    Component {
        id: spheresPage
        SpheresHubView { anchors.fill: parent }
    }

    Component {
        id: advisorPage
        AdvisorView { anchors.fill: parent }
    }

    Component {
        id: accountsPage
        AccountsView { anchors.fill: parent }
    }
    Component {
        id: serversPage
        ServersView { anchors.fill: parent }
    }
    Component {
        id: presetsPage
        PresetsView { anchors.fill: parent }
    }
    Component {
        id: statisticsPage
        StatisticsView { anchors.fill: parent }
    }
    Component {
        id: debugPage
        ParseLabView { anchors.fill: parent }
    }
    Component {
        id: settingsPage
        SettingsView { anchors.fill: parent }
    }
}
