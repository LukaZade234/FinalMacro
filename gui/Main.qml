import QtQuick
import QtQuick.Controls

import gui 1.0
import "shells"

/*
    Window frame.

    The visible layout lives in gui/shells/<Design>Shell.qml, chosen by
    ShellSwitcher. This file only owns the window itself and keeps Theme pointed
    at the persisted appearance settings.
*/
ApplicationWindow {
    id: win
    width: 1200
    height: 1000
    minimumWidth: 980
    minimumHeight: 680
    visible: true
    title: "FinalMacro"
    color: Theme.bg
    font.family: Theme.fontFamily

    property alias currentPage: switcher.currentPage

    // Theme is a singleton with no access to the App context property, so the
    // window drives it from the persisted settings.
    Binding {
        target: Theme
        property: "layoutId"
        value: App.uiLayout
    }
    Binding {
        target: Theme
        property: "paletteId"
        value: App.uiPalette
    }
    Binding {
        target: Theme
        property: "systemFonts"
        value: App.uiSystemFonts
    }
    Binding {
        target: Theme
        property: "systemFontFamily"
        value: App.systemFontFamily
    }

    // Views that do not set font.family fall back to the application font, so
    // pushing the design's family there keeps every page consistent.
    Connections {
        target: Theme
        function onLayoutIdChanged() { App.applyUiFont(Theme.fontFamily) }
        function onFontFamilyChanged() { App.applyUiFont(Theme.fontFamily) }
    }
    Component.onCompleted: App.applyUiFont(Theme.fontFamily)

    onClosing: function(close) {
        if (App.minimizeToTray) {
            close.accepted = false
            win.hide()
        }
    }

    ShellSwitcher {
        id: switcher
        anchors.fill: parent
    }
}
