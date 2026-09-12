import QtQuick
import qs.Commons
import qs.Ui

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
    if (service && service.refreshEnergy) service.refreshEnergy()
  }

  onServiceChanged: {
    if (onboardLoader.item) onboardLoader.item.service = service
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
    contentHeight: panel.fittedContentHeight(Math.min(column.implicitHeight, Style.space(560)))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: onboardLoader.item ? onboardLoader.item.fieldFocused === true : false
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.refresh()
        else if (t === "s" || t === "S") { if (service) service.showSettings = true }
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

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

          Column {
            visible: root.configured
            width: parent.width
            spacing: Style.space(10)

            PanelHero {
              width: parent.width
              title: service && service.activeName ? service.activeName : "Hearth"
              meta: root.connectionState
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
            }

            Text {
              width: parent.width
              text: service && service.lastError ? service.lastError : "Rooms and devices land in the next slice. This instance is saved."
              color: service && service.lastError ? Color.urgent : root.dim
              wrapMode: Text.WordWrap
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
            }
          }
        }
      }
    }
  }

  property alias onboard: onboardLoader.item
}
