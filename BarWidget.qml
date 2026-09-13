import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "hearth"

  readonly property var svc: bar && bar.shell && bar.shell.serviceFor ? bar.shell.serviceFor("hearth") : null
  readonly property bool connected: svc ? svc.connected === true : false
  readonly property string pillLabel: {
    if (svc && svc.pillLabel) return String(svc.pillLabel)
    return "Hearth"
  }
  readonly property color pillColor: connected ? (bar ? bar.barForeground : Color.foreground)
                                               : Qt.darker(bar ? bar.barForeground : Color.foreground, 1.55)

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
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

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

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.pillLabel
    foreground: root.pillColor
    tooltipText: ""
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
