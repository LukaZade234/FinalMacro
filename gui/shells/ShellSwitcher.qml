import QtQuick
import QtQuick.Layouts

import gui 1.0
import "../components"

/*
    Picks the shell for the current design and owns the page index.

    Kept separate from Main.qml so the same switcher can be hosted by the app
    window and by scripts/ui_preview.py.

    A compact update notice sits above every layout; the full update UI lives
    on Settings (page index 7).
*/
Item {
    id: switcher

    property int currentPage: 0
    readonly property int settingsPageIndex: 7

    onCurrentPageChanged: {
        if (currentPage === settingsPageIndex && App.updateAvailable)
            App.dismissUpdate()
    }

    Connections {
        target: App
        function onUpdateStatusChanged() {
            if (switcher.currentPage === switcher.settingsPageIndex && App.updateAvailable)
                App.dismissUpdate()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        UpdateNotice {
            Layout.fillWidth: true
            onOpenSettings: switcher.currentPage = switcher.settingsPageIndex
        }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true

            sourceComponent: {
                switch (Theme.layoutId) {
                case "haul": return haulShell
                case "console": return consoleShell
                case "boxed": return boxedShell
                default: return classicShell
                }
            }

            Component {
                id: classicShell
                ClassicShell {
                    currentPage: switcher.currentPage
                    onNavigate: function(index) { switcher.currentPage = index }
                }
            }
            Component {
                id: haulShell
                HaulShell {
                    currentPage: switcher.currentPage
                    onNavigate: function(index) { switcher.currentPage = index }
                }
            }
            Component {
                id: consoleShell
                ConsoleShell {
                    currentPage: switcher.currentPage
                    onNavigate: function(index) { switcher.currentPage = index }
                }
            }
            Component {
                id: boxedShell
                BoxedShell {
                    currentPage: switcher.currentPage
                    onNavigate: function(index) { switcher.currentPage = index }
                }
            }
        }
    }
}
