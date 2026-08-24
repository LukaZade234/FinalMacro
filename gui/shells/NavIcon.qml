import QtQuick
import QtQuick.Shapes

/*
    The 16x16 line icons used by the nav rails.

    Paths are SVG path data on a 0 0 16 16 canvas, matching the icons in the
    design mockups. `size` scales the whole shape, stroke included.
*/
Item {
    id: icon

    property string name: "run"
    property int size: 16
    property color color: "#ffffff"
    property real strokeWidth: 1.6

    implicitWidth: size
    implicitHeight: size

    readonly property var paths: ({
        "run": { d: "M5 3.5 L12.5 8 L5 12.5 Z", filled: true },
        "accounts": { d: "M10.5 5.5 A2.5 2.5 0 1 1 5.5 5.5 A2.5 2.5 0 1 1 10.5 5.5 M3 13.5 C3 11 5.2 9.5 8 9.5 C10.8 9.5 13 11 13 13.5", filled: false },
        "servers": { d: "M4.5 3 H11.5 A2 2 0 0 1 13.5 5 V11 A2 2 0 0 1 11.5 13 H4.5 A2 2 0 0 1 2.5 11 V5 A2 2 0 0 1 4.5 3 Z M2.5 6.5 H13.5", filled: false },
        "presets": { d: "M3 4.5 H13 M3 8 H13 M3 11.5 H9", filled: false },
        "statistics": { d: "M3 13 V8 M7 13 V3.5 M11 13 V9.5", filled: false },
        "debug": { d: "M5.5 7 H10.5 V10 A2.5 2.5 0 0 1 5.5 10 Z M6.4 7 A1.6 1.6 0 0 1 9.6 7 M2.5 8.5 H5.5 M10.5 8.5 H13.5 M3.5 12.5 L5.6 10.8 M12.5 12.5 L10.4 10.8", filled: false },
        "utilities": { d: "M3.5 4.5 H12.5 M3.5 8 H12.5 M3.5 11.5 H8.5 M10.5 10.2 L11.7 11.4 L14 9", filled: false },
        "settings": { d: "M2.5 5.5 H6 M9 5.5 H13.5 M2.5 10.5 H7 M10 10.5 H13.5 M9 5.5 A1.5 1.5 0 1 1 6 5.5 A1.5 1.5 0 1 1 9 5.5 M10 10.5 A1.5 1.5 0 1 1 7 10.5 A1.5 1.5 0 1 1 10 10.5", filled: false }
    })

    readonly property var spec: paths[name] !== undefined ? paths[name] : paths["run"]

    Shape {
        anchors.centerIn: parent
        width: 16
        height: 16
        preferredRendererType: Shape.CurveRenderer
        scale: icon.size / 16

        ShapePath {
            strokeColor: icon.color
            fillColor: icon.spec.filled ? icon.color : "transparent"
            strokeWidth: icon.strokeWidth
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin

            PathSvg { path: icon.spec.d }
        }
    }
}
