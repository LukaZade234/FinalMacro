import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

RowLayout {
    id: row
    property var rowData: ({})
    property string presetId: ""
    property bool editable: true

    signal fieldChanged(string field, var value)

    spacing: 10
    Layout.fillWidth: true
    Layout.preferredHeight: rowLayoutHeight
    Layout.minimumHeight: 34

    readonly property int rowLayoutHeight: {
        if (rowData.editor === "servlimroul")
            return 34
        if (rowData.editor === "snipe")
            return 34
        return 34
    }

    function optionIndex(options, value) {
        var opts = options || []
        for (var i = 0; i < opts.length; i++) {
            if (opts[i].value === value)
                return i
        }
        return 0
    }

    function emitValue(val) {
        if (!presetId || !rowData.field)
            return
        fieldChanged(rowData.field, val)
    }

    Label {
        Layout.preferredWidth: 118
        Layout.maximumWidth: 140
        Layout.alignment: Qt.AlignVCenter
        text: rowData.label || rowData.field || ""
        color: Theme.fgSecondary
        font.pixelSize: 11
        elide: Text.ElideRight
        ToolTip.visible: descMa.containsMouse && implicitWidth < contentWidth
        ToolTip.text: rowData.label || rowData.field || ""
        MouseArea {
            id: descMa
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
        }
    }

    MudaeCommandChip {
        Layout.alignment: Qt.AlignVCenter
        visible: (rowData.command || "").length > 0
        command: rowData.command
    }

    Item { Layout.fillWidth: true; Layout.minimumWidth: 4 }

    Loader {
        id: editorLoader
        Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
        sourceComponent: {
            if (!editable || rowData.editor === "readonly")
                return readOnlyValue
            if (rowData.editor === "bool")
                return boolEditor
            if (rowData.editor === "enum")
                return enumEditor
            if (rowData.editor === "snipe")
                return snipeEditor
            if (rowData.editor === "servlimroul")
                return servlimEditor
            if (rowData.editor === "text")
                return textEditor
            return numberEditor
        }
    }

    Component {
        id: readOnlyValue
        Label {
            text: rowData.display || "—"
            color: Theme.fgPrimary
            font.pixelSize: 11
            font.weight: Font.Medium
            horizontalAlignment: Text.AlignRight
        }
    }

    Component {
        id: boolEditor
        ThemedComboBox {
            implicitWidth: 108
            model: ["enabled", "disabled"]
            currentIndex: rowData.value === false ? 1 : 0
            onActivated: emitValue(currentIndex === 0)
        }
    }

    Component {
        id: enumEditor
        ThemedComboBox {
            implicitWidth: 180
            model: (rowData.options || []).map(function(o) { return o.label })
            currentIndex: row.optionIndex(rowData.options, rowData.value)
            onActivated: {
                var opts = rowData.options || []
                if (currentIndex >= 0 && currentIndex < opts.length)
                    emitValue(opts[currentIndex].value)
            }
        }
    }

    Component {
        id: numberEditor
        ThemedSpinBox {
            implicitWidth: 96
            from: rowData.min_value !== undefined && rowData.min_value !== null ? rowData.min_value : 0
            to: rowData.max_value !== undefined && rowData.max_value !== null ? rowData.max_value : 99999
            value: rowData.value !== undefined && rowData.value !== null ? rowData.value : from
            onValueModified: emitValue(value)
        }
    }

    Component {
        id: textEditor
        ThemedTextField {
            implicitWidth: 72
            text: rowData.value !== undefined && rowData.value !== null ? String(rowData.value) : ""
            onEditingFinished: emitValue(text)
        }
    }

    Component {
        id: snipeEditor
        RowLayout {
            spacing: 6
            ThemedComboBox {
                id: snipeMode
                implicitWidth: 168
                model: (rowData.options || []).map(function(o) { return o.label })
                currentIndex: row.optionIndex(
                    rowData.options,
                    rowData.value && rowData.value.mode !== undefined ? rowData.value.mode : 0
                )
                onActivated: {
                    var opts = rowData.options || []
                    var mode = opts[currentIndex] ? opts[currentIndex].value : 0
                    var sec = snipeSeconds.value
                    emitValue({ mode: mode, seconds: sec > 0 ? sec : null })
                }
            }
            Label {
                text: "s"
                color: Theme.fgMuted
                font.pixelSize: 10
            }
            ThemedSpinBox {
                id: snipeSeconds
                implicitWidth: 64
                from: 0
                to: 45
                value: rowData.value && rowData.value.seconds ? rowData.value.seconds : 0
                onValueModified: {
                    var opts = rowData.options || []
                    var mode = opts[snipeMode.currentIndex] ? opts[snipeMode.currentIndex].value : 0
                    emitValue({ mode: mode, seconds: value > 0 ? value : null })
                }
            }
        }
    }

    Component {
        id: servlimEditor
        RowLayout {
            spacing: 4
            Repeater {
                model: ["wa", "ha", "wg", "hg"]
                delegate: RowLayout {
                    spacing: 2
                    Label {
                        text: modelData
                        color: Theme.fgMuted
                        font.pixelSize: 9
                    }
                    ThemedSpinBox {
                        property string axis: modelData
                        implicitWidth: 78
                        from: 1
                        to: 99999
                        value: {
                            if (!rowData.value)
                                return 7000
                            return rowData.value[axis] || 7000
                        }
                        onValueModified: {
                            var next = rowData.value ? Object.assign({}, rowData.value) : {}
                            next[axis] = value
                            emitValue(next)
                        }
                    }
                }
            }
        }
    }
}
