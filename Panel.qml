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

  readonly property var barIdentity: hostWidget || root
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool configured: service ? service.configured === true : false
  readonly property string connectionState: service ? String(service.connectionState || "idle") : "idle"
  readonly property string heroMeta: {
    if (service && service.lastError) return String(service.lastError)
    if (connectionState === "connected") return (service && service.locationName) ? String(service.locationName) : "Online"
    return connectionState
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
  }

  onServiceChanged: {
    if (onboardLoader.item) onboardLoader.item.service = service
    if (roomList.service !== service) roomList.service = service
  }

  onOpenedChanged: {
    if (opened) {
      refresh()
      if (keyCatcher) keyCatcher.forceActiveFocus()
      cursorActive = false
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
      blocked: onboardLoader.item ? onboardLoader.item.fieldFocused === true : false
      onCloseRequested: {
        if (roomList.openAreaId) roomList.goBack()
        else root.close()
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.refresh()
      }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(12)

        // Onboard scrolls on its own so the form never sits under a connected view.
        Flickable {
          visible: !root.configured
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
            active: !root.configured
            source: Qt.resolvedUrl("qml/Onboard.qml")
            onLoaded: {
              if (item) {
                item.service = root.service
                item.foreground = root.foreground
                item.fontFamily = root.fontFamily
                item.width = Qt.binding(function() { return column.width })
              }
            }
          }
        }

        Column {
          visible: root.configured
          width: parent.width
          spacing: Style.space(10)

          PanelHero {
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
            trailingControl: roomList.openAreaId !== "" ? backButton : null
          }

          Flickable {
            width: parent.width
            height: Math.min(roomList.implicitHeight, Style.space(420))
            contentWidth: width
            contentHeight: roomList.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height

            RoomList {
              id: roomList
              width: parent.width
              service: root.service
              foreground: root.foreground
              fontFamily: root.fontFamily
            }
          }
        }
      }
    }
  }

  Component {
    id: backButton
    Button {
      text: "Back"
      foreground: root.foreground
      onClicked: roomList.goBack()
    }
  }

  property alias onboard: onboardLoader.item
}
