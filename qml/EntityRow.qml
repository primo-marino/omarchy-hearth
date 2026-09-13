import QtQuick
import qs.Commons
import qs.Ui
import "../js/Entities.js" as Entities

Item {
  id: root
  property var entity: ({})
  property var service: null
  property var bar: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string kind: entity && entity.kind ? String(entity.kind) : ""
  readonly property string domain: entity && entity.domain ? String(entity.domain) : ""
  readonly property var attrs: entity && entity.attrs ? entity.attrs : ({})
  readonly property bool unavailable: {
    var st = entity && entity.state ? String(entity.state) : ""
    return st === "unavailable" || st === "unknown"
  }
  readonly property bool starred: !!(entity && entity.favorite)
  readonly property string errorText: entity && entity.lastError ? String(entity.lastError) : ""
  readonly property bool showPlay: kind === "media" && Entities.mediaCanPlayPause({ state: entity.state }, attrs)
  readonly property bool showVolume: kind === "media" && attrs.volume_level !== undefined && attrs.volume_level !== null
  readonly property bool fanSpeeds: kind === "fan" && Entities.fanHasSpeeds(attrs)
  readonly property var fanOptions: {
    var opts = [{ value: "0", label: "Off" }]
    if (!fanSpeeds) return opts
    var n = Entities.fanSpeedCount(attrs)
    for (var i = 1; i <= n; i++) opts.push({ value: String(i), label: String(i) })
    return opts
  }
  readonly property string fanValue: String(Entities.fanSpeedIndex(entity.state, attrs))
  implicitHeight: row.implicitHeight
  width: parent ? parent.width : 0

  signal touched()

  function run(svcName, data) {
    root.touched()
    if (root.unavailable) return
    if (root.service && root.service.actOnEntity)
      root.service.actOnEntity(root.entity.entity_id, svcName || root.entity.service, data)
  }

  function star() {
    root.touched()
    if (root.service && root.service.toggleFavorite)
      root.service.toggleFavorite(root.entity.entity_id)
  }

  function climateCaption() {
    var cur = Entities.num(attrs.current_temperature)
    if (!isFinite(cur)) cur = Entities.num(attrs.temperature)
    var tgt = Entities.climateTarget(attrs)
    var mode = attrs.hvac_mode ? String(attrs.hvac_mode) : ""
    var parts = []
    if (isFinite(cur)) parts.push(cur + "°")
    if (isFinite(tgt)) parts.push("set " + tgt + "°")
    if (mode) parts.push(mode)
    if (entity.pending) parts.push("…")
    else if (entity.state) parts.push(String(entity.state))
    return parts.join(" · ")
  }

  function bumpClimate(dir) {
    var step = Entities.climateStep(attrs)
    var cur = Entities.climateTarget(attrs)
    if (!isFinite(cur)) cur = Entities.num(attrs.current_temperature)
    if (!isFinite(cur)) return
    var next = Entities.clampTemp(cur + dir * step, attrs)
    root.run("set_temperature", { temperature: next })
  }

  function setFan(idx) {
    var n = Number(idx)
    var pct = Entities.fanPercentageForIndex(n, attrs)
    if (n <= 0 || pct <= 0) root.run("turn_off")
    else root.run("set_percentage", { percentage: pct })
  }

  function bumpSetpoint(dir, key, minKey, maxKey, serviceName) {
    var step = key === "humidity" ? 1 : Entities.climateStep(attrs)
    var cur = Entities.num(attrs[key])
    if (!isFinite(cur)) cur = Entities.num(attrs["current_" + key])
    if (!isFinite(cur)) return
    var next = cur + dir * step
    var lo = Entities.num(attrs[minKey])
    var hi = Entities.num(attrs[maxKey])
    if (isFinite(lo) && next < lo) next = lo
    if (isFinite(hi) && next > hi) next = hi
    var data = {}
    data[key === "humidity" ? "humidity" : "temperature"] = next
    root.run(serviceName, data)
  }

  Row {
    id: row
    width: parent.width
    spacing: Style.space(8)

    Button {
      id: starButton
      text: root.starred ? "★" : "☆"
      foreground: root.starred ? Color.accent : root.dim
      fontFamily: root.fontFamily
      onClicked: root.star()
    }

    Column {
      width: parent.width - starButton.implicitWidth - parent.spacing
      spacing: Style.space(4)
      opacity: root.unavailable ? 0.45 : 1

      Toggle {
        visible: root.kind === "toggle" || (root.kind === "fan" && !root.fanSpeeds)
        width: parent.width
        enabled: !root.unavailable
        label: entity.name || entity.entity_id || ""
        description: entity.pending ? "…" : (entity.state || "")
        checked: entity.state === "on"
        foreground: root.foreground
        fontFamily: root.fontFamily
        onClicked: root.run("toggle")
      }

      PanelSlider {
        visible: root.kind === "toggle" && root.domain === "light" && attrs.brightness !== undefined && attrs.brightness !== null
        width: parent.width
        enabled: !root.unavailable
        bar: root.bar
        value: Math.max(0, Math.min(255, Number(attrs.brightness) || 0))
        minimum: 0
        maximum: 255
        integer: true
        onReleased: function(v) {
          if (v <= 0) root.run("turn_off")
          else root.run("turn_on", { brightness: Math.round(v) })
        }
      }

      Column {
        visible: root.kind === "fan" && root.fanSpeeds
        width: parent.width
        spacing: Style.space(4)
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
          text: entity.pending ? "…" : (root.fanValue === "0" ? "off" : ("speed " + root.fanValue))
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
        ButtonGroup {
          width: parent.width
          foreground: root.foreground
          fontFamily: root.fontFamily
          value: root.fanValue
          options: root.fanOptions
          onChanged: function(v) {
            if (String(v) === root.fanValue) return
            root.setFan(v)
          }
        }
      }

      Column {
        visible: root.kind === "climate"
        width: parent.width
        spacing: Style.space(4)
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
          text: root.climateCaption()
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
        Row {
          spacing: Style.space(6)
          Button {
            enabled: !root.unavailable
            text: "−"
            foreground: root.foreground
            onClicked: root.bumpClimate(-1)
          }
          Button {
            enabled: !root.unavailable
            text: "+"
            foreground: root.foreground
            onClicked: root.bumpClimate(1)
          }
          Button {
            visible: Entities.nextHvacMode(root.attrs) !== ""
            enabled: !root.unavailable
            text: attrs.hvac_mode ? String(attrs.hvac_mode) : "Mode"
            foreground: root.foreground
            onClicked: root.run("set_hvac_mode", { hvac_mode: Entities.nextHvacMode(root.attrs) })
          }
        }
      }

      Column {
        visible: root.kind === "media"
        width: parent.width
        spacing: Style.space(4)
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
          text: entity.pending ? "…" : (entity.state || "")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
        Button {
          visible: root.showPlay
          enabled: !root.unavailable
          text: entity.state === "playing" ? "Pause" : "Play"
          foreground: root.foreground
          onClicked: root.run("media_play_pause")
        }
        PanelSlider {
          visible: root.showVolume
          width: parent.width
          enabled: !root.unavailable
          bar: root.bar
          value: Math.max(0, Math.min(1, Number(attrs.volume_level) || 0))
          minimum: 0
          maximum: 1
          step: Entities.mediaVolumeStep(root.attrs)
          onReleased: function(v) { root.run("volume_set", { volume_level: v }) }
        }
      }

      Row {
        visible: root.kind !== "toggle" && root.kind !== "climate" && root.kind !== "media" && root.kind !== "fan"
        width: parent.width
        spacing: Style.space(8)

        Column {
          width: parent.width - actions.implicitWidth - parent.spacing
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
            text: entity.pending ? "…" : (entity.state || "")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }
        }

        Row {
          id: actions
          spacing: Style.space(6)

          Button {
            visible: root.kind === "activate"
            enabled: !root.unavailable
            text: "Run"
            foreground: root.foreground
            onClicked: root.run()
          }

          Button {
            visible: root.kind === "cover"
            enabled: !root.unavailable
            text: "Open"
            foreground: root.foreground
            onClicked: root.run(Entities.coverService(root.domain, "open"))
          }
          Button {
            visible: root.kind === "cover"
            enabled: !root.unavailable
            text: "Close"
            foreground: root.foreground
            onClicked: root.run(Entities.coverService(root.domain, "close"))
          }
          Button {
            visible: root.kind === "cover"
            enabled: !root.unavailable
            text: "Stop"
            foreground: root.foreground
            onClicked: root.run(Entities.coverService(root.domain, "stop"))
          }

          Button {
            visible: root.kind === "lock"
            enabled: !root.unavailable
            text: (entity.state === "locked" || entity.state === "locking") ? "Unlock" : "Lock"
            foreground: root.foreground
            onClicked: root.run(entity.state === "locked" || entity.state === "locking" ? "unlock" : "lock")
          }

          Button {
            visible: root.kind === "vacuum"
            enabled: !root.unavailable
            text: "Start"
            foreground: root.foreground
            onClicked: root.run("start")
          }
          Button {
            visible: root.kind === "vacuum"
            enabled: !root.unavailable
            text: "Dock"
            foreground: root.foreground
            onClicked: root.run("return_to_base")
          }

          Button {
            visible: root.kind === "remote"
            enabled: !root.unavailable
            text: entity.state === "on" ? "Off" : "On"
            foreground: root.foreground
            onClicked: root.run(entity.state === "on" ? "turn_off" : "turn_on")
          }

          Button {
            visible: root.kind === "humidifier" || root.kind === "water"
            enabled: !root.unavailable
            text: entity.state === "on" ? "Off" : "On"
            foreground: root.foreground
            onClicked: root.run(entity.state === "on" ? "turn_off" : "turn_on")
          }
          Button {
            visible: root.kind === "humidifier" && (attrs.humidity !== undefined || attrs.current_humidity !== undefined)
            enabled: !root.unavailable
            text: "−"
            foreground: root.foreground
            onClicked: root.bumpSetpoint(-1, "humidity", "min_humidity", "max_humidity", "set_humidity")
          }
          Button {
            visible: root.kind === "humidifier" && (attrs.humidity !== undefined || attrs.current_humidity !== undefined)
            enabled: !root.unavailable
            text: "+"
            foreground: root.foreground
            onClicked: root.bumpSetpoint(1, "humidity", "min_humidity", "max_humidity", "set_humidity")
          }
          Button {
            visible: root.kind === "water"
            enabled: !root.unavailable
            text: "−"
            foreground: root.foreground
            onClicked: root.bumpSetpoint(-1, "temperature", "min_temp", "max_temp", "set_temperature")
          }
          Button {
            visible: root.kind === "water"
            enabled: !root.unavailable
            text: "+"
            foreground: root.foreground
            onClicked: root.bumpSetpoint(1, "temperature", "min_temp", "max_temp", "set_temperature")
          }

          Button {
            visible: root.kind === "lawn"
            enabled: !root.unavailable
            text: "Mow"
            foreground: root.foreground
            onClicked: root.run("start_mowing")
          }
          Button {
            visible: root.kind === "lawn"
            enabled: !root.unavailable
            text: "Dock"
            foreground: root.foreground
            onClicked: root.run("dock")
          }

          Button {
            visible: root.kind === "alarm"
            enabled: !root.unavailable
            text: entity.state === "disarmed" ? "Arm home" : "Disarm"
            foreground: root.foreground
            onClicked: root.run(entity.state === "disarmed" ? "alarm_arm_home" : "alarm_disarm")
          }
        }
      }

      Text {
        visible: root.errorText !== ""
        width: parent.width
        text: root.errorText
        color: Color.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }
    }
  }
}
