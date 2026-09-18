import QtQuick
import QtQuick.Shapes
import qs.Commons

Item {
  id: root
  property real iconSize: Style.font.icon
  property color color: Color.foreground
  property bool lit: true

  width: iconSize
  height: iconSize
  implicitWidth: iconSize
  implicitHeight: iconSize

  readonly property real stroke: Math.max(1.15, iconSize * 0.09)

  Shape {
    anchors.fill: parent
    antialiasing: true
    preferredRendererType: Shape.GeometryRenderer

    ShapePath {
      fillColor: "transparent"
      strokeColor: root.color
      strokeWidth: root.stroke
      capStyle: ShapePath.RoundCap
      joinStyle: ShapePath.RoundJoin
      startX: root.iconSize * 0.10
      startY: root.iconSize * 0.50
      PathLine { x: root.iconSize * 0.50; y: root.iconSize * 0.12 }
      PathLine { x: root.iconSize * 0.90; y: root.iconSize * 0.50 }
    }

    ShapePath {
      fillColor: "transparent"
      strokeColor: root.color
      strokeWidth: root.stroke
      capStyle: ShapePath.RoundCap
      joinStyle: ShapePath.RoundJoin
      startX: root.iconSize * 0.22
      startY: root.iconSize * 0.48
      PathLine { x: root.iconSize * 0.22; y: root.iconSize * 0.90 }
      PathLine { x: root.iconSize * 0.78; y: root.iconSize * 0.90 }
      PathLine { x: root.iconSize * 0.78; y: root.iconSize * 0.48 }
    }
  }

  Rectangle {
    x: root.iconSize * 0.40
    y: root.iconSize * 0.58
    width: root.iconSize * 0.20
    height: root.iconSize * 0.32
    radius: Math.max(0.5, width * 0.12)
    color: root.lit ? root.color : "transparent"
    border.color: root.color
    border.width: root.lit ? 0 : Math.max(1, root.stroke * 0.85)
    opacity: root.lit ? 1 : 0.42
  }
}
