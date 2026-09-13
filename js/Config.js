.pragma library

function emptyConfig() {
  return { version: 1, activeInstanceId: "", instances: [] }
}

function emptyState() {
  return { version: 1, instances: {} }
}

function parseJsonObject(raw, fallback) {
  var text = String(raw || "").replace(/^\s+|\s+$/g, "")
  if (!text) return fallback
  try {
    var obj = JSON.parse(text)
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return fallback
    return obj
  } catch (e) {
    return null
  }
}

function loadConfig(raw) {
  var parsed = parseJsonObject(raw, emptyConfig())
  if (parsed === null) return { ok: false, error: "Hearth config is not valid JSON.", config: emptyConfig() }
  if (parsed.version !== undefined && parsed.version !== 1)
    return { ok: false, error: "Hearth config is newer than this plugin.", config: parsed }
  if (!Array.isArray(parsed.instances)) parsed.instances = []
  if (typeof parsed.activeInstanceId !== "string") parsed.activeInstanceId = ""
  parsed.version = 1
  return { ok: true, error: "", config: parsed }
}

function loadState(raw) {
  var parsed = parseJsonObject(raw, emptyState())
  if (parsed === null) return { ok: false, error: "Hearth state is not valid JSON.", state: emptyState() }
  if (parsed.version !== undefined && parsed.version !== 1)
    return { ok: false, error: "Hearth state is newer than this plugin.", state: parsed }
  if (!parsed.instances || typeof parsed.instances !== "object") parsed.instances = {}
  parsed.version = 1
  return { ok: true, error: "", state: parsed }
}

function instanceIds(config) {
  var ids = []
  var list = config && config.instances ? config.instances : []
  for (var i = 0; i < list.length; i++) {
    if (list[i] && list[i].id) ids.push(String(list[i].id))
  }
  return ids
}

function findInstance(config, id) {
  var list = config && config.instances ? config.instances : []
  for (var i = 0; i < list.length; i++) {
    if (list[i] && String(list[i].id) === String(id)) return list[i]
  }
  return null
}

function upsertInstance(config, inst) {
  var next = {
    version: 1,
    activeInstanceId: String(inst.id),
    instances: []
  }
  var replaced = false
  var list = config && config.instances ? config.instances : []
  for (var i = 0; i < list.length; i++) {
    if (list[i] && String(list[i].id) === String(inst.id)) {
      next.instances.push(inst)
      replaced = true
    } else {
      next.instances.push(list[i])
    }
  }
  if (!replaced) next.instances.push(inst)
  return next
}

function removeInstance(config, id) {
  var next = { version: 1, activeInstanceId: "", instances: [] }
  var list = config && config.instances ? config.instances : []
  for (var i = 0; i < list.length; i++) {
    if (!list[i] || String(list[i].id) === String(id)) continue
    next.instances.push(list[i])
  }
  if (next.instances.length > 0) {
    if (config && String(config.activeInstanceId) !== String(id))
      next.activeInstanceId = String(config.activeInstanceId)
    else
      next.activeInstanceId = String(next.instances[0].id)
  }
  return next
}

function copyState(state) {
  var next = { version: 1, instances: {} }
  var insts = state && state.instances ? state.instances : {}
  for (var k in insts) {
    if (!Object.prototype.hasOwnProperty.call(insts, k)) continue
    var src = insts[k] && typeof insts[k] === "object" ? insts[k] : {}
    var bag = {}
    for (var f in src) {
      if (Object.prototype.hasOwnProperty.call(src, f)) bag[f] = src[f]
    }
    if (!Array.isArray(bag.favorites)) bag.favorites = []
    if (!Array.isArray(bag.recents)) bag.recents = []
    next.instances[k] = bag
  }
  return next
}

function instanceState(state, id) {
  var key = String(id || "")
  var insts = state && state.instances ? state.instances : {}
  var cur = key ? insts[key] : null
  if (!cur || typeof cur !== "object") return { favorites: [], recents: [] }
  return {
    favorites: Array.isArray(cur.favorites) ? cur.favorites : [],
    recents: Array.isArray(cur.recents) ? cur.recents : []
  }
}

function ensureInstanceState(state, id) {
  var next = copyState(state)
  var key = String(id || "")
  if (!key) return next
  if (!next.instances[key]) next.instances[key] = { favorites: [], recents: [] }
  if (!Array.isArray(next.instances[key].favorites)) next.instances[key].favorites = []
  if (!Array.isArray(next.instances[key].recents)) next.instances[key].recents = []
  return next
}

function toggleFavorite(state, instanceId, entityId) {
  var next = ensureInstanceState(state, instanceId)
  var key = String(instanceId || "")
  var eid = String(entityId || "")
  var favs = next.instances[key].favorites.slice()
  var found = false
  var out = []
  for (var i = 0; i < favs.length; i++) {
    if (String(favs[i]) === eid) {
      found = true
      continue
    }
    out.push(String(favs[i]))
  }
  if (!found) out.push(eid)
  next.instances[key].favorites = out
  return { state: next, favorites: out, starred: !found }
}

function pushRecent(state, instanceId, entityId) {
  var next = ensureInstanceState(state, instanceId)
  var key = String(instanceId || "")
  var eid = String(entityId || "")
  var rec = next.instances[key].recents.slice()
  var out = [{ entity_id: eid, at: new Date().toISOString() }]
  for (var i = 0; i < rec.length; i++) {
    var item = rec[i]
    var other = item && item.entity_id ? String(item.entity_id) : String(item || "")
    if (!other || other === eid) continue
    out.push(item && item.entity_id ? item : { entity_id: other, at: "" })
    if (out.length >= 12) break
  }
  next.instances[key].recents = out
  return next
}

function removeInstanceState(state, id) {
  var next = copyState(state)
  delete next.instances[String(id || "")]
  return next
}
