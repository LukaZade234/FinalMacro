import QtQuick
import Qt5Compat.GraphicalEffects
import gui 1.0

// The app mark: a mudae sphere whose colour follows the active palette.
// ``sphereId`` defaults to Theme.markSphereId; settings cards pass another id
// so each swatch can show that palette's sphere.
Item {
    id: root

    property int size: 22
    property string sphereId: Theme.markSphereId
    // Kept so GemMark call sites that set ``color`` still load.
    property color color: "#ffffff"

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    readonly property bool _mask: GraphicsInfo.api !== GraphicsInfo.Software
    readonly property string _src: SphereAssets.iconUrl(sphereId)

    Image {
        id: raw
        anchors.fill: parent
        source: root._src
        sourceSize.width: root.size
        sourceSize.height: root.size
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        visible: !root._mask
    }

    Rectangle {
        id: circle
        width: root.size
        height: root.size
        radius: root.size / 2
        visible: false
        color: "#ffffff"
    }

    OpacityMask {
        visible: root._mask
        anchors.fill: parent
        source: raw
        maskSource: circle
        cached: true
    }
}
