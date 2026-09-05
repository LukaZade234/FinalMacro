import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    Expected keys per hour across every `$bw` from 0 to the roll pool's limit.

    Two curves, as `bwcalc` draws them: the whole wishlist against the left
    axis, and — when a character is selected — that one character against its
    own axis on the right. A single character's EV is roughly 65x below the
    wishlist total, so one shared scale would flatten it onto the baseline and
    hide the very thing the selection was made to look at. The axes are labelled
    and colour-matched to their curves so the two are not read as comparable
    heights; what is being compared is *where each peaks*.

    The `$bw` values worth pointing at are vertical guides rather than a legend
    entry: their whole meaning is where on this axis they sit. Their labels are
    stacked rather than placed side by side, because the peaks cluster within a
    few `$bw` of each other and the labels would otherwise overlap exactly where
    the chart is most interesting.
*/
Item {
    id: root

    property var points: []
    property int currentBw: -1
    property int bestTotalBw: -1
    property int bestStarwishBw: -1
    property int bestFocusBw: -1
    property string focusName: ""

    // Follows the mouse; -1 when the pointer is away.
    property int hoverBw: -1

    readonly property real maxKeys: {
        var top = 0
        for (var i = 0; i < points.length; i++)
            top = Math.max(top, Number(points[i].total_keys_per_hour || 0))
        return top
    }
    readonly property real maxFocusKeys: {
        var top = 0
        for (var i = 0; i < points.length; i++)
            top = Math.max(top, Number(points[i].focus_keys_per_hour || 0))
        return top
    }
    readonly property bool hasFocus: focusName !== "" && maxFocusKeys > 0
    readonly property int lastBw: points.length > 0 ? Number(points[points.length - 1].bw) : 0

    // Gridline spacing a person would choose, sized so the axis lands on four
    // to six lines. Rounding the maximum up to one big step instead (51.2 -> 100)
    // would leave the curve using half the panel.
    function niceStep(value) {
        if (value <= 0)
            return 1
        var magnitude = Math.pow(10, Math.floor(Math.log(value) / Math.LN10))
        var ladder = [1, 2, 2.5, 5, 10]
        for (var i = 0; i < ladder.length; i++) {
            var step = ladder[i] * magnitude
            if (Math.ceil(value / step) <= 6)
                return step
        }
        return 10 * magnitude
    }

    readonly property real axisStep: niceStep(maxKeys)
    readonly property real axisMax: Math.ceil(maxKeys / axisStep) * axisStep
    readonly property real focusAxisStep: niceStep(maxFocusKeys)
    readonly property real focusAxisMax: maxFocusKeys > 0
        ? Math.ceil(maxFocusKeys / focusAxisStep) * focusAxisStep : 1

    readonly property var hoverPoint: {
        if (hoverBw < 0)
            return null
        for (var i = 0; i < points.length; i++) {
            if (Number(points[i].bw) === hoverBw)
                return points[i]
        }
        return null
    }

    function pointAt(bw) {
        for (var i = 0; i < points.length; i++) {
            if (Number(points[i].bw) === bw)
                return points[i]
        }
        return null
    }

    onPointsChanged: canvas.requestPaint()
    onCurrentBwChanged: canvas.requestPaint()
    onBestTotalBwChanged: canvas.requestPaint()
    onBestStarwishBwChanged: canvas.requestPaint()
    onBestFocusBwChanged: canvas.requestPaint()
    onFocusNameChanged: canvas.requestPaint()
    onHoverBwChanged: canvas.requestPaint()

    // Canvas paints with literal colours, so a palette swap has to be redrawn.
    Connections {
        target: Theme
        function onPaletteIdChanged() { canvas.requestPaint() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 5

        // Reads out whatever the pointer is over, falling back to the peak so
        // the chart says something before anyone touches it.
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    text: {
                        var point = root.hoverPoint || root.pointAt(root.bestTotalBw)
                        return point ? "$bw " + point.bw : ""
                    }
                    color: Theme.fg
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    font.weight: Font.Medium
                }

                Label {
                    Layout.fillWidth: true
                    text: {
                        var point = root.hoverPoint || root.pointAt(root.bestTotalBw)
                        if (!point)
                            return ""
                        return point.net_rolls + " net rolls/hr  ·  "
                               + Number(point.wl_spawns_per_hour).toFixed(2) + " spawns/hr"
                    }
                    color: Theme.dim
                    font.pixelSize: Theme.sizeMicro
                    elide: Text.ElideRight
                }

                Label {
                    text: root.hoverPoint ? "" : "at the peak"
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Label {
                    text: {
                        var point = root.hoverPoint || root.pointAt(root.bestTotalBw)
                        return point
                               ? Number(point.total_keys_per_hour).toFixed(3) + " keys/hr"
                               : ""
                    }
                    color: Theme.accent
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.hasFocus
                    text: {
                        var point = root.hoverPoint || root.pointAt(root.bestFocusBw)
                        if (!point || point.focus_keys_per_hour === null)
                            return ""
                        return root.focusName + " "
                               + Number(point.focus_keys_per_hour).toFixed(3) + " keys/hr"
                    }
                    color: Theme.accent2
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    elide: Text.ElideRight
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Canvas {
                id: canvas
                anchors.fill: parent
                renderStrategy: Canvas.Cooperative

                readonly property int padLeft: 54
                // Room for the right-hand axis only when there is one to draw.
                readonly property int padRight: root.hasFocus ? 56 : 14
                readonly property int padTop: 10
                readonly property int padBottom: 32

                function plotX(bw) {
                    if (root.lastBw <= 0)
                        return padLeft
                    return padLeft + (bw / root.lastBw) * (width - padLeft - padRight)
                }

                function plotY(keys) {
                    var span = height - padTop - padBottom
                    if (root.axisMax <= 0)
                        return height - padBottom
                    return height - padBottom - (keys / root.axisMax) * span
                }

                // The right-hand axis: one selected character, whose EV is far
                // below the wishlist total and would otherwise sit flat on the
                // baseline.
                function plotFocusY(keys) {
                    var span = height - padTop - padBottom
                    if (root.focusAxisMax <= 0)
                        return height - padBottom
                    return height - padBottom - (keys / root.focusAxisMax) * span
                }

                function axisTitle(ctx, text, colour, x, rotation) {
                    ctx.save()
                    ctx.translate(x, (padTop + height - padBottom) / 2)
                    ctx.rotate(rotation)
                    ctx.fillStyle = colour
                    ctx.font = "9px sans-serif"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText(text, 0, 0)
                    ctx.restore()
                }

                function series(ctx, key, mapY, colour, fill) {
                    var pts = root.points
                    ctx.beginPath()
                    var started = false
                    for (var i = 0; i < pts.length; i++) {
                        var value = pts[i][key]
                        if (value === null || value === undefined)
                            continue
                        var px = plotX(pts[i].bw)
                        var py = mapY(value)
                        if (!started) { ctx.moveTo(px, py); started = true }
                        else ctx.lineTo(px, py)
                    }
                    if (!started)
                        return
                    if (fill) {
                        var bottom = height - padBottom
                        ctx.lineTo(plotX(pts[pts.length - 1].bw), bottom)
                        ctx.lineTo(plotX(pts[0].bw), bottom)
                        ctx.closePath()
                        ctx.globalAlpha = 0.10
                        ctx.fillStyle = colour
                        ctx.fill()
                        ctx.globalAlpha = 1
                        // Re-stroke the line itself; the fill path closed it.
                        series(ctx, key, mapY, colour, false)
                        return
                    }
                    ctx.strokeStyle = colour
                    ctx.lineWidth = 2
                    ctx.lineJoin = "round"
                    ctx.stroke()
                }

                function dot(ctx, bw, key, mapY, colour) {
                    var point = root.pointAt(bw)
                    if (!point || point[key] === null || point[key] === undefined)
                        return
                    ctx.beginPath()
                    ctx.arc(plotX(bw), mapY(point[key]), 3.5, 0, Math.PI * 2)
                    ctx.fillStyle = colour
                    ctx.fill()
                    ctx.strokeStyle = Theme.surface
                    ctx.lineWidth = 1.5
                    ctx.stroke()
                }

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var pts = root.points || []
                    if (pts.length < 2 || root.axisMax <= 0)
                        return

                    var plotBottom = height - padBottom
                    var plotRight = width - padRight

                    // Horizontal grid, one line per step of the chosen ladder.
                    ctx.font = "9px sans-serif"
                    ctx.lineWidth = 1
                    ctx.textAlign = "right"
                    ctx.textBaseline = "middle"
                    var places = root.axisStep < 1 ? 2 : root.axisStep < 10 ? 1 : 0
                    var lines = Math.round(root.axisMax / root.axisStep)
                    for (var step = 0; step <= lines; step++) {
                        var value = root.axisStep * step
                        var y = plotY(value)
                        ctx.strokeStyle = Theme.line
                        ctx.globalAlpha = 0.3
                        ctx.beginPath()
                        ctx.moveTo(padLeft, y)
                        ctx.lineTo(plotRight, y)
                        ctx.stroke()
                        ctx.globalAlpha = 1
                        ctx.fillStyle = Theme.mute
                        ctx.fillText(value.toFixed(places), padLeft - 7, y)
                    }

                    // x ticks every 10, labelled every 20 so a narrow chart does
                    // not crowd.
                    ctx.textAlign = "center"
                    ctx.textBaseline = "top"
                    for (var tick = 0; tick <= root.lastBw; tick += 10) {
                        var tx = plotX(tick)
                        ctx.strokeStyle = Theme.line
                        ctx.globalAlpha = 0.5
                        ctx.beginPath()
                        ctx.moveTo(tx, plotBottom)
                        ctx.lineTo(tx, plotBottom + (tick % 20 === 0 ? 4 : 2))
                        ctx.stroke()
                        ctx.globalAlpha = 1
                        if (tick % 20 === 0) {
                            ctx.fillStyle = Theme.mute
                            ctx.fillText(String(tick), tx, plotBottom + 6)
                        }
                    }

                    series(ctx, "total_keys_per_hour", plotY, Theme.accent, true)
                    if (root.hasFocus)
                        series(ctx, "focus_keys_per_hour", plotFocusY, Theme.accent2, false)

                    // Right-hand axis, on its own ladder — the two series differ
                    // by ~65x, so a shared one would flatten this curve.
                    if (root.hasFocus) {
                        ctx.fillStyle = Theme.accent2
                        ctx.textAlign = "left"
                        ctx.textBaseline = "middle"
                        var focusPlaces = root.focusAxisStep < 0.1 ? 3
                                        : root.focusAxisStep < 1 ? 2 : 1
                        var focusLines = Math.round(root.focusAxisMax / root.focusAxisStep)
                        for (var rs = 0; rs <= focusLines; rs++) {
                            var rv = root.focusAxisStep * rs
                            ctx.fillText(rv.toFixed(focusPlaces), plotRight + 7, plotFocusY(rv))
                        }
                    }

                    // Guides, labelled in a stack so clustered peaks stay legible.
                    var guides = []
                    if (root.bestTotalBw >= 0)
                        guides.push({ bw: root.bestTotalBw, colour: Theme.good,
                                      label: "wishlist " + root.bestTotalBw })
                    if (root.bestStarwishBw >= 0 && root.bestStarwishBw !== root.bestTotalBw)
                        guides.push({ bw: root.bestStarwishBw, colour: Theme.warn,
                                      label: "starwishes " + root.bestStarwishBw })
                    if (root.hasFocus && root.bestFocusBw >= 0
                            && root.bestFocusBw !== root.bestStarwishBw
                            && root.bestFocusBw !== root.bestTotalBw)
                        guides.push({ bw: root.bestFocusBw, colour: Theme.accent2,
                                      label: root.focusName + " " + root.bestFocusBw })
                    if (root.currentBw >= 0 && root.currentBw !== root.bestTotalBw)
                        guides.push({ bw: root.currentBw, colour: Theme.fg,
                                      label: "yours " + root.currentBw })

                    ctx.textBaseline = "middle"
                    for (var g = 0; g < guides.length; g++) {
                        var gx = plotX(guides[g].bw)
                        ctx.strokeStyle = guides[g].colour
                        ctx.globalAlpha = 0.75
                        ctx.lineWidth = 1
                        ctx.beginPath()
                        ctx.moveTo(gx, padTop)
                        ctx.lineTo(gx, plotBottom)
                        ctx.stroke()
                        ctx.globalAlpha = 1

                        // Stack labels down the top-left of the plot, away from
                        // the curve's own peak.
                        var ly = padTop + 7 + g * 12
                        var toRight = gx < (padLeft + plotRight) / 2
                        ctx.fillStyle = guides[g].colour
                        ctx.textAlign = toRight ? "left" : "right"
                        ctx.fillText(guides[g].label, gx + (toRight ? 4 : -4), ly)
                    }

                    if (root.hoverBw >= 0) {
                        var hx = plotX(root.hoverBw)
                        ctx.strokeStyle = Theme.mute
                        ctx.globalAlpha = 0.6
                        ctx.beginPath()
                        ctx.moveTo(hx, padTop)
                        ctx.lineTo(hx, plotBottom)
                        ctx.stroke()
                        ctx.globalAlpha = 1
                    }

                    // Peak markers, drawn last so nothing crosses them.
                    dot(ctx, root.bestTotalBw, "total_keys_per_hour", plotY, Theme.good)
                    if (root.hasFocus)
                        dot(ctx, root.bestFocusBw, "focus_keys_per_hour", plotFocusY,
                            Theme.accent2)
                    if (root.hoverBw >= 0) {
                        dot(ctx, root.hoverBw, "total_keys_per_hour", plotY, Theme.accent)
                        if (root.hasFocus)
                            dot(ctx, root.hoverBw, "focus_keys_per_hour", plotFocusY,
                                Theme.accent2)
                    }

                    axisTitle(ctx, "whole wishlist · keys/hr", Theme.accent, 11, -Math.PI / 2)
                    if (root.hasFocus)
                        axisTitle(ctx, root.focusName + " · keys/hr", Theme.accent2,
                                  width - 9, Math.PI / 2)

                    ctx.fillStyle = Theme.mute
                    ctx.textAlign = "center"
                    ctx.textBaseline = "bottom"
                    ctx.fillText("$bw invested   (" + root.lastBw + " = rolls run out)",
                                 (padLeft + plotRight) / 2, height - 1)
                }
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton

                onPositionChanged: function (mouse) {
                    if (root.lastBw <= 0 || root.points.length === 0) {
                        root.hoverBw = -1
                        return
                    }
                    var span = canvas.width - canvas.padLeft - canvas.padRight
                    if (span <= 0 || mouse.x < canvas.padLeft || mouse.x > canvas.width
                            - canvas.padRight) {
                        root.hoverBw = -1
                        return
                    }
                    var ratio = (mouse.x - canvas.padLeft) / span
                    root.hoverBw = Math.max(
                        0, Math.min(root.lastBw, Math.round(ratio * root.lastBw)))
                }

                onExited: root.hoverBw = -1
            }
        }
    }
}
