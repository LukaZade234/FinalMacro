import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Revenue-style kakera/sphere charts: daily line trend + monthly bars.
Item {
    id: root

    property var dailySeries: []
    property var monthlySeries: []
    property int rangeDays: 30
    property string emptyText: "No kakera earnings in this range."

    readonly property var visibleDaily: filteredDaily()
    readonly property var visibleMonthly: {
        var series = monthlySeries || []
        if (series.length <= 12)
            return series
        return series.slice(series.length - 12)
    }
    readonly property real dailyMax: {
        var maxVal = 1
        for (var i = 0; i < visibleDaily.length; i++)
            maxVal = Math.max(maxVal, Number(visibleDaily[i].amount) || 0)
        return maxVal
    }
    readonly property real monthlyMax: {
        var maxVal = 1
        for (var j = 0; j < visibleMonthly.length; j++)
            maxVal = Math.max(maxVal, Number(visibleMonthly[j].amount) || 0)
        return maxVal
    }

    function formatAmount(value) {
        var n = Number(value) || 0
        if (n >= 1000000)
            return (n / 1000000).toFixed(1) + "M"
        if (n >= 1000)
            return (n / 1000).toFixed(1) + "k"
        return String(n)
    }

    function filteredDaily() {
        if (!dailySeries || dailySeries.length === 0)
            return []
        if (rangeDays <= 0)
            return dailySeries
        var start = Math.max(0, dailySeries.length - rangeDays)
        return dailySeries.slice(start)
    }

    function colorStr(color) {
        return Qt.color(color).toString()
    }

    function repaintCharts() {
        lineCanvas.requestPaint()
        barCanvas.requestPaint()
    }

    onDailySeriesChanged: repaintCharts()
    onMonthlySeriesChanged: repaintCharts()
    onRangeDaysChanged: repaintCharts()
    onWidthChanged: if (width > 0) repaintCharts()

    Component.onCompleted: Qt.callLater(repaintCharts)

    implicitHeight: chartsColumn.implicitHeight
    implicitWidth: chartsColumn.implicitWidth

    ColumnLayout {
        id: chartsColumn
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 14

        Label {
            text: "Daily earnings"
            color: Theme.fgPrimary
            font.pixelSize: 12
            font.weight: Font.DemiBold
            Layout.fillWidth: true
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            radius: 8
            color: Theme.bgDark
            border.color: Theme.border
            border.width: 1

            Label {
                anchors.centerIn: parent
                visible: visibleDaily.length === 0
                text: root.emptyText
                color: Theme.fgMuted
                font.pixelSize: 12
            }

            Canvas {
                id: lineCanvas
                anchors.fill: parent
                anchors.margins: 10
                visible: visibleDaily.length > 0

                onWidthChanged: if (width > 0) requestPaint()
                onHeightChanged: if (height > 0) requestPaint()

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var series = root.visibleDaily
                    if (series.length === 0 || width <= 0 || height <= 0)
                        return

                    var padL = 42
                    var padR = 8
                    var padT = 10
                    var padB = 24
                    var plotW = width - padL - padR
                    var plotH = height - padT - padB
                    var maxVal = root.dailyMax

                    ctx.strokeStyle = colorStr(Theme.border)
                    ctx.lineWidth = 1
                    ctx.beginPath()
                    ctx.moveTo(padL, padT)
                    ctx.lineTo(padL, padT + plotH)
                    ctx.lineTo(padL + plotW, padT + plotH)
                    ctx.stroke()

                    ctx.fillStyle = colorStr(Theme.fgMuted)
                    ctx.font = "10px sans-serif"
                    ctx.textAlign = "right"
                    ctx.fillText(root.formatAmount(maxVal), padL - 4, padT + 8)
                    ctx.fillText("0", padL - 4, padT + plotH)

                    if (series.length === 1) {
                        var cx = padL + plotW / 2
                        var cy = padT + plotH - (series[0].amount / maxVal) * plotH
                        ctx.fillStyle = colorStr(Theme.accentPrimary)
                        ctx.beginPath()
                        ctx.arc(cx, cy, 4, 0, Math.PI * 2)
                        ctx.fill()
                    } else {
                        ctx.strokeStyle = colorStr(Theme.accentPrimary)
                        ctx.lineWidth = 2
                        ctx.beginPath()
                        for (var j = 0; j < series.length; j++) {
                            var x = padL + (plotW * j / (series.length - 1))
                            var y = padT + plotH - (series[j].amount / maxVal) * plotH
                            if (j === 0)
                                ctx.moveTo(x, y)
                            else
                                ctx.lineTo(x, y)
                        }
                        ctx.stroke()

                        ctx.fillStyle = colorStr(Theme.accentPrimary)
                        for (var k = 0; k < series.length; k++) {
                            var px = padL + (plotW * k / (series.length - 1))
                            var py = padT + plotH - (series[k].amount / maxVal) * plotH
                            ctx.beginPath()
                            ctx.arc(px, py, 3, 0, Math.PI * 2)
                            ctx.fill()
                        }
                    }

                    ctx.textAlign = "center"
                    ctx.fillStyle = colorStr(Theme.fgMuted)
                    ctx.fillText(series[0].date.slice(5), padL, padT + plotH + 16)
                    if (series.length > 1)
                        ctx.fillText(series[series.length - 1].date.slice(5), padL + plotW, padT + plotH + 16)
                }
            }
        }

        Label {
            text: "Monthly totals"
            color: Theme.fgPrimary
            font.pixelSize: 12
            font.weight: Font.DemiBold
            Layout.fillWidth: true
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            radius: 8
            color: Theme.bgDark
            border.color: Theme.border
            border.width: 1

            Label {
                anchors.centerIn: parent
                visible: visibleMonthly.length === 0
                text: "No monthly data yet."
                color: Theme.fgMuted
                font.pixelSize: 12
            }

            Canvas {
                id: barCanvas
                anchors.fill: parent
                anchors.margins: 10
                visible: visibleMonthly.length > 0

                onWidthChanged: if (width > 0) requestPaint()
                onHeightChanged: if (height > 0) requestPaint()

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var series = root.visibleMonthly
                    if (series.length === 0 || width <= 0 || height <= 0)
                        return

                    var padL = 8
                    var padR = 8
                    var padT = 8
                    var padB = 22
                    var plotW = width - padL - padR
                    var plotH = height - padT - padB
                    var maxVal = root.monthlyMax
                    var barGap = 6
                    var barW = Math.max(8, (plotW - barGap * (series.length - 1)) / series.length)

                    for (var j = 0; j < series.length; j++) {
                        var item = series[j]
                        var bx = padL + j * (barW + barGap)
                        var bh = (item.amount / maxVal) * plotH
                        var by = padT + plotH - bh
                        ctx.fillStyle = colorStr(j === series.length - 1
                                                 ? Theme.accentPrimary
                                                 : Theme.accentSecondary)
                        ctx.fillRect(bx, by, barW, bh)

                        ctx.fillStyle = colorStr(Theme.fgMuted)
                        ctx.font = "9px sans-serif"
                        ctx.textAlign = "center"
                        var label = item.label || item.month
                        if (label.length > 6)
                            label = label.slice(0, 3)
                        ctx.fillText(label, bx + barW / 2, padT + plotH + 14)
                    }
                }
            }
        }
    }
}
