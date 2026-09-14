import QtQuick
import qs.Commons
import qs.Ui
import "qml"

Panel {
  id: root
  moduleName: "hearth"
  ipcTarget: ""
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var service: null
  property bool openedFromHotkey: false
  property bool cursorActive: false
  property string tab: "rooms"
  property string focusedEntityId: ""
  property bool filterOpen: false
  property string filterQuery: ""

  readonly property var barIdentity: hostWidget || root
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool configured: service ? service.configured === true : false
  readonly property bool addingInstance: service ? service.addingInstance === true : false
  readonly property bool showOnboard: !configured || addingInstance
  readonly property bool showSettings: service ? service.showSettings === true : false
  readonly property string connectionState: service ? String(service.connectionState || "idle") : "idle"
  readonly property string heroMeta: {
    if (connectionState === "reconnecting") return "Reconnecting…"
    if (service && service.lastError && connectionState !== "connected") return String(service.lastError)
    if (connectionState === "connected") return (service && service.locationName) ? String(service.locationName) : "Online"
    return connectionState
  }
  readonly property var instanceOptions: {
    var list = []
    var insts = service && service.config && service.config.instances ? service.config.instances : []
    for (var i = 0; i < insts.length; i++) {
      if (!insts[i] || !insts[i].id) continue
      list.push({ value: String(insts[i].id), label: insts[i].name ? String(insts[i].name) : String(insts[i].id) })
    }
    return list
  }
  readonly property var tabEntities: {
    if (!service) return []
    if (tab === "favorites") return service.favoriteEntities || []
    if (tab === "recents") return service.recentEntities || []
    return []
  }

  function open() {
    openedFromHotkey = false
    setCenterHoverRevealSuppressed(false)
    root.controller.show()
    root.refresh()
  }

  function openFromHotkey() {
    openedFromHotkey = true
    root.controller.show()
    root.refresh()
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    if (!configured && onboardLoader.item && onboardLoader.item.cancel) onboardLoader.item.cancel()
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.openFromHotkey()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(value)
    else if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function refresh() {
    if (service && service.refresh) service.refresh()
    if (service && service.refreshEnergy) service.refreshEnergy(true)
  }

  function currentEntities() {
    if (root.tab === "favorites") return service ? service.favoriteEntities : []
    if (root.tab === "recents") return service ? service.recentEntities : []
    if (roomList.openRoom && roomList.openRoom.entities) return roomList.openRoom.entities
    return []
  }

  function toggleFocusedFavorite() {
    var eid = root.focusedEntityId
    if (!eid) {
      var list = root.currentEntities() || []
      if (list.length > 0) eid = list[0].entity_id
    }
    if (eid && service && service.toggleFavorite) service.toggleFavorite(eid)
  }

  function handleClose() {
    if (root.filterOpen) {
      root.filterOpen = false
      root.filterQuery = ""
      return
    }
    if (root.addingInstance && service && service.cancelOnboard) {
      service.cancelOnboard()
      return
    }
    if (service && service.showSettings) {
      service.showSettings = false
      return
    }
    if (roomList.openAreaId) {
      roomList.goBack()
      return
    }
    root.close()
  }

  onServiceChanged: {
    if (onboardLoader.item) onboardLoader.item.service = service
    if (roomList.service !== service) roomList.service = service
    if (settingsPage.service !== service) settingsPage.service = service
  }

  onOpenedChanged: {
    if (opened) {
      refresh()
      if (keyCatcher) keyCatcher.forceActiveFocus()
      cursorActive = false
      if (service && service.pendingOpenAreaId) {
        root.tab = "rooms"
        roomList.openAreaId = String(service.pendingOpenAreaId)
        service.pendingOpenAreaId = ""
      }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: {
        if (onboardLoader.item && onboardLoader.item.fieldFocused === true) return true
        if (settingsPage.visible && settingsPage.fieldFocused === true) return true
        if (filterField.visible && filterField.activeFocus) return true
        return false
      }
      onCloseRequested: root.handleClose()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (root.tab === "rooms" && roomList.moveCursor) roomList.moveCursor(dy)
        else {
          var n = root.tabEntities.length
          if (n <= 0) return
          var idx = 0
          for (var i = 0; i < n; i++) if (root.tabEntities[i].entity_id === root.focusedEntityId) idx = i
          idx += dy
          if (idx < 0) idx = 0
          if (idx >= n) idx = n - 1
          root.focusedEntityId = root.tabEntities[idx].entity_id
        }
      }
      onActivateRequested: {
        if (root.tab === "rooms" && roomList.activateCursor) roomList.activateCursor()
        else {
          var list = root.tabEntities || []
          for (var i = 0; i < list.length; i++) {
            if (list[i].entity_id === root.focusedEntityId && service && service.actOnEntity)
              service.actOnEntity(list[i].entity_id, list[i].service)
          }
        }
      }
      onTextKey: function(t) {
        if (!root.configured) return
        if (t === "/") {
          root.filterOpen = true
          Qt.callLater(function() { if (filterField.forceActiveFocus) filterField.forceActiveFocus() })
        } else if (t === "r" || t === "R") root.refresh()
        else if (t === "s" || t === "S") {
          if (service) service.showSettings = !service.showSettings
        } else if (t === "f" || t === "F") root.toggleFocusedFavorite()
        else if (t === "1") { root.tab = "recents"; if (service) service.showSettings = false }
        else if (t === "2") { root.tab = "favorites"; if (service) service.showSettings = false }
        else if (t === "3") { root.tab = "rooms"; if (service) service.showSettings = false }
      }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(12)

        Flickable {
          visible: root.showOnboard
          width: parent.width
          height: visible ? Math.min(onboardLoader.item ? onboardLoader.item.implicitHeight : 0, Style.space(520)) : 0
          contentWidth: width
          contentHeight: onboardLoader.item ? onboardLoader.item.implicitHeight : 0
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          interactive: contentHeight > height

          Loader {
            id: onboardLoader
            width: parent.width
            active: root.showOnboard
            source: Qt.resolvedUrl("qml/Onboard.qml")
            onLoaded: {
              if (item) {
                item.service = root.service
                item.foreground = root.foreground
                item.fontFamily = root.fontFamily
                item.width = Qt.binding(function() { return column.width })
                if (root.addingInstance && item.reset) item.reset()
              }
            }
          }
        }

        Column {
          visible: root.configured && !root.addingInstance
          width: parent.width
          spacing: Style.space(10)

          Item {
            id: header
            width: parent.width
            implicitHeight: hero.implicitHeight
            readonly property bool settingsOpen: root.showSettings
            readonly property string openAreaId: roomList.openAreaId
            function headerClicked() {
              if (root.showSettings) {
                if (root.service) root.service.showSettings = false
              } else if (roomList.openAreaId) {
                roomList.goBack()
              } else if (root.service) {
                root.service.showSettings = true
                if (settingsPage.reloadFromService) settingsPage.reloadFromService()
              }
            }

            PanelHero {
              id: hero
              width: parent.width
              title: service && service.activeName ? service.activeName : "Hearth"
              meta: root.heroMeta
              foreground: root.foreground
              fontFamily: root.fontFamily
              iconComponent: Component {
                Text {
                  textFormat: Text.PlainText
                  text: "󰋜"
                  color: root.connectionState === "connected" ? root.foreground : root.dim
                  font.pixelSize: Style.font.display
                }
              }
              trailingControl: Component {
                Button {
                  text: header.settingsOpen ? "Done" : (header.openAreaId !== "" ? "Back" : "Settings")
                  foreground: hero.foreground
                  onClicked: header.headerClicked()
                }
              }
            }
          }

          Row {
            visible: !root.showSettings
            width: parent.width
            spacing: Style.space(8)
            Dropdown {
              width: parent.width - syncBtn.implicitWidth - addInstanceBtn.implicitWidth - parent.spacing * 2
              showLabel: false
              label: ""
              value: service && service.config ? String(service.config.activeInstanceId || "") : ""
              options: root.instanceOptions
              foreground: root.foreground
              fontFamily: root.fontFamily
              onChanged: function(v) {
                var cur = service && service.config ? String(service.config.activeInstanceId || "") : ""
                if (String(v) === cur) return
                if (service && service.setActiveId) service.setActiveId(v)
              }
            }
            Button {
              id: syncBtn
              text: "Sync"
              foreground: root.foreground
              onClicked: { if (service && service.fullSync) service.fullSync() }
            }
            Button {
              id: addInstanceBtn
              text: "+"
              foreground: root.foreground
              onClicked: { if (service && service.beginAddInstance) service.beginAddInstance() }
            }
          }

          EnergyStrip {
            visible: !root.showSettings
            width: parent.width
            energy: service && service.energy ? service.energy : ({})
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          TextField {
            id: filterField
            visible: root.filterOpen && !root.showSettings
            width: parent.width
            placeholderText: "Filter rooms and devices"
            text: root.filterQuery
            foreground: root.foreground
            onTextChanged: root.filterQuery = text
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Escape) {
                root.filterOpen = false
                root.filterQuery = ""
                text = ""
                keyCatcher.forceActiveFocus()
                event.accepted = true
              }
            }
          }

          ButtonGroup {
            visible: !root.showSettings
            width: parent.width
            foreground: root.foreground
            fontFamily: root.fontFamily
            value: root.tab
            options: [
              { value: "recents", label: "Recents" },
              { value: "favorites", label: "Favorites" },
              { value: "rooms", label: "Rooms" }
            ]
            onChanged: function(v) { root.tab = v }
          }

          Flickable {
            width: parent.width
            height: Math.min(bodyColumn.implicitHeight, Style.space(420))
            contentWidth: width
            contentHeight: bodyColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height

            Column {
              id: bodyColumn
              width: parent.width
              spacing: Style.space(8)

              SettingsPage {
                id: settingsPage
                visible: root.showSettings
                width: parent.width
                service: root.service
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              Column {
                visible: !root.showSettings && root.tab !== "rooms"
                width: parent.width
                spacing: Style.space(8)

                Text {
                  visible: root.tabEntities.length === 0
                  width: parent.width
                  text: root.tab === "favorites" ? "Star a device from a room." : "Act on a device to see it here."
                  color: root.dim
                  wrapMode: Text.WordWrap
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }

                Repeater {
                  model: root.tabEntities
                  EntityRow {
                    required property var modelData
                    width: bodyColumn.width
                    entity: modelData
                    service: root.service
                    bar: root.bar
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    onTouched: root.focusedEntityId = modelData.entity_id || ""
                  }
                }
              }

              RoomList {
                id: roomList
                visible: !root.showSettings && root.tab === "rooms"
                width: parent.width
                service: root.service
                bar: root.bar
                query: root.filterQuery
                foreground: root.foreground
                fontFamily: root.fontFamily
                onEntityTouched: function(entityId) { root.focusedEntityId = entityId }
              }
            }
          }
        }
      }
    }
  }

  property alias onboard: onboardLoader.item
}
