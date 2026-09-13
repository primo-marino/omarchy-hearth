import QtQuick
import qs.Commons
import qs.Ui

Column {
  id: root
  spacing: Style.space(10)

  property var service: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property color dim: Qt.darker(foreground, 1.55)

  property string tokenText: ""
  property bool confirmRemove: false
  property bool allRooms: service && service.config && service.activeInstance() ? !!service.activeInstance().allRooms : false
  property var selectedAreaIds: service && service.activeInstance() && service.activeInstance().selectedAreaIds ? service.activeInstance().selectedAreaIds.slice() : []
  property string statusMessage: ""

  readonly property bool fieldFocused: tokenField.activeFocus

  function reloadFromService() {
    var inst = service && service.activeInstance ? service.activeInstance() : null
    allRooms = !!(inst && inst.allRooms)
    selectedAreaIds = inst && inst.selectedAreaIds ? inst.selectedAreaIds.slice() : []
    tokenText = ""
    confirmRemove = false
    statusMessage = ""
  }

  function areaSelected(areaId) {
    if (allRooms) return true
    for (var i = 0; i < selectedAreaIds.length; i++)
      if (String(selectedAreaIds[i]) === String(areaId)) return true
    return false
  }

  function toggleArea(areaId) {
    allRooms = false
    var next = []
    var found = false
    for (var i = 0; i < selectedAreaIds.length; i++) {
      if (String(selectedAreaIds[i]) === String(areaId)) {
        found = true
        continue
      }
      next.push(selectedAreaIds[i])
    }
    if (!found) next.push(areaId)
    selectedAreaIds = next
  }

  Text {
    width: parent.width
    text: "Settings"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.subtitle
    font.bold: true
  }

  Text {
    width: parent.width
    text: {
      var inst = service && service.activeInstance ? service.activeInstance() : null
      if (!inst) return "No instance."
      return inst.name + "\n" + inst.url
    }
    color: root.dim
    wrapMode: Text.WordWrap
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
  }

  Text {
    width: parent.width
    text: "Rooms"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Button {
    text: "All rooms"
    selected: root.allRooms
    foreground: root.foreground
    onClicked: {
      root.allRooms = !root.allRooms
      if (root.allRooms) {
        var ids = []
        var areas = service && service.allAreas ? service.allAreas : []
        for (var i = 0; i < areas.length; i++) ids.push(areas[i].area_id)
        root.selectedAreaIds = ids
      }
    }
  }

  Repeater {
    model: service && service.allAreas ? service.allAreas : []
    Toggle {
      required property var modelData
      width: root.width
      label: modelData.name || modelData.area_id
      checked: root.areaSelected(modelData.area_id)
      foreground: root.foreground
      fontFamily: root.fontFamily
      onClicked: root.toggleArea(modelData.area_id)
    }
  }

  Button {
    width: parent.width
    text: "Save rooms"
    foreground: root.foreground
    onClicked: {
      if (!service || !service.setSelection) return
      var result = service.setSelection({ allRooms: root.allRooms, selectedAreaIds: root.selectedAreaIds })
      root.statusMessage = result && result.ok ? "Rooms saved." : (result && result.error ? result.error : "Save failed.")
    }
  }

  Text {
    width: parent.width
    text: "Replace token"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  TextField {
    id: tokenField
    width: parent.width
    password: true
    placeholderText: "Long-lived access token"
    text: root.tokenText
    foreground: root.foreground
    onTextChanged: root.tokenText = text
  }

  Button {
    width: parent.width
    text: "Save token"
    enabled: root.tokenText.length > 0
    foreground: root.foreground
    onClicked: {
      if (!service || !service.replaceToken) return
      var result = service.replaceToken(root.tokenText)
      root.tokenText = ""
      tokenField.text = ""
      root.statusMessage = result && result.ok ? "Token sent. Wait for login." : (result && result.error ? result.error : "Replace failed.")
    }
  }

  Text {
    visible: root.statusMessage !== ""
    width: parent.width
    text: root.statusMessage
    color: root.dim
    wrapMode: Text.WordWrap
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  Button {
    width: parent.width
    text: "Add instance"
    foreground: root.foreground
    onClicked: {
      if (service && service.beginAddInstance) service.beginAddInstance()
    }
  }

  Button {
    width: parent.width
    text: root.confirmRemove ? "Confirm remove instance" : "Remove instance"
    foreground: root.foreground
    onClicked: {
      if (!root.confirmRemove) {
        root.confirmRemove = true
        return
      }
      if (service && service.removeActiveInstance) service.removeActiveInstance()
      root.confirmRemove = false
    }
  }
}
