import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: mudaeRoot
    clip: true

    property var presetData: ({ presets: [], default_preset_id: "" })
    property var serverData: ({ servers: [] })
    property int selectedPresetIndex: 0
    property var editorData: ({ sections: [], preset_id: "", preset_name: "" })
    property var diffData: ({ items: [], command_count: 0 })
    property var enabledGroups: ({
        rolls: true, claims: true, snipe: true, content: true,
        kakera: true, spheres: true, ranking: true
    })
    property int copyServerIndex: 0
    property int copyChannelIndex: 0
    property int applyServerIndex: 0
    property int applyChannelIndex: 0

    function presets() { return presetData.presets || [] }
    function selectedPresetId() {
        var list = presets()
        if (selectedPresetIndex < 0 || selectedPresetIndex >= list.length)
            return ""
        return list[selectedPresetIndex].id
    }
    function selectedPreset() {
        var list = presets()
        if (selectedPresetIndex < 0 || selectedPresetIndex >= list.length)
            return null
        return list[selectedPresetIndex]
    }

    function refreshPresets() {
        try { presetData = JSON.parse(App.mudaeSettingsPresetsJson) }
        catch (e) { presetData = { presets: [], default_preset_id: "" } }
        if (selectedPresetIndex >= presets().length)
            selectedPresetIndex = Math.max(0, presets().length - 1)
        if (presetList.currentIndex !== selectedPresetIndex)
            presetList.currentIndex = selectedPresetIndex
        refreshEditor()
    }

    function refreshServers() {
        try { serverData = JSON.parse(App.serversJson) }
        catch (e) { serverData = { servers: [] } }
    }

    function serverAt(index) {
        var list = serverData.servers || []
        return index >= 0 && index < list.length ? list[index] : null
    }

    function channelsAt(serverIndex) {
        var s = serverAt(serverIndex)
        return s ? (s.channels || []) : []
    }

    function channelProfileIdAt(serverIndex, channelIndex) {
        var chs = channelsAt(serverIndex)
        if (channelIndex < 0 || channelIndex >= chs.length)
            return ""
        return chs[channelIndex].id
    }

    function applyChannelProfileId() {
        return channelProfileIdAt(applyServerIndex, applyChannelIndex)
    }

    function copyChannelProfileId() {
        return channelProfileIdAt(copyServerIndex, copyChannelIndex)
    }

    function refreshEditor() {
        var pid = selectedPresetId()
        if (!pid) {
            editorData = { sections: [], preset_id: "", preset_name: "" }
            return
        }
        try { editorData = JSON.parse(App.getMudaeSettingsPresetEditorJson(pid)) }
        catch (e) { editorData = { sections: [], preset_id: pid, preset_name: "" } }
        var p = selectedPreset()
        if (p)
            presetNameField.text = p.name
        refreshDiff()
    }

    function syncApplyGroups() {
        var active = []
        for (var key in enabledGroups) {
            if (enabledGroups[key])
                active.push(key)
        }
        App.setMudaeSettingsApplyGroups(JSON.stringify(active))
    }

    function refreshDiff() {
        syncApplyGroups()
        var pid = selectedPresetId()
        var chId = applyChannelProfileId()
        if (!pid || !chId) {
            diffData = { items: [], command_count: 0 }
            return
        }
        try { diffData = JSON.parse(App.diffMudaeSettingsPreset(chId, pid)) }
        catch (e) { diffData = { items: [], command_count: 0 } }
    }

    function onFieldChanged(field, value) {
        var pid = selectedPresetId()
        if (!pid)
            return
        App.updateMudaeSettingsPresetField(pid, field, JSON.stringify(value))
        refreshEditor()
    }

    Connections {
        target: App
        function onMudaeSettingsPresetsChanged() { mudaeRoot.refreshPresets() }
        function onServersChanged() { mudaeRoot.refreshServers(); mudaeRoot.refreshDiff() }
        function onSettingsApplyChanged() { }
    }

    Component.onCompleted: {
        refreshServers()
        refreshPresets()
    }

    ScrollablePage {
        anchors.fill: parent

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 640
            spacing: 12
            clip: true

        PanelCard {
            Layout.preferredWidth: 200
            Layout.maximumWidth: 220
            Layout.minimumWidth: 160
            Layout.minimumHeight: 520
            Layout.alignment: Qt.AlignTop
            title: "Presets"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                ThemedButton {
                    Layout.fillWidth: true
                    text: "New preset"
                    accent: true
                    onClicked: App.addMudaeSettingsPreset("New preset")
                }

                ListView {
                    id: presetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: mudaeRoot.presets().length
                    currentIndex: mudaeRoot.selectedPresetIndex
                    onCurrentIndexChanged: {
                        if (currentIndex >= 0)
                            mudaeRoot.selectedPresetIndex = currentIndex
                        mudaeRoot.refreshEditor()
                    }
                    delegate: ThemedListDelegate {
                        width: presetList.width
                        property var presetItem: {
                            var list = mudaeRoot.presets()
                            return index >= 0 && index < list.length ? list[index] : null
                        }
                        text: {
                            if (!presetItem)
                                return ""
                            var mark = presetItem.id === mudaeRoot.presetData.default_preset_id ? " ★" : ""
                            return presetItem.name + mark
                        }
                        highlighted: ListView.isCurrentItem
                        onClicked: presetList.currentIndex = index
                    }
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Duplicate"
                    enabled: selectedPresetId().length > 0
                    onClicked: {
                        var p = selectedPreset()
                        if (p)
                            App.duplicateMudaeSettingsPreset(p.id, p.name + " copy")
                    }
                }
                ThemedButton {
                    Layout.fillWidth: true
                    text: "Set as default ★"
                    enabled: selectedPresetId().length > 0
                    onClicked: App.setDefaultMudaeSettingsPreset(selectedPresetId())
                }
                ThemedButton {
                    Layout.fillWidth: true
                    text: "Remove"
                    danger: true
                    enabled: presets().length > 1 && selectedPresetId().length > 0
                    onClicked: App.removeMudaeSettingsPreset(selectedPresetId())
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.minimumWidth: 240
            Layout.minimumHeight: 520
            Layout.alignment: Qt.AlignTop
            title: editorData.preset_name || "Preset commands"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                ThemedTextField {
                    id: presetNameField
                    Layout.fillWidth: true
                    placeholderText: "Preset name"
                    onEditingFinished: {
                        var pid = selectedPresetId()
                        if (pid && text.trim())
                            App.renameMudaeSettingsPreset(pid, text.trim())
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: "Each row matches a $settings line. Edit values below to build your template."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Label {
                        Layout.fillWidth: true
                        text: "Import from channel"
                        color: Theme.fgSecondary
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        ThemedComboBox {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 80
                            model: (serverData.servers || []).map(function(s) { return s.name })
                            currentIndex: copyServerIndex
                            onActivated: copyServerIndex = currentIndex
                        }
                        ThemedComboBox {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 80
                            model: channelsAt(copyServerIndex).map(function(c) { return "#" + c.name })
                            currentIndex: copyChannelIndex
                            onActivated: copyChannelIndex = currentIndex
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        ThemedButton {
                            Layout.fillWidth: true
                            text: "Import $settings"
                            enabled: copyChannelProfileId().length > 0 && selectedPresetId().length > 0
                            onClicked: {
                                App.copyChannelSettingsToMudaePreset(copyChannelProfileId(), selectedPresetId())
                                refreshEditor()
                            }
                        }
                        ThemedButton {
                            Layout.fillWidth: true
                            text: "Save as new preset"
                            enabled: copyChannelProfileId().length > 0
                            onClicked: {
                                var chs = channelsAt(copyServerIndex)
                                var name = chs[copyChannelIndex] ? chs[copyChannelIndex].name : "Channel"
                                App.saveChannelSettingsAsPreset(copyChannelProfileId(), name)
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        ThemedComboBox {
                            id: copyPresetCombo
                            Layout.fillWidth: true
                            model: presets().filter(function(p) { return p.id !== selectedPresetId() })
                                    .map(function(p) { return p.name })
                            enabled: model.length > 0 && selectedPresetId().length > 0
                        }
                        ThemedButton {
                            Layout.preferredWidth: 110
                            text: "Copy preset"
                            enabled: copyPresetCombo.count > 0 && selectedPresetId().length > 0
                            onClicked: {
                                var others = presets().filter(function(p) { return p.id !== selectedPresetId() })
                                var src = others[copyPresetCombo.currentIndex]
                                if (src)
                                    App.copyMudaePresetToPreset(src.id, selectedPresetId())
                                refreshEditor()
                            }
                        }
                    }
                }

                ThemedScrollView {
                    id: editorScroll
                    Layout.fillWidth: true
                    Layout.preferredHeight: 360
                    Layout.minimumHeight: 200

                    ColumnLayout {
                        id: editorColumn
                        width: editorScroll.availableWidth
                        spacing: 8

                        Repeater {
                            model: editorData.sections || []
                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.title
                                    color: Theme.accentPrimary
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    Layout.topMargin: 6
                                    Layout.bottomMargin: 2
                                }

                                Repeater {
                                    model: modelData.rows || []
                                    delegate: MudaeSettingsCommandRow {
                                        Layout.fillWidth: true
                                        width: editorColumn.width
                                        rowData: modelData
                                        presetId: mudaeRoot.selectedPresetId()
                                        editable: modelData.editor !== "readonly"
                                        onFieldChanged: function(field, value) {
                                            mudaeRoot.onFieldChanged(field, value)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        PanelCard {
            Layout.preferredWidth: 260
            Layout.maximumWidth: 300
            Layout.minimumWidth: 220
            Layout.minimumHeight: 520
            Layout.alignment: Qt.AlignTop
            title: "Apply to server"
            titleSize: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "Target channel (must match Run target to apply while connected):"
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                ThemedComboBox {
                    Layout.fillWidth: true
                    model: (serverData.servers || []).map(function(s) { return s.name })
                    currentIndex: applyServerIndex
                    onActivated: {
                        applyServerIndex = currentIndex
                        refreshDiff()
                    }
                }
                ThemedComboBox {
                    Layout.fillWidth: true
                    model: channelsAt(applyServerIndex).map(function(c) { return "#" + c.name })
                    currentIndex: applyChannelIndex
                    onActivated: {
                        applyChannelIndex = currentIndex
                        refreshDiff()
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    Repeater {
                        model: ["rolls", "claims", "snipe", "content", "kakera", "spheres", "ranking"]
                        delegate: ThemedCheckBox {
                            text: modelData
                            checked: mudaeRoot.enabledGroups[modelData]
                            onCheckedChanged: {
                                var copy = Object.assign({}, mudaeRoot.enabledGroups)
                                copy[modelData] = checked
                                mudaeRoot.enabledGroups = copy
                                mudaeRoot.refreshDiff()
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: diffData.command_count > 0
                        ? (diffData.command_count + " command(s) pending")
                        : "No changes for selected groups"
                    color: Theme.fgSecondary
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                ThemedScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    ColumnLayout {
                        width: parent.width
                        spacing: 4
                        Repeater {
                            model: diffData.items || []
                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.field + ": " + JSON.stringify(modelData.current) + " → " + JSON.stringify(modelData.desired)
                                    font.pixelSize: 9
                                    color: modelData.command ? Theme.fgPrimary : Theme.fgMuted
                                    wrapMode: Text.WordWrap
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: !!modelData.command
                                    text: modelData.command
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: 9
                                    color: Theme.accentPrimary
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }

                ThemedScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                    Layout.minimumHeight: 80
                    TextArea {
                        width: parent.width
                        readOnly: true
                        wrapMode: TextArea.Wrap
                        font.family: "Consolas, monospace"
                        font.pixelSize: 9
                        color: Theme.fgSecondary
                        text: App.settingsApplyLogText
                        background: Rectangle { color: "transparent" }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    ThemedButton {
                        Layout.fillWidth: true
                        text: "Dry run"
                        enabled: App.connected && applyChannelProfileId().length > 0 && !App.settingsApplyRunning
                        onClicked: App.applyMudaeSettingsPreset(applyChannelProfileId(), selectedPresetId(), true)
                    }
                    ThemedButton {
                        Layout.fillWidth: true
                        text: App.settingsApplyRunning ? "Applying…" : "Apply"
                        accent: true
                        enabled: App.connected && applyChannelProfileId().length > 0
                                && !App.settingsApplyRunning && diffData.command_count > 0
                        onClicked: App.applyMudaeSettingsPreset(applyChannelProfileId(), selectedPresetId(), false)
                    }
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Refresh diff"
                    onClicked: refreshDiff()
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Setup wizard…"
                    enabled: applyChannelProfileId().length > 0
                    onClicked: setupWizard.open()
                }
            }
        }
    }
    }

    MudaeSettingsSetupWizard {
        id: setupWizard
        channelProfileId: applyChannelProfileId()
        presetId: selectedPresetId()
        onClosed: refreshDiff()
    }
}
