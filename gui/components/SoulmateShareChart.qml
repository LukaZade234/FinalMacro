import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Donut on the left, stacked bar + scrollable legend rows on the right.
Item {
    id: root

    property var chartData: ({ total: 0, items: [] })
    property string emptyText: "No data to chart."
    property bool selectable: false
    property string selectedId: ""
    property int legendScrollMax: 180

    signal sliceClicked(string id, string label)

    readonly property var palette: [
        Theme.accentPrimary,
        Theme.accentSecondary,
        Theme.success,
        Theme.warning,
        Theme.error,
        "#2ac3de",
        "#ff9e64",
        "#b4f9f8",
        "#cba6f7"
    ]

    readonly property int rowCount: (chartData.items || []).length
    readonly property int legendHeight: rowCount === 0
            ? 0
            : Math.min(legendScrollMax, rowCount * 34)
    readonly property int bodyHeight: chartData.total > 0
            ? Math.max(120, 24 + 10 + legendHeight)
            : 40

    function colorAt(index) {
        return palette[index % palette.length]
    }

    onChartDataChanged: pieCanvas.requestPaint()

    implicitHeight: bodyHeight
    implicitWidth: mainRow.implicitWidth

    RowLayout {
        id: mainRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: root.bodyHeight
        spacing: 14

        Item {
            id: donutBox
            Layout.preferredWidth: 120
            Layout.preferredHeight: 120
            Layout.minimumWidth: 120
            Layout.maximumWidth: 120
            Layout.maximumHeight: 120
            Layout.alignment: Qt.AlignTop
            visible: chartData.total > 0

            Canvas {
                id: pieCanvas
                anchors.fill: parent

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var items = chartData.items || []
                    var total = chartData.total || 0
                    if (total <= 0)
                        return

                    var cx = width / 2
                    var cy = height / 2
                    var outerR = Math.min(width, height) / 2 - 4
                    var innerR = outerR * 0.55
                    var start = -Math.PI / 2

                    for (var i = 0; i < items.length; i++) {
                        var slice = items[i].count / total
                        var sweep = slice * Math.PI * 2
                        var end = start + sweep
                        ctx.beginPath()
                        ctx.arc(cx, cy, outerR, start, end)
                        ctx.arc(cx, cy, innerR, end, start, true)
                        ctx.closePath()
                        ctx.fillStyle = root.colorAt(i)
                        ctx.fill()
                        start = end
                    }

                    ctx.beginPath()
                    ctx.arc(cx, cy, innerR, 0, Math.PI * 2)
                    ctx.fillStyle = Theme.bgMedium
                    ctx.fill()

                    ctx.fillStyle = Theme.fgPrimary
                    ctx.font = "bold 16px sans-serif"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText(String(total), cx, cy - 5)
                    ctx.fillStyle = Theme.fgMuted
                    ctx.font = "9px sans-serif"
                    ctx.fillText("total", cx, cy + 10)
                }
            }
        }

        Column {
            id: legendColumn
            Layout.fillWidth: true
            Layout.preferredHeight: root.bodyHeight
            spacing: 10

            Rectangle {
                width: parent.width
                height: 24
                radius: 8
                color: Theme.bgDark
                border.color: Theme.border
                border.width: 1
                visible: chartData.total > 0

                Row {
                    anchors.fill: parent
                    anchors.margins: 3
                    spacing: 2

                    Repeater {
                        model: chartData.items || []

                        delegate: Rectangle {
                            required property var modelData
                            required property int index

                            height: parent.height
                            width: {
                                var total = chartData.total || 0
                                if (total <= 0)
                                    return 0
                                return Math.max(2, (parent.width - (chartData.items.length - 1) * 2)
                                                 * (modelData.count / total))
                            }
                            radius: 4
                            color: root.colorAt(index)
                            ToolTip.visible: barMouse.containsMouse
                            ToolTip.text: modelData.label + ": "
                                          + modelData.count + " ("
                                          + modelData.percent.toFixed(1) + "%)"

                            MouseArea {
                                id: barMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: root.selectable
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: root.sliceClicked(modelData.id, modelData.label)
                            }
                        }
                    }
                }
            }

            Label {
                width: parent.width
                visible: chartData.total <= 0
                text: emptyText
                color: Theme.fgMuted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            ScrollView {
                width: parent.width
                height: root.legendHeight
                visible: root.rowCount > 0
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    width: parent.width
                    spacing: 2

                    Repeater {
                        model: chartData.items || []

                        delegate: Rectangle {
                            required property var modelData
                            required property int index

                            width: legendColumn.width
                            height: 32
                            radius: 6
                            color: root.selectedId === modelData.id ? Theme.bgLight : "transparent"
                            border.color: root.selectedId === modelData.id ? Theme.accentPrimary : "transparent"
                            border.width: root.selectedId === modelData.id ? 1 : 0

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: 6
                                spacing: 8

                                Rectangle {
                                    Layout.preferredWidth: 10
                                    Layout.preferredHeight: 10
                                    radius: 3
                                    color: root.colorAt(index)
                                }

                                Label {
                                    Layout.preferredWidth: 120
                                    text: modelData.label
                                    color: Theme.fgPrimary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 8
                                    radius: 4
                                    color: Theme.bgDark

                                    Rectangle {
                                        height: parent.height
                                        width: parent.width * Math.min(1, modelData.percent / 100)
                                        radius: 4
                                        color: root.colorAt(index)
                                        opacity: 0.85
                                    }
                                }

                                Label {
                                    Layout.preferredWidth: 32
                                    text: String(modelData.count)
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    horizontalAlignment: Text.AlignRight
                                }

                                Label {
                                    Layout.preferredWidth: 48
                                    text: modelData.percent.toFixed(1) + "%"
                                    color: Theme.fgMuted
                                    font.pixelSize: 11
                                    horizontalAlignment: Text.AlignRight
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: root.selectable
                                hoverEnabled: enabled
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: root.sliceClicked(modelData.id, modelData.label)
                            }
                        }
                    }
                }
            }
        }
    }
}
