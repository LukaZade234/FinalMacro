import QtQuick

import gui 1.0
import "../gui/shells"

// Host for scripts/ui_preview.py — the same shell switcher the app window uses,
// but in a QQuickView so the scene can be grabbed to an image.
Item {
    id: root

    property string layoutId: "haul"
    property string paletteId: "kakera"
    property int currentPage: 0

    Binding { target: Theme; property: "layoutId"; value: root.layoutId }
    Binding { target: Theme; property: "paletteId"; value: root.paletteId }

    Connections {
        target: Theme
        function onLayoutIdChanged() { App.applyUiFont(Theme.fontFamily) }
    }
    Component.onCompleted: App.applyUiFont(Theme.fontFamily)

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    ShellSwitcher {
        anchors.fill: parent
        currentPage: root.currentPage
    }
}
