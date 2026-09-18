import QtQuick
import qs.Commons
import qs.Ui
import "qml"

BarWidget {
  id: root
  moduleName: "io.github.primo-marino.hearth"

  readonly property var svc: bar && bar.shell && bar.shell.serviceFor ? bar.shell.serviceFor("io.github.primo-marino.hearth") : null
  readonly property bool connected: svc ? svc.connected === true : false
  readonly property int lightsOn: svc && svc.lightsOn ? Number(svc.lightsOn) : 0
  readonly property string countText: (connected && lightsOn > 0) ? (lightsOn + " on") : ""
  readonly property color pillColor: connected ? (bar ? bar.barForeground : Color.foreground)
                                               : Qt.darker(bar ? bar.barForeground : Color.foreground, 1.55)
  readonly property string tipText: {
    if (!svc || !svc.configured) return "Hearth — click to set up"
    if (!connected) return "Disconnected from Home Assistant"
    var bits = []
    if (lightsOn > 0) bits.push(lightsOn + " on")
    if (svc.energy && isFinite(Number(svc.energy.solarPowerW)) && Number(svc.energy.solarPowerW) > 0) {
      var w = Number(svc.energy.solarPowerW)
      bits.push(w >= 1000 ? ((Math.round(w / 100) / 10) + " kW") : (Math.round(w) + " W"))
    }
    if (bits.length) return bits.join(" · ")
    return svc.activeName ? String(svc.activeName) : "Hearth"
  }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
    if ("service" in target) target.service = root.svc
  }

  function refresh() {
    if (root.svc && root.svc.refresh) root.svc.refresh()
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item && panelLoader.item.openFromHotkey) panelLoader.item.openFromHotkey()
  }

  function close() {
    if (panelLoader.item && panelLoader.item.close) panelLoader.item.close()
  }

  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  visible: true
  implicitWidth: chip.implicitWidth
  implicitHeight: chip.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onSvcChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  Item {
    id: chip
    implicitWidth: row.implicitWidth + Style.space(10)
    implicitHeight: bar ? bar.barSize : Style.bar.sizeHorizontal

    Row {
      id: row
      z: 1
      anchors.centerIn: parent
      spacing: Style.space(5)

      HearthIcon {
        iconSize: Style.space(13)
        color: root.pillColor
        lit: root.connected
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        visible: root.countText !== ""
        text: root.countText
        color: root.pillColor
        font.family: bar ? bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.body
        renderType: Text.NativeRendering
        anchors.verticalCenter: parent.verticalCenter
      }
    }

    WidgetButton {
      id: button
      z: 2
      anchors.fill: parent
      bar: root.bar
      text: ""
      labelVisible: false
      hasVisualContent: true
      opacity: 0.01
      tooltipText: root.tipText
      dimmed: !root.connected && !!(root.svc && root.svc.configured)
      onPressed: function(b) {
        if (!root.bar) return
        if (b === Qt.RightButton) {
          if (root.svc) root.svc.showSettings = true
          root.togglePanel()
        } else if (b === Qt.MiddleButton) {
          root.refresh()
        } else {
          root.togglePanel()
        }
      }
    }
  }
}
