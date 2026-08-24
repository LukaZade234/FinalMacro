import QtQuick
import QtQuick.Shapes

/*
    A rounded rectangle with a diagonal gradient.

    QML's built-in Rectangle gradient is axis-aligned only, and several of the
    designs use angled gradients (the app mark, the session haul card), so those
    are drawn as a shape instead.
*/
Shape {
    id: panel

    property real radius: 12
    property color colorFrom: "#000000"
    property color colorTo: "#000000"
    // Fraction of the diagonal at which colorTo is fully reached.
    property real stopTo: 1.0
    property color borderColor: "transparent"
    property real borderWidth: 0

    preferredRendererType: Shape.CurveRenderer

    ShapePath {
        strokeColor: panel.borderColor
        strokeWidth: panel.borderWidth

        fillGradient: LinearGradient {
            x1: 0
            y1: 0
            x2: panel.width
            y2: panel.height

            GradientStop { position: 0.0; color: panel.colorFrom }
            GradientStop { position: Math.min(1, Math.max(0.01, panel.stopTo)); color: panel.colorTo }
            GradientStop { position: 1.0; color: panel.colorTo }
        }

        PathSvg {
            path: {
                var w = Math.max(panel.width, 1)
                var h = Math.max(panel.height, 1)
                var r = Math.min(panel.radius, w / 2, h / 2)
                return "M " + r + " 0"
                    + " H " + (w - r) + " A " + r + " " + r + " 0 0 1 " + w + " " + r
                    + " V " + (h - r) + " A " + r + " " + r + " 0 0 1 " + (w - r) + " " + h
                    + " H " + r + " A " + r + " " + r + " 0 0 1 0 " + (h - r)
                    + " V " + r + " A " + r + " " + r + " 0 0 1 " + r + " 0 Z"
            }
        }
    }
}
