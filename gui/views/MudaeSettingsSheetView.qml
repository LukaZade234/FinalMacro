import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Mudae › $settings — the server's rule sheet, plus the drift and copy tools
    that act on it.

    Drift and copy live here rather than on a shared overview because they only
    ever touch `$settings`: the preset editor, the diff, the dry run and the
    apply pipeline are all one feature, and it is the sheet they compare against.
    `MudaeSettingsView` is that machinery, moved from a sub-tab of Servers.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.preferredWidth: 340
            Layout.minimumWidth: 260
            Layout.maximumWidth: 420
            Layout.fillHeight: true
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

        MudaeSettingsView {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
