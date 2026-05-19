import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: presetsRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var presetData: ({ presets: [] })
    property int selectedIndex: 0
    property string editingPresetId: ""

    function reload() {
        try {
            presetData = JSON.parse(App.presetsJson)
        } catch (e) {
            presetData = { presets: [], active_preset_id: "" }
        }
        if (selectedIndex >= (presetData.presets || []).length)
            selectedIndex = Math.max(0, (presetData.presets || []).length - 1)
        if (presetList)
            presetList.currentIndex = selectedIndex
        var p = currentPreset()
        editingPresetId = p ? p.id : ""
        macroForm.presetId = editingPresetId
        macroForm.reloadFromApp()
    }

    function presets() {
        return presetData.presets || []
    }

    function currentPreset() {
        var list = presets()
        if (selectedIndex < 0 || selectedIndex >= list.length)
            return null
        return list[selectedIndex]
    }

    Connections {
        target: App
        function onConfigChanged() {
            presetsRoot.reload()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PanelCard {
            Layout.preferredWidth: 200
            Layout.maximumWidth: 240
            Layout.fillHeight: true
            title: "Presets"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: newPresetField
                        Layout.fillWidth: true
                        placeholderText: "Preset name"
                        color: Theme.fgPrimary
                        background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                    }
                    Button {
                        text: "Add"
                        enabled: newPresetField.text.trim().length > 0
                        onClicked: {
                            App.addPreset(newPresetField.text.trim())
                            newPresetField.text = ""
                            reload()
                            presetList.currentIndex = presets().length - 1
                            selectedIndex = presetList.currentIndex
                        }
                    }
                }

                ListView {
                    id: presetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: presets().length
                    currentIndex: selectedIndex
                    onCurrentIndexChanged: {
                        selectedIndex = currentIndex
                        var p = currentPreset()
                        editingPresetId = p ? p.id : ""
                        macroForm.presetId = editingPresetId
                        macroForm.reloadFromApp()
                    }
                    delegate: ItemDelegate {
                        width: presetList.width
                        text: presets()[index].id
                        highlighted: presetList.currentIndex === index
                        onClicked: presetList.currentIndex = index
                    }
                }

                Button {
                    Layout.fillWidth: true
                    text: "Duplicate"
                    enabled: currentPreset() !== null
                    onClicked: {
                        var p = currentPreset()
                        if (!p)
                            return
                        App.duplicatePreset(p.id, p.id + "_copy")
                        reload()
                    }
                }

                Button {
                    Layout.fillWidth: true
                    text: "Remove"
                    enabled: presets().length > 1 && currentPreset() !== null
                    onClicked: {
                        var p = currentPreset()
                        if (!p)
                            return
                        App.removePreset(p.id)
                        reload()
                    }
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: editingPresetId ? ("Preset: " + editingPresetId) : "Preset settings"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                MacroConfigForm {
                    id: macroForm
                    presetId: editingPresetId
                    Layout.fillWidth: true
                }

                RowLayout {
                    Button {
                        text: "Use on Run"
                        enabled: editingPresetId.length > 0
                        onClicked: App.setActivePreset(editingPresetId)
                    }
                }
            }
        }
    }

    Component.onCompleted: reload()
}
