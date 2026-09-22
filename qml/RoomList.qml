import QtQuick
import qs.Commons
import qs.Ui
import "../js/Entities.js" as Entities

Column {
  id: root
  spacing: Style.space(8)

  property var service: null
  property var bar: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property string openAreaId: ""
  property string query: ""
  property int cursorIndex: 0
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property var rooms: {
    var all = service && service.rooms ? service.rooms : []
    var q = String(query || "").toLowerCase()
    if (!q) return all
    var out = []
    for (var i = 0; i < all.length; i++) {
      var r = all[i]
      var name = String(r.name || r.area_id || "").toLowerCase()
      if (name.indexOf(q) !== -1) { out.push(r); continue }
      var ents = r.entities || []
      for (var j = 0; j < ents.length; j++) {
        var en = String(ents[j].name || ents[j].entity_id || "").toLowerCase()
        if (en.indexOf(q) !== -1) { out.push(r); break }
      }
    }
    return out
  }
  readonly property var openRoom: {
    if (!openAreaId) return null
    for (var i = 0; i < rooms.length; i++)
      if (String(rooms[i].area_id) === String(openAreaId)) return rooms[i]
    return null
  }

  signal entityTouched(string entityId)

  function goBack() { openAreaId = ""; cursorIndex = 0 }

  function visibleEntities() {
    var ents = openRoom ? (openRoom.entities || []) : []
    var q = String(query || "").toLowerCase()
    if (!q) return ents
    var out = []
    for (var i = 0; i < ents.length; i++) {
      var en = String(ents[i].name || ents[i].entity_id || "").toLowerCase()
      if (en.indexOf(q) !== -1) out.push(ents[i])
    }
    return out
  }

  function moveCursor(dy) {
    var n = openRoom ? visibleEntities().length : rooms.length
    if (n <= 0) { cursorIndex = 0; return }
    var next = cursorIndex + dy
    if (next < 0) next = 0
    if (next >= n) next = n - 1
    cursorIndex = next
  }

  function activateCursor() {
    if (!openRoom) {
      if (rooms[cursorIndex]) openAreaId = rooms[cursorIndex].area_id
      cursorIndex = 0
      return
    }
    var ents = visibleEntities()
    var row = ents[cursorIndex]
    if (!row || !service || !service.actOnEntity) return
    entityTouched(row.entity_id || "")
    if (row.kind === "fan") {
      if (Entities.fanHasSpeeds(row.attrs)) {
        var cur = Entities.fanSpeedIndex(row.state, row.attrs)
        var max = Entities.fanSpeedCount(row.attrs)
        var next = cur >= max ? 0 : cur + 1
        var pct = Entities.fanPercentageForIndex(next, row.attrs)
        if (next <= 0 || pct <= 0) service.actOnEntity(row.entity_id, "turn_off")
        else service.actOnEntity(row.entity_id, "set_percentage", { percentage: pct })
      } else {
        service.actOnEntity(row.entity_id, "toggle")
      }
      return
    }
    service.actOnEntity(row.entity_id, row.service)
  }

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
      required property int index
      width: root.width
      text: modelData.name + (modelData.count ? ("  ·  " + modelData.count) : "")
      selected: !openRoom && root.cursorIndex === index
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
      model: {
        var ents = openRoom ? (openRoom.entities || []) : []
        var q = String(root.query || "").toLowerCase()
        if (!q) return ents
        var out = []
        for (var i = 0; i < ents.length; i++) {
          var en = String(ents[i].name || ents[i].entity_id || "").toLowerCase()
          if (en.indexOf(q) !== -1) out.push(ents[i])
        }
        return out
      }
      EntityRow {
        required property var modelData
        required property int index
        width: root.width
        entity: modelData
        service: root.service
        bar: root.bar
        foreground: root.foreground
        fontFamily: root.fontFamily
        opacity: openRoom && root.cursorIndex === index ? 1 : 0.92
        onTouched: {
          root.cursorIndex = index
          root.entityTouched(modelData.entity_id || "")
        }
      }
    }
  }
}
