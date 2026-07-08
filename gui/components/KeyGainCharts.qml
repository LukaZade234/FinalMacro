import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Key gain charts: stacked daily/monthly bars + omega-only line trend.
Item {
    id: root

    property var dailySeries: []
    property var monthlySeries: []
    property var omegaDailySeries: []
    property int rangeDays: 30
    property string emptyText: "No key gains in this range."

    readonly property var keyColors: ({
        bronze: "#cd7f32",
        silver: "#a9b1d6",
        gold: "#e0af68",
        chaos: "#bb9af7",
        omega: "#7aa2f7"
    })
    readonly property var keyOrder: ["bronze", "silver", "gold", "chaos", "omega"]

    readonly property var visibleDaily: filteredDaily()
    readonly property var visibleMonthly: {
        var series = monthlySeries || []
        if (series.length <= 12)
            return series
        return series.slice(series.length - 12)
    }
    readonly property var visibleOmegaDaily: filteredOmegaDaily()

    function filteredDaily() {
        if (!dailySeries || dailySeries.length === 0)
            return []
        if (rangeDays <= 0)
            return dailySeries
        var start = Math.max(0, dailySeries.length - rangeDays)
        return dailySeries.slice(start)
    }

    function filteredOmegaDaily() {
        if (!omegaDailySeries || omegaDailySeries.length === 0)
            return []
        if (rangeDays <= 0)
            return omegaDailySeries
        var start = Math.max(0, omegaDailySeries.length - rangeDays)
        return omegaDailySeries.slice(start)
    }

    function dailyMax() {
        var maxVal = 1
        for (var i = 0; i < visibleDaily.length; i++) {
            var row = visibleDaily[i]
            var total = 0
            for (var j = 0; j < keyOrder.length; j++)
                total += Number(row[keyOrder[j]] || 0)
            maxVal = Math.max(maxVal, total)
        }
        return maxVal
    }

    function monthlyMax() {
        var maxVal = 1
        for (var i = 0; i < visibleMonthly.length; i++) {
            var row = visibleMonthly[i]
            var total = 0
            for (var j = 0; j < keyOrder.length; j++)
                total += Number(row[keyOrder[j]] || 0)
            maxVal = Math.max(maxVal, total)
        }
        return maxVal
    }

    function omegaMax() {
        var maxVal = 1
        for (var i = 0; i < visibleOmegaDaily.length; i++)
            maxVal = Math.max(maxVal, Number(visibleOmegaDaily[i].amount) || 0)
        return maxVal
    }

    function colorStr(color) {
        return Qt.color(color).toString()
    }

    function repaintCharts() {
        dailyCanvas.requestPaint()
        monthlyCanvas.requestPaint()
        omegaCanvas.requestPaint()
    }

    onDailySeriesChanged: repaintCharts()
    onMonthlySeriesChanged: repaintCharts()
    onOmegaDailySeriesChanged: repaintCharts()
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
            text: "Daily key gains (stacked)"
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
                id: dailyCanvas
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

                    var padL = 8
                    var padR = 8
                    var padT = 8
                    var padB = 22
                    var plotW = width - padL - padR
                    var plotH = height - padT - padB
                    var maxVal = root.dailyMax()
                    var barGap = 4
                    var barW = Math.max(6, (plotW - barGap * (series.length - 1)) / series.length)

                    for (var i = 0; i < series.length; i++) {
                        var row = series[i]
                        var bx = padL + i * (barW + barGap)
                        var yBottom = padT + plotH
                        var stacked = 0
                        for (var k = 0; k < root.keyOrder.length; k++) {
                            var keyId = root.keyOrder[k]
                            var amount = Number(row[keyId] || 0)
                            if (amount <= 0)
                                continue
                            var bh = (amount / maxVal) * plotH
                            var by = yBottom - stacked - bh
                            ctx.fillStyle = colorStr(root.keyColors[keyId] || Theme.accentPrimary)
                            ctx.fillRect(bx, by, barW, bh)
                            stacked += bh
                        }
                        ctx.fillStyle = colorStr(Theme.fgMuted)
                        ctx.font = "9px sans-serif"
                        ctx.textAlign = "center"
                        ctx.fillText(row.date.slice(5), bx + barW / 2, padT + plotH + 14)
                    }
                }
            }
        }

        Label {
            text: "Monthly totals (stacked)"
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
                id: monthlyCanvas
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
                    var maxVal = root.monthlyMax()
                    var barGap = 6
                    var barW = Math.max(8, (plotW - barGap * (series.length - 1)) / series.length)

                    for (var i = 0; i < series.length; i++) {
                        var row = series[i]
                        var bx = padL + i * (barW + barGap)
                        var yBottom = padT + plotH
                        var stacked = 0
                        for (var k = 0; k < root.keyOrder.length; k++) {
                            var keyId = root.keyOrder[k]
                            var amount = Number(row[keyId] || 0)
                            if (amount <= 0)
                                continue
                            var bh = (amount / maxVal) * plotH
                            var by = yBottom - stacked - bh
                            ctx.fillStyle = colorStr(root.keyColors[keyId] || Theme.accentPrimary)
                            ctx.fillRect(bx, by, barW, bh)
                            stacked += bh
                        }
                        ctx.fillStyle = colorStr(Theme.fgMuted)
                        ctx.font = "9px sans-serif"
                        ctx.textAlign = "center"
                        var label = row.label || row.month
                        if (label.length > 6)
                            label = label.slice(0, 3)
                        ctx.fillText(label, bx + barW / 2, padT + plotH + 14)
                    }
                }
            }
        }

        Label {
            text: "Omega keys (daily)"
            color: Theme.fgPrimary
            font.pixelSize: 12
            font.weight: Font.DemiBold
            Layout.fillWidth: true
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 100
            radius: 8
            color: Theme.bgDark
            border.color: Theme.border
            border.width: 1

            Label {
                anchors.centerIn: parent
                visible: visibleOmegaDaily.length === 0
                text: "No omega keys logged yet."
                color: Theme.fgMuted
                font.pixelSize: 12
            }

            Canvas {
                id: omegaCanvas
                anchors.fill: parent
                anchors.margins: 10
                visible: visibleOmegaDaily.length > 0

                onWidthChanged: if (width > 0) requestPaint()
                onHeightChanged: if (height > 0) requestPaint()

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var series = root.visibleOmegaDaily
                    if (series.length === 0 || width <= 0 || height <= 0)
                        return

                    var padL = 42
                    var padR = 8
                    var padT = 10
                    var padB = 24
                    var plotW = width - padL - padR
                    var plotH = height - padT - padB
                    var maxVal = root.omegaMax()

                    ctx.strokeStyle = colorStr(Theme.border)
                    ctx.lineWidth = 1
                    ctx.beginPath()
                    ctx.moveTo(padL, padT)
                    ctx.lineTo(padL, padT + plotH)
                    ctx.lineTo(padL + plotW, padT + plotH)
                    ctx.stroke()

                    if (series.length === 1) {
                        var cx = padL + plotW / 2
                        var cy = padT + plotH - (series[0].amount / maxVal) * plotH
                        ctx.fillStyle = colorStr(root.keyColors.omega)
                        ctx.beginPath()
                        ctx.arc(cx, cy, 4, 0, Math.PI * 2)
                        ctx.fill()
                    } else {
                        ctx.strokeStyle = colorStr(root.keyColors.omega)
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
                    }
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: root.keyOrder

                delegate: Row {
                    required property string modelData
                    spacing: 4

                    Rectangle {
                        width: 10
                        height: 10
                        radius: 2
                        anchors.verticalCenter: parent.verticalCenter
                        color: root.keyColors[modelData] || Theme.accentPrimary
                    }
                    Label {
                        text: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                        color: Theme.fgMuted
                        font.pixelSize: 10
                    }
                }
            }
        }
    }
}
