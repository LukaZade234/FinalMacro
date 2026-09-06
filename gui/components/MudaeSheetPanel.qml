import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    One parsed Mudae sheet — `$settings`, `$ov`, `$bonus` or `$shop` — as
    label/value rows grouped into sections.

    Replaces three near-identical panels that differed only in which bridge slot
    they called, an empty-state hint, whether valueless rows were hidden, a
    starwish/bku icon on `$bonus`, and a value-column width fraction. Those are
    now the properties below.

    `$ov`, `$bonus` and `$shop` describe the *connected account*, not the server,
    so they are stored per account (`gui/sheet_store.py`) and this panel reports
    which account it is showing and when that sheet was read. A sheet saved
    before that split is marked `inferred` rather than passed off as measured.

    Sizes and colours come from `Theme` rather than being hardcoded, so the
    panel takes the shape of whichever shell is loaded.
*/
Item {
    id: panel

    implicitHeight: 320
    implicitWidth: 280

    // "settings" | "ov" | "bonus" | "shop"
    property string sheetKind: "settings"
    property string channelProfileId: ""
    // Blank asks the bridge for the account this channel is run as.
    property string accountId: ""

    property var displayData: ({ sections: [], field_count: 0 })

    readonly property bool isSettings: sheetKind === "settings"
    readonly property bool isOv: sheetKind === "ov"
    readonly property string commandName: "$" + sheetKind

    // The two settings sheets print a fixed line list, so a field with no value
    // is news — it means Mudae stopped printing it — and stays visible as "—".
    // `$bonus` and `$shop` list only what you have unlocked, where an unset row
    // is the normal case and a wall of them is noise.
    readonly property bool hideEmptyRows: !isSettings && !isOv
    readonly property bool showCommandChip: sheetKind !== "shop"
    readonly property bool showFieldIcon: sheetKind === "bonus"
    // `$ov` labels are sentences ("Emoji for disabled characters"), where the
    // other sheets' are two or three words, so the label column widens for it
    // rather than eliding most of the sheet.
    readonly property real labelWidth: isOv ? 212 : 118
    readonly property real labelMaxWidth: isOv ? 260 : 140

    readonly property real valueWidthFraction: {
        if (sheetKind === "shop") return 0.55
        // `$ov` values are phrases ("depend on the $togglebutton value"), not
        // numbers, so they need more of the row than the other sheets.
        if (sheetKind === "ov") return 0.46
        if (sheetKind === "bonus") return 0.42
        return 0.35
    }

    readonly property string emptyHint: {
        var base = "No " + commandName + " yet — set this channel on Run, connect, then Fetch " + commandName
        if (sheetKind === "bonus")
            return base + " (fetch $settings first for rolls/h)."
        return base + "."
    }

    readonly property string accountLabel: String(displayData.account_id || "")
    readonly property bool inferred: !!displayData.inferred
    readonly property string readAt: String(displayData.read_at || "")

    function fieldIcon(field) {
        if (!showFieldIcon)
            return ""
        var f = String(field || "")
        if (f.indexOf("starwish") !== -1)
            return MudaeEmoji.urlFor("starwish")
        if (f.indexOf("bku") !== -1)
            return MudaeEmoji.urlFor("bku")
        return ""
    }

    function rowVisible(row) {
        return !hideEmptyRows || !!row.has_value
    }

    function sectionVisible(section) {
        if (!hideEmptyRows)
            return true
        var rows = section.rows || []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].has_value)
                return true
        }
        return false
    }

    function refresh() {
        if (!channelProfileId) {
            displayData = { sections: [], field_count: 0 }
            return
        }
        try {
            var raw
            if (sheetKind === "bonus")
                raw = App.formatChannelBonusDisplayJson(channelProfileId, accountId)
            else if (sheetKind === "shop")
                raw = App.formatChannelShopDisplayJson(channelProfileId, accountId)
            else if (sheetKind === "ov")
                raw = App.formatChannelOvDisplayJson(channelProfileId, accountId)
            else
                raw = App.formatChannelSettingsDisplayJson(channelProfileId)
            displayData = JSON.parse(raw)
        } catch (e) {
            displayData = { sections: [], field_count: 0 }
        }
    }

    Connections {
        target: App
        function onServersChanged() { panel.refresh() }
        function onConfigChanged() { panel.refresh() }
    }

    onChannelProfileIdChanged: refresh()
    onAccountIdChanged: refresh()
    onSheetKindChanged: refresh()
    Component.onCompleted: refresh()

    ScrollView {
        id: displayScroll
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: displayScroll.availableWidth
            spacing: Theme.gap

            Label {
                visible: !panel.channelProfileId
                Layout.fillWidth: true
                text: "Select a channel to view parsed " + panel.commandName + "."
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                wrapMode: Text.WordWrap
            }

            Label {
                visible: panel.channelProfileId && panel.displayData.field_count === 0
                Layout.fillWidth: true
                text: panel.emptyHint
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                wrapMode: Text.WordWrap
            }

            // Which account this sheet belongs to, and how much to trust it.
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                visible: !panel.isSettings
                         && panel.displayData.field_count > 0

                Rectangle {
                    visible: panel.inferred
                    Layout.preferredHeight: 16
                    Layout.preferredWidth: inferredLabel.implicitWidth + 12
                    radius: Theme.radiusXs
                    color: Theme.fade(Theme.warn, 0.16)
                    border.width: 1
                    border.color: Theme.fade(Theme.warn, 0.4)

                    Label {
                        id: inferredLabel
                        anchors.centerIn: parent
                        text: Theme.sectionLabel("inferred")
                        color: Theme.warn
                        font.pixelSize: Theme.sizeMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: panel.inferred
                          ? "Saved before sheets were per-account — re-fetch to be sure."
                          : (panel.readAt ? "read " + panel.readAt.substring(0, 16).replace("T", " ") + " UTC" : "")
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    elide: Text.ElideRight
                }
            }

            Repeater {
                model: panel.displayData.sections || []

                delegate: ColumnLayout {
                    required property var modelData

                    Layout.fillWidth: true
                    spacing: 6
                    visible: panel.sectionVisible(modelData)

                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        text: Theme.sectionLabel(modelData.title || "")
                        color: Theme.accent
                        font.pixelSize: Theme.sizeSmall
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.tracking(Theme.sizeSmall)
                    }

                    Repeater {
                        model: modelData.rows || []

                        delegate: RowLayout {
                            required property var modelData

                            Layout.fillWidth: true
                            Layout.preferredHeight: 30
                            spacing: 10
                            visible: panel.rowVisible(modelData)

                            Rectangle {
                                Layout.preferredWidth: 4
                                Layout.preferredHeight: 14
                                Layout.alignment: Qt.AlignVCenter
                                radius: 2
                                color: modelData.has_value ? Theme.good : Theme.mute
                                opacity: modelData.has_value ? 0.85 : 0.35
                            }

                            Label {
                                Layout.preferredWidth: panel.labelWidth
                                Layout.maximumWidth: panel.labelMaxWidth
                                Layout.alignment: Qt.AlignVCenter
                                text: modelData.label || modelData.field || ""
                                color: Theme.dim
                                font.pixelSize: Theme.sizeSmall
                                elide: Text.ElideRight
                            }

                            MudaeCommandChip {
                                Layout.alignment: Qt.AlignVCenter
                                visible: panel.showCommandChip
                                         && (modelData.command || "").length > 0
                                command: modelData.command || ""
                            }

                            Image {
                                readonly property string iconUrl: panel.fieldIcon(modelData.field)
                                Layout.preferredWidth: 14
                                Layout.preferredHeight: 14
                                Layout.alignment: Qt.AlignVCenter
                                visible: iconUrl !== ""
                                source: iconUrl
                                sourceSize.width: 14
                                sourceSize.height: 14
                                fillMode: Image.PreserveAspectFit
                                smooth: true
                            }

                            Item { Layout.fillWidth: true; Layout.minimumWidth: 4 }

                            Label {
                                Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                Layout.maximumWidth: Math.max(
                                    120,
                                    displayScroll.availableWidth * panel.valueWidthFraction)
                                text: modelData.display || "—"
                                color: modelData.has_value ? Theme.fg : Theme.mute
                                font.pixelSize: Theme.sizeSmall
                                font.weight: Font.Medium
                                horizontalAlignment: Text.AlignRight
                                elide: Text.ElideLeft
                            }
                        }
                    }
                }
            }
        }
    }
}
