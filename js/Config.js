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
