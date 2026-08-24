import QtQuick
import QtQuick.Shapes

/*
    The faceted gem used as the app mark, matching the mockups'
    clip-path: polygon(50% 0, 100% 35%, 80% 100%, 20% 100%, 0 35%).
*/
Shape {
    id: gem

    property int size: 11
    property color color: "#ffffff"

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size
    preferredRendererType: Shape.CurveRenderer

    ShapePath {
        fillColor: gem.color
        strokeWidth: 0
        strokeColor: "transparent"

        PathSvg {
            path: "M " + (gem.size * 0.5) + " 0"
                + " L " + gem.size + " " + (gem.size * 0.35)
                + " L " + (gem.size * 0.8) + " " + gem.size
                + " L " + (gem.size * 0.2) + " " + gem.size
                + " L 0 " + (gem.size * 0.35) + " Z"
        }
    }
}
