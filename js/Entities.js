.pragma library

var TOGGLE = { light: 1, switch: 1, input_boolean: 1, siren: 1 }
var FAN = { fan: 1 }
var ACTIVATE = { scene: 1, script: 1, button: 1, automation: 1, input_button: 1 }
var COVER = { cover: 1, valve: 1 }
var LOCK = { lock: 1 }
var CLIMATE = { climate: 1 }
var MEDIA = { media_player: 1 }
var VACUUM = { vacuum: 1 }
var REMOTE = { remote: 1 }
var HUMIDIFIER = { humidifier: 1 }
var WATER = { water_heater: 1 }
var LAWN = { lawn_mower: 1 }
var ALARM = { alarm_control_panel: 1 }
var MEDIA_PAUSE = 1
var MEDIA_PLAY = 16384

function domainOf(entityId) {
  var s = String(entityId || "")
  var i = s.indexOf(".")
  return i === -1 ? "" : s.slice(0, i)
}

function kindOf(domain) {
  if (TOGGLE[domain]) return "toggle"
  if (FAN[domain]) return "fan"
  if (ACTIVATE[domain]) return "activate"
  if (COVER[domain]) return "cover"
  if (LOCK[domain]) return "lock"
  if (CLIMATE[domain]) return "climate"
  if (MEDIA[domain]) return "media"
  if (VACUUM[domain]) return "vacuum"
  if (REMOTE[domain]) return "remote"
  if (HUMIDIFIER[domain]) return "humidifier"
  if (WATER[domain]) return "water"
  if (LAWN[domain]) return "lawn"
  if (ALARM[domain]) return "alarm"
  return ""
}

function validEntityId(entityId) {
  return /^[a-z0-9_]+\.[a-z0-9_]+$/.test(String(entityId || ""))
}

function primaryService(domain, kind, state) {
  if (kind === "toggle") return "toggle"
  if (kind === "fan") return "set_percentage"
  if (domain === "button" || domain === "input_button") return "press"
  if (kind === "activate") return "turn_on"
  if (kind === "media") return "media_play_pause"
  if (kind === "lock") return (state === "unlocked" || state === "unlocking") ? "lock" : "unlock"
  if (domain === "cover") return "open_cover"
  if (domain === "valve") return "open_valve"
  if (kind === "vacuum") return "start"
  if (kind === "remote") return state === "on" ? "turn_off" : "turn_on"
  if (kind === "humidifier" || kind === "water") return state === "on" ? "turn_off" : "turn_on"
  if (kind === "lawn") return "start_mowing"
  if (kind === "alarm") return state === "disarmed" ? "alarm_arm_home" : "alarm_disarm"
  if (kind === "climate") return "set_temperature"
  return ""
}

function hasService(services, domain, name) {
  if (!services || typeof services !== "object") return true
  var list = services[domain]
  if (!list || !list.length) return Object.keys(services).length === 0
  for (var i = 0; i < list.length; i++) if (String(list[i]) === String(name)) return true
  return false
}

function num(value) {
  var n = Number(value)
  return isFinite(n) ? n : NaN
}

function pickAttrs(st) {
  var a = (st && st.attributes) ? st.attributes : {}
  return {
    temperature: a.temperature,
    target_temp: a.target_temp,
    current_temperature: a.current_temperature,
    target_temp_step: a.target_temp_step,
    min_temp: a.min_temp,
    max_temp: a.max_temp,
    temperature_unit: a.temperature_unit,
    hvac_modes: a.hvac_modes,
    hvac_mode: a.hvac_mode,
    volume_level: a.volume_level,
    volume_step: a.volume_step,
    supported_features: a.supported_features,
    humidity: a.humidity,
    current_humidity: a.current_humidity,
    min_humidity: a.min_humidity,
    max_humidity: a.max_humidity,
    brightness: a.brightness,
    brightness_pct: a.brightness_pct,
    supported_color_modes: a.supported_color_modes,
    color_mode: a.color_mode,
    percentage: a.percentage,
    percentage_step: a.percentage_step,
    preset_modes: a.preset_modes,
    preset_mode: a.preset_mode,
    supported_features: a.supported_features,
    code_arm_required: a.code_arm_required,
    code_disarm_required: a.code_disarm_required
  }
}

function climateStep(attrs) {
  var step = num(attrs && attrs.target_temp_step)
  if (isFinite(step) && step > 0) return step
  var unit = String(attrs && attrs.temperature_unit ? attrs.temperature_unit : "")
  if (unit.indexOf("F") !== -1 || unit.indexOf("f") !== -1) return 1
  return 0.5
}

function climateTarget(attrs) {
  var t = num(attrs && attrs.target_temp)
  if (isFinite(t)) return t
  t = num(attrs && attrs.temperature)
  if (isFinite(t)) return t
  return num(attrs && attrs.current_temperature)
}

function clampTemp(value, attrs) {
  var v = Number(value)
  var lo = num(attrs && attrs.min_temp)
  var hi = num(attrs && attrs.max_temp)
  if (isFinite(lo) && v < lo) v = lo
  if (isFinite(hi) && v > hi) v = hi
  return v
}

function nextHvacMode(attrs) {
  var modes = attrs && attrs.hvac_modes ? attrs.hvac_modes : []
  var list = []
  for (var i = 0; i < modes.length; i++) {
    var m = String(modes[i])
    if (m && m !== "hvac_action") list.push(m)
  }
  if (list.length === 0) return ""
  var cur = String(attrs && attrs.hvac_mode ? attrs.hvac_mode : "")
  var idx = -1
  for (var j = 0; j < list.length; j++) if (list[j] === cur) idx = j
  return list[(idx + 1) % list.length]
}

function mediaCanPlayPause(st, attrs) {
  var a = attrs || (st && st.attributes) || {}
  var feat = a.supported_features
  if (feat === undefined || feat === null || feat === "") {
    var state = String(st && st.state ? st.state : "")
    return state === "playing" || state === "paused" || state === "idle"
  }
  var n = Number(feat)
  if (!isFinite(n)) return true
  return (n & MEDIA_PAUSE) !== 0 || (n & MEDIA_PLAY) !== 0
}

function lightIsDimmer(attrs) {
  var modes = attrs && attrs.supported_color_modes
  if (modes && modes.length) {
    for (var i = 0; i < modes.length; i++) {
      if (String(modes[i]) !== "onoff") return true
    }
    return false
  }
  if (attrs && attrs.brightness !== undefined && attrs.brightness !== null) return true
  var feat = num(attrs && attrs.supported_features)
  return isFinite(feat) && (feat & 1) !== 0
}

function lightBrightnessPct(state, attrs) {
  if (String(state || "") === "off") return 0
  var p = num(attrs && attrs.brightness_pct)
  if (isFinite(p)) return Math.max(0, Math.min(100, Math.round(p)))
  var b = num(attrs && attrs.brightness)
  if (isFinite(b)) return Math.max(0, Math.min(100, Math.round(b * 100 / 255)))
  return 0
}

function fanStep(attrs) {
  var step = num(attrs && attrs.percentage_step)
  if (isFinite(step) && step > 0) return step
  return 100 / 3
}

function fanSpeedCount(attrs) {
  var n = Math.round(100 / fanStep(attrs))
  if (n < 1) n = 1
  if (n > 6) n = 6
  return n
}

function fanHasSpeeds(attrs) {
  var feat = num(attrs && attrs.supported_features)
  if (isFinite(feat) && feat > 0 && (feat & 1) === 0) return false
  return true
}

function fanSpeedIndex(state, attrs) {
  if (String(state || "") === "off" || String(state || "") === "unavailable") return 0
  var pct = num(attrs && attrs.percentage)
  if (!isFinite(pct) || pct <= 0) return 0
  // Home Assistant: math.ceil(percentage / percentage_step)
  var idx = Math.ceil(pct / fanStep(attrs) - 1e-9)
  var max = fanSpeedCount(attrs)
  if (idx < 1) idx = 1
  if (idx > max) idx = max
  return idx
}

function fanPercentageForIndex(idx, attrs) {
  var i = Number(idx)
  if (!isFinite(i) || i <= 0) return 0
  var max = fanSpeedCount(attrs)
  if (i >= max) return 100
  // floor so HA's ceil(percentage / step) maps back to i.
  // round(2 * 33.33) = 67 → ceil(67/33.33) = 3 (stuck on high).
  return Math.floor((i * 100) / max)
}

function mediaVolumeStep(attrs) {
  var step = num(attrs && attrs.volume_step)
  if (isFinite(step) && step > 0) return step
  return 0.05
}

function includeRow(kind, domain, st, services) {
  var a = (st && st.attributes) ? st.attributes : {}
  var state = String(st && st.state ? st.state : "")
  if (kind === "climate") {
    if (a.temperature === undefined && a.target_temp === undefined && a.current_temperature === undefined)
      return false
  }
  if (kind === "media") {
    if (!mediaCanPlayPause(st, a) && a.volume_level === undefined) return false
  }
  if (kind === "remote") {
    if (state !== "on" && state !== "off") return false
    if (!hasService(services, "remote", "turn_on") && !hasService(services, "remote", "turn_off")) return false
  }
  if (kind === "alarm") {
    if (a.code_arm_required === true || a.code_disarm_required === true) return false
    if (!hasService(services, "alarm_control_panel", "alarm_arm_home") &&
        !hasService(services, "alarm_control_panel", "alarm_disarm")) return false
  }
  if (kind === "vacuum") {
    if (!hasService(services, "vacuum", "start") && !hasService(services, "vacuum", "return_to_base")) return false
  }
  if (kind === "humidifier") {
    if (!hasService(services, "humidifier", "turn_on") && !hasService(services, "humidifier", "turn_off") &&
        !hasService(services, "humidifier", "set_humidity") && !hasService(services, "humidifier", "set_temperature"))
      return false
  }
  if (kind === "water") {
    if (!hasService(services, "water_heater", "turn_on") && !hasService(services, "water_heater", "turn_off") &&
        !hasService(services, "water_heater", "set_temperature"))
      return false
  }
  if (kind === "lawn") {
    if (!hasService(services, "lawn_mower", "start_mowing") && !hasService(services, "lawn_mower", "dock")) return false
  }
  return true
}

function coverService(domain, action) {
  if (domain === "valve") return action + "_valve"
  return action + "_cover"
}

function isHidden(reg) {
  if (!reg) return false
  if (reg.disabled_by) return true
  if (reg.hidden_by) return true
  var c = reg.entity_category
  return c === "config" || c === "diagnostic"
}

function effectiveArea(reg, devices) {
  if (reg && reg.area_id) return String(reg.area_id)
  var id = reg && reg.device_id ? String(reg.device_id) : ""
  var seen = ({})
  while (id && !seen[id]) {
    seen[id] = true
    var dev = devices[id]
    if (!dev) break
    if (dev.area_id) return String(dev.area_id)
    id = dev.parent_device_id ? String(dev.parent_device_id) : ""
  }
  return ""
}

function deviceUserName(dev) {
  if (!dev) return ""
  if (dev.name_by_user) return String(dev.name_by_user)
  return ""
}

function friendly(state, reg, entityId, devices) {
  if (reg && reg.name) return String(reg.name)
  var dev = null
  if (reg && devices && reg.device_id) dev = devices[String(reg.device_id)]
  var duser = deviceUserName(dev)
  var orig = reg && reg.original_name ? String(reg.original_name).replace(/^\s+|\s+$/g, "") : ""
  if (duser) {
    if (!orig || orig.toLowerCase() === duser.toLowerCase()) return duser
    return duser + " " + orig
  }
  if (state && state.attributes && state.attributes.friendly_name)
    return String(state.attributes.friendly_name)
  if (orig) return orig
  if (dev && dev.name) {
    var dname = String(dev.name)
    if (orig && orig.toLowerCase() !== dname.toLowerCase()) return dname + " " + orig
    return dname
  }
  return String(entityId || "")
}

function selectedAreas(config, areas) {
  if (config && config.allRooms) {
    var all = []
    for (var i = 0; i < areas.length; i++) all.push(String(areas[i].area_id))
    return { ids: all, unassigned: true }
  }
  return { ids: (config && config.selectedAreaIds) ? config.selectedAreaIds.slice() : [], unassigned: false }
}

function areaAllowed(areaId, sel) {
  if (areaId === "") return sel.unassigned === true
  for (var i = 0; i < sel.ids.length; i++) if (String(sel.ids[i]) === String(areaId)) return true
  return false
}

function build(config, snap) {
  var inst = null
  if (config && config.instances) {
    for (var i = 0; i < config.instances.length; i++) {
      if (config.instances[i] && String(config.instances[i].id) === String(config.activeInstanceId)) {
        inst = config.instances[i]
        break
      }
    }
  }
  var areasIn = (snap && snap.areas) ? snap.areas : []
  var devicesIn = (snap && snap.devices) ? snap.devices : []
  var regsIn = (snap && snap.entities) ? snap.entities : []
  var statesIn = (snap && snap.states) ? snap.states : []
  var services = (snap && snap.services) ? snap.services : null

  var devices = ({})
  for (var d = 0; d < devicesIn.length; d++) {
    var dev = devicesIn[d]
    if (dev && dev.id) devices[String(dev.id)] = dev
  }
  var regs = ({})
  for (var r = 0; r < regsIn.length; r++) {
    var reg = regsIn[r]
    if (reg && reg.entity_id) regs[String(reg.entity_id)] = reg
  }
  var areaNames = ({})
  var areaList = []
  for (var a = 0; a < areasIn.length; a++) {
    var area = areasIn[a]
    if (!area) continue
    var aid = String(area.area_id || area.id || "")
    if (!aid) continue
    areaNames[aid] = String(area.name || aid)
    areaList.push({ area_id: aid, name: areaNames[aid] })
  }
  areaList.sort(function(x, y) { return x.name.localeCompare(y.name) })

  var sel = selectedAreas(inst, areaList)
  var includeAll = !inst || inst.includeAllEntities !== false
  var allow = ({})
  if (!includeAll && inst && inst.selectedEntityIds) {
    for (var s = 0; s < inst.selectedEntityIds.length; s++) allow[String(inst.selectedEntityIds[s])] = true
  }

  var byArea = ({})
  var lightsOn = 0
  var count = 0
  for (var t = 0; t < statesIn.length; t++) {
    if (count >= 5000) break
    var st = statesIn[t]
    if (!st || !st.entity_id) continue
    var eid = String(st.entity_id)
    var domain = domainOf(eid)
    var kind = kindOf(domain)
    if (!kind) continue
    var registry = regs[eid]
    if (isHidden(registry)) continue
    var areaId = effectiveArea(registry, devices)
    if (!areaAllowed(areaId, sel)) continue
    if (!includeAll && !allow[eid]) continue
    var name = friendly(st, registry, eid, devices)
    var state = String(st.state || "")
    if (!validEntityId(eid)) continue
    if (!includeRow(kind, domain, st, services)) continue
    var attrs = pickAttrs(st)
    var row = {
      entity_id: eid,
      name: name,
      domain: domain,
      kind: kind,
      state: state,
      area_id: areaId,
      service: primaryService(domain, kind, state),
      attrs: attrs,
      favorite: false,
      pending: false,
      lastError: ""
    }
    var bucket = areaId || "unassigned"
    if (!byArea[bucket]) byArea[bucket] = []
    byArea[bucket].push(row)
    count++
    if ((kind === "toggle" || kind === "fan") && (state === "on" || Number(st.attributes && st.attributes.brightness) > 0 || Number(st.attributes && st.attributes.percentage) > 0))
      lightsOn++
  }

  function disambiguateNames(list) {
  var counts = ({})
  for (var i = 0; i < list.length; i++) {
    var n = String(list[i].name || "")
    counts[n] = (counts[n] || 0) + 1
  }
  for (var j = 0; j < list.length; j++) {
    var name = String(list[j].name || "")
    if (counts[name] > 1 && list[j].domain)
      list[j].name = name + " (" + list[j].domain + ")"
  }
  return list
}

function sortRows(list) {
    list.sort(function(x, y) { return x.name.localeCompare(y.name) })
    return list
  }

  var rooms = []
  for (var b = 0; b < areaList.length; b++) {
    var id = areaList[b].area_id
    if (!areaAllowed(id, sel)) continue
    var ents = disambiguateNames(sortRows(byArea[id] || []))
    rooms.push({ area_id: id, name: areaList[b].name, count: ents.length, entities: ents })
  }
  if (sel.unassigned) {
    var un = disambiguateNames(sortRows(byArea["unassigned"] || []))
    if (un.length > 0)
      rooms.push({ area_id: "unassigned", name: "Unassigned", count: un.length, entities: un })
  }
  return { rooms: rooms, lightsOn: lightsOn }
}

function patch(rooms, entity) {
  if (!rooms || !entity || !entity.entity_id) return rooms
  var eid = String(entity.entity_id)
  var state = String(entity.state || "")
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id === eid) {
        ents[j].state = state
        ents[j].pending = false
        ents[j].lastError = ""
        ents[j].service = primaryService(ents[j].domain, ents[j].kind, state)
        if (entity.attributes) ents[j].attrs = pickAttrs(entity)
        if (entity.attributes && entity.attributes.friendly_name)
          ents[j].name = String(entity.attributes.friendly_name)
        else if (entity.name)
          ents[j].name = String(entity.name)
        return rooms
      }
    }
  }
  return rooms
}

function lightsOnCount(rooms) {
  var n = 0
  if (!rooms) return 0
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      var k = ents[j].kind
      if ((k === "toggle" || k === "fan") && ents[j].state === "on") n++
    }
  }
  return n
}

function optimisticBrightness(rooms, entityId, brightness) {
  if (!rooms) return rooms
  var eid = String(entityId)
  var bri = Number(brightness)
  if (!isFinite(bri)) return rooms
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id !== eid) continue
      var attrs = ents[j].attrs || {}
      attrs.brightness = bri <= 0 ? 0 : bri
      attrs.brightness_pct = bri <= 0 ? 0 : Math.round(bri * 100 / 255)
      ents[j].attrs = attrs
      ents[j].state = bri <= 0 ? "off" : "on"
      ents[j].pending = true
      ents[j].lastError = ""
      return rooms
    }
  }
  return rooms
}

function optimisticFan(rooms, entityId, idx) {
  if (!rooms) return rooms
  var eid = String(entityId)
  var speed = Number(idx)
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id !== eid) continue
      var attrs = ents[j].attrs || {}
      attrs.percentage = fanPercentageForIndex(speed, attrs)
      ents[j].attrs = attrs
      ents[j].state = speed <= 0 ? "off" : "on"
      ents[j].pending = true
      ents[j].lastError = ""
      return rooms
    }
  }
  return rooms
}

function optimisticToggle(rooms, entityId) {
  if (!rooms) return rooms
  var eid = String(entityId)
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id === eid && ents[j].kind === "toggle") {
        ents[j].state = ents[j].state === "on" ? "off" : "on"
        ents[j].pending = true
        ents[j].lastError = ""
        return rooms
      }
    }
  }
  return rooms
}

function findEntity(rooms, entityId) {
  var eid = String(entityId || "")
  if (!rooms) return null
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id === eid) return ents[j]
    }
  }
  return null
}

function cloneRow(row) {
  if (!row) return null
  return {
    entity_id: row.entity_id,
    name: row.name,
    domain: row.domain,
    kind: row.kind,
    state: row.state,
    area_id: row.area_id,
    service: row.service,
    attrs: row.attrs || {},
    favorite: !!row.favorite,
    pending: !!row.pending,
    lastError: row.lastError || ""
  }
}

function stubEntity(entityId) {
  var eid = String(entityId || "")
  var domain = domainOf(eid)
  var kind = kindOf(domain)
  return {
    entity_id: eid,
    name: eid,
    domain: domain,
    kind: kind || "toggle",
    state: "unavailable",
    area_id: "",
    service: primaryService(domain, kind || "toggle", "unavailable"),
    attrs: {},
    favorite: true,
    pending: false,
    lastError: ""
  }
}

function markFavorites(rooms, favoriteIds) {
  var set = ({})
  var ids = favoriteIds || []
  for (var i = 0; i < ids.length; i++) set[String(ids[i])] = true
  if (!rooms) return rooms
  for (var r = 0; r < rooms.length; r++) {
    var ents = rooms[r].entities || []
    for (var j = 0; j < ents.length; j++)
      ents[j].favorite = !!set[ents[j].entity_id]
  }
  return rooms
}

function setPending(rooms, entityId, pending, lastError) {
  var eid = String(entityId || "")
  if (!rooms) return rooms
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id === eid) {
        ents[j].pending = !!pending
        if (lastError !== undefined) ents[j].lastError = String(lastError || "")
        return rooms
      }
    }
  }
  return rooms
}

function favoritesList(rooms, favoriteIds) {
  var out = []
  var ids = favoriteIds || []
  for (var i = 0; i < ids.length; i++) {
    var eid = String(ids[i])
    if (!validEntityId(eid)) continue
    var found = findEntity(rooms, eid)
    if (found) {
      var row = cloneRow(found)
      row.favorite = true
      out.push(row)
    } else {
      out.push(stubEntity(eid))
    }
  }
  out.sort(function(a, b) { return String(a.name).localeCompare(String(b.name)) })
  return out
}

function recentsList(rooms, recents) {
  var out = []
  var list = recents || []
  for (var i = 0; i < list.length; i++) {
    var item = list[i]
    var eid = item && item.entity_id ? String(item.entity_id) : String(item || "")
    if (!validEntityId(eid)) continue
    var found = findEntity(rooms, eid)
    if (!found) continue
    out.push(cloneRow(found))
  }
  return out
}
