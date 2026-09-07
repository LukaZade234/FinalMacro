import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Mudae › $settings — the server's rule sheet, read.

    Shown the same way `$ov` and `$bonus` are: the parsed sheet and nothing
    else. The drift / preset / diff / dry-run / apply machinery that used to
    share this page is `views/MudaeSettingsView.qml`, which is no longer
    mounted anywhere — it is kept rather than deleted because the pipeline
    behind it (`macro/settings_apply.py`, `mudae/settings_commands.py` and
    their tests) is intact and the page can be put back by mounting it here.

    Editing a server's settings means sending commands that change the live
    server, which is a heavier thing than reading a sheet and wants its own
    deliberate return rather than riding along beside the read-only view.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""

    PanelCard {
        anchors.fill: parent
        title: "$settings (parsed)"
        titleSize: Theme.sizeMedium
        fillContentVertically: true

        MudaeSheetPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            sheetKind: "settings"
            channelProfileId: root.channelProfileId
        }
    }
}
