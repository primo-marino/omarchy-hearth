import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root
  property var entity: ({})
  property var service: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string kind: entity && entity.kind ? String(entity.kind) : ""
  implicitHeight: row.implicitHeight
  width: parent ? parent.width : 0

  function run(svcName) {
    if (root.service && root.service.actOnEntity)
      root.service.actOnEntity(root.entity.entity_id, svcName || root.entity.service)
  }

  Toggle {
    id: row
    visible: kind === "toggle"
    width: parent.width
    label: entity.name || entity.entity_id || ""
    description: entity.state || ""
    checked: entity.state === "on"
    foreground: root.foreground
    fontFamily: root.fontFamily
    onClicked: root.run("toggle")
  }

  Row {
    visible: kind !== "toggle"
    width: parent.width
    spacing: Style.space(10)

    Column {
      width: parent.width - action.implicitWidth - parent.spacing
      spacing: Style.space(2)
      Text {
        width: parent.width
        text: entity.name || entity.entity_id || ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
        elide: Text.ElideRight
      }
      Text {
        width: parent.width
        text: entity.state || ""
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }
    }

    Button {
      id: action
      visible: kind === "activate" || kind === "media"
      text: kind === "media" ? "Play/Pause" : "Run"
      foreground: root.foreground
      onClicked: root.run()
    }
  }
}
