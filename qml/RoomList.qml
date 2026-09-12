import QtQuick
import qs.Commons
import qs.Ui

Column {
  id: root
  spacing: Style.space(8)

  property var service: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property string openAreaId: ""
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property var rooms: service && service.rooms ? service.rooms : []
  readonly property var openRoom: {
    if (!openAreaId) return null
    for (var i = 0; i < rooms.length; i++)
      if (String(rooms[i].area_id) === String(openAreaId)) return rooms[i]
    return null
  }

  function goBack() { openAreaId = "" }

  Text {
    visible: rooms.length === 0
    width: parent.width
    text: "No rooms yet. Hearth is connected — wait a moment for the house to load."
    color: root.dim
    wrapMode: Text.WordWrap
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
  }

  Repeater {
    model: openRoom ? [] : rooms
    Button {
      required property var modelData
      width: root.width
      text: modelData.name + (modelData.count ? ("  ·  " + modelData.count) : "")
      foreground: root.foreground
      onClicked: root.openAreaId = modelData.area_id
    }
  }

  Column {
    visible: openRoom !== null
    width: parent.width
    spacing: Style.space(8)

    Text {
      visible: openRoom && openRoom.entities && openRoom.entities.length === 0
      width: parent.width
      text: "Nothing to control in this room."
      color: root.dim
      wrapMode: Text.WordWrap
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }

    Repeater {
      model: openRoom ? openRoom.entities : []
      EntityRow {
        required property var modelData
        width: root.width
        entity: modelData
        service: root.service
        foreground: root.foreground
        fontFamily: root.fontFamily
      }
    }
  }
}
