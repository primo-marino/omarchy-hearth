import QtQuick
import qs.Commons
import qs.Ui
import "../js/Energy.js" as Energy

Row {
  id: root
  spacing: Style.space(16)

  property var energy: ({})
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property bool shown: !!(energy && energy.enabled)
  visible: shown
  width: parent ? parent.width : 0

  readonly property bool showSolar: Energy.formatKwh(energy.solarKwh) !== ""
  readonly property bool showImport: Energy.formatKwh(energy.gridImportKwh) !== ""
  readonly property bool showExport: Energy.formatKwh(energy.gridExportKwh) !== ""

  Column {
    visible: root.showSolar
    spacing: Style.space(2)
    Text {
      text: "☀  " + Energy.formatKwh(energy.solarKwh)
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.subtitle
      font.bold: true
    }
    Text {
      text: "solar today"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  Column {
    visible: root.showImport
    spacing: Style.space(2)
    Text {
      text: "↓  " + Energy.formatKwh(energy.gridImportKwh)
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.subtitle
      font.bold: true
    }
    Text {
      text: "grid in"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  Column {
    visible: root.showExport
    spacing: Style.space(2)
    Text {
      text: "↑  " + Energy.formatKwh(energy.gridExportKwh)
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.subtitle
      font.bold: true
    }
    Text {
      text: "grid out"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
