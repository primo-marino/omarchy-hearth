.pragma library

var TOGGLE = { light: 1, switch: 1, fan: 1, input_boolean: 1, siren: 1 }
var ACTIVATE = { scene: 1, script: 1, button: 1, automation: 1, input_button: 1 }
var COVER = { cover: 1, valve: 1 }
var LOCK = { lock: 1 }
var CLIMATE = { climate: 1 }
var MEDIA = { media_player: 1 }

function domainOf(entityId) {
  var s = String(entityId || "")
  var i = s.indexOf(".")
  return i === -1 ? "" : s.slice(0, i)
}

function kindOf(domain) {
  if (TOGGLE[domain]) return "toggle"
  if (ACTIVATE[domain]) return "activate"
  if (COVER[domain]) return "cover"
  if (LOCK[domain]) return "lock"
  if (CLIMATE[domain]) return "climate"
  if (MEDIA[domain]) return "media"
  return ""
}

function primaryService(domain, kind) {
  if (kind === "toggle") return "toggle"
  if (domain === "button" || domain === "input_button") return "press"
  if (kind === "activate") return "turn_on"
  if (kind === "media") return "media_play_pause"
  return ""
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

function friendly(state, reg, entityId) {
  if (state && state.attributes && state.attributes.friendly_name)
    return String(state.attributes.friendly_name)
  if (reg && reg.name) return String(reg.name)
  if (reg && reg.original_name) return String(reg.original_name)
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
    var name = friendly(st, registry, eid)
    var state = String(st.state || "")
    var row = {
      entity_id: eid,
      name: name,
      domain: domain,
      kind: kind,
      state: state,
      area_id: areaId,
      service: primaryService(domain, kind)
    }
    var bucket = areaId || "unassigned"
    if (!byArea[bucket]) byArea[bucket] = []
    byArea[bucket].push(row)
    count++
    if (kind === "toggle" && (state === "on" || Number(st.attributes && st.attributes.brightness) > 0))
      lightsOn++
  }

  function sortRows(list) {
    list.sort(function(x, y) { return x.name.localeCompare(y.name) })
    return list
  }

  var rooms = []
  for (var b = 0; b < areaList.length; b++) {
    var id = areaList[b].area_id
    if (!areaAllowed(id, sel)) continue
    var ents = sortRows(byArea[id] || [])
    rooms.push({ area_id: id, name: areaList[b].name, count: ents.length, entities: ents })
  }
  if (sel.unassigned) {
    var un = sortRows(byArea["unassigned"] || [])
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
        if (entity.attributes && entity.attributes.friendly_name)
          ents[j].name = String(entity.attributes.friendly_name)
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
      if (ents[j].kind === "toggle" && ents[j].state === "on") n++
    }
  }
  return n
}

function optimisticToggle(rooms, entityId) {
  if (!rooms) return rooms
  var eid = String(entityId)
  for (var i = 0; i < rooms.length; i++) {
    var ents = rooms[i].entities || []
    for (var j = 0; j < ents.length; j++) {
      if (ents[j].entity_id === eid && ents[j].kind === "toggle") {
        ents[j].state = ents[j].state === "on" ? "off" : "on"
        return rooms
      }
    }
  }
  return rooms
}
