import QtQuick

import "../views"

/*
    Loads the view for a page index.

    Every design shares the same eight pages and the same view files; only the
    Run page differs, so each shell passes its own `runComponent`.
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
        case 4: return statisticsPage
        case 5: return debugPage
        case 6: return utilitiesPage
        case 7: return settingsPage
        default: return host.runComponent
        }
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
        id: utilitiesPage
        UtilitiesView { anchors.fill: parent }
    }
    Component {
        id: settingsPage
        SettingsView { anchors.fill: parent }
    }
}
