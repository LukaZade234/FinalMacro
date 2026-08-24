import QtQuick

import gui 1.0

/*
    Picks the shell for the current design and owns the page index.

    Kept separate from Main.qml so the same switcher can be hosted by the app
    window and by scripts/ui_preview.py.
*/
Item {
    id: switcher

    property int currentPage: 0

    Loader {
        anchors.fill: parent

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
