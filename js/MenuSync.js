.pragma library

function slugSeg(value) {
  var s = String(value || "").toLowerCase()
  s = s.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")
  return s || "item"
}

function entitySeg(entityId) {
  return slugSeg(String(entityId || "").replace(/\./g, "_"))
}

function actLabel(entity) {
  var name = entity && entity.name ? String(entity.name) : String(entity && entity.entity_id ? entity.entity_id : "")
  var kind = entity && entity.kind ? String(entity.kind) : ""
  if (kind === "toggle") return "Toggle " + name
  if (kind === "fan") return name
  if (kind === "activate") return "Run " + name
  if (kind === "lock") return "Lock/Unlock " + name
  if (kind === "cover") return name
  return name
}

function actIcon(entity) {
  var kind = entity && entity.kind ? String(entity.kind) : ""
  if (kind === "toggle") return "󰌵"
  if (kind === "fan") return "󰈐"
  if (kind === "lock") return ""
  if (kind === "cover") return "󰠝"
  if (kind === "climate") return "󰔏"
  if (kind === "media") return "󰐊"
  return "󰋜"
}

function leaf(cli, entity) {
  var eid = String(entity.entity_id || "")
  return {
    icon: actIcon(entity),
    label: actLabel(entity),
    aliases: entity.name ? [String(entity.name)] : [],
    action: cli + " act " + eid
  }
}

function disconnected(cli) {
  return {
    "hearth": { icon: "󰋜", label: "Hearth", aliases: ["home assistant", "ha"] },
    "hearth.open": { icon: "󰏥", label: "Open Hearth", action: "omarchy-shell shell summon hearth" },
    "hearth.add": { icon: "", label: "Add Home Assistant", action: cli + " onboard" },
    "hearth.status": {
      icon: "󰋜",
      label: "Hearth is not connected",
      action: "omarchy-notification-send -g 󰋜 \"Hearth is not connected\""
    }
  }
}

function build(config, state, rooms, cli, connected) {
  var path = String(cli || "")
  var tree = {
    "hearth": { icon: "󰋜", label: "Hearth", aliases: ["home assistant", "ha"] },
    "hearth.open": { icon: "󰏥", label: "Open Hearth", action: "omarchy-shell shell summon hearth" },
    "hearth.add": { icon: "", label: "Add Home Assistant", action: path + " onboard" }
  }
  var instances = config && config.instances ? config.instances : []
  if (!instances.length) return disconnected(path)

  var activeId = String(config.activeInstanceId || "")
  var activeName = "Home"
  tree["hearth.instance"] = { icon: "󰒍", label: activeName, description: "current instance" }
  for (var i = 0; i < instances.length; i++) {
    var inst = instances[i]
    if (!inst || !inst.id) continue
    var iid = String(inst.id)
    var iname = inst.name ? String(inst.name) : iid
    if (iid === activeId) {
      activeName = iname
      tree["hearth.instance"].label = iname
    }
    tree["hearth.instance." + iid] = {
      icon: iid === activeId ? "✓" : "",
      label: iname,
      action: path + " instance " + iid
    }
  }

  if (!connected) {
    tree["hearth.status"] = {
      icon: "󰋜",
      label: "Hearth is not connected",
      action: "omarchy-notification-send -g 󰋜 \"Hearth is not connected\""
    }
  }

  var roomList = rooms || []
  if (roomList.length) tree["hearth.rooms"] = { icon: "󰠜", label: "Rooms" }
  for (var r = 0; r < roomList.length; r++) {
    var room = roomList[r]
    var rid = slugSeg(room.area_id || room.name || ("room" + r))
    var rname = room.name ? String(room.name) : rid
    var rkey = "hearth.rooms." + rid
    tree[rkey] = { icon: "󰍎", label: rname }
    var ents = room.entities || []
    var cap = Math.min(ents.length, 40)
    for (var e = 0; e < cap; e++) {
      if (!ents[e] || !ents[e].entity_id) continue
      var ekey = rkey + "." + entitySeg(ents[e].entity_id)
      var step = Number(ents[e].attrs && ents[e].attrs.percentage_step)
      if (ents[e].kind === "fan" && isFinite(step) && step > 0) {
        var speeds = Math.round(100 / step)
        if (speeds < 1) speeds = 1
        if (speeds > 6) speeds = 6
        tree[ekey] = { icon: actIcon(ents[e]), label: actLabel(ents[e]) }
        tree[ekey + ".off"] = { icon: "󰈐", label: "Off", action: path + " act " + ents[e].entity_id + " turn_off" }
        for (var sp = 1; sp <= speeds; sp++) {
          var pct = sp >= speeds ? 100 : Math.floor((sp * 100) / speeds)
          tree[ekey + "." + sp] = {
            icon: "󰈐",
            label: "Speed " + sp,
            action: path + " act " + ents[e].entity_id + " set_percentage " + pct
          }
        }
      } else {
        tree[ekey] = leaf(path, ents[e])
      }
    }
    if (ents.length > 40) {
      tree[rkey + ".more"] = {
        icon: "󰏥",
        label: "Open " + rname + " in Hearth",
        action: path + " open --room " + rid
      }
    }
  }

  var instState = state && state.instances && activeId ? state.instances[activeId] : null
  var favs = instState && instState.favorites ? instState.favorites : []
  if (favs.length) {
    tree["hearth.favorites"] = { icon: "", label: "Favorites" }
    var byId = ({})
    for (var a = 0; a < roomList.length; a++) {
      var list = roomList[a].entities || []
      for (var b = 0; b < list.length; b++)
        if (list[b] && list[b].entity_id) byId[String(list[b].entity_id)] = list[b]
    }
    for (var f = 0; f < favs.length; f++) {
      var fid = String(favs[f])
      var fent = byId[fid] || { entity_id: fid, name: fid, kind: "toggle" }
      tree["hearth.favorites." + entitySeg(fid)] = leaf(path, fent)
    }
  }

  var recents = instState && instState.recents ? instState.recents : []
  var recentRows = []
  for (var n = 0; n < recents.length && recentRows.length < 12; n++) {
    var item = recents[n]
    var reid = item && item.entity_id ? String(item.entity_id) : String(item || "")
    if (!reid) continue
    var rent = null
    for (var ra = 0; ra < roomList.length && !rent; ra++) {
      var relist = roomList[ra].entities || []
      for (var rb = 0; rb < relist.length; rb++)
        if (relist[rb] && String(relist[rb].entity_id) === reid) { rent = relist[rb]; break }
    }
    if (!rent) continue
    recentRows.push(rent)
  }
  if (recentRows.length) {
    tree["hearth.recents"] = { icon: "󰚰", label: "Recents" }
    for (var q = 0; q < recentRows.length; q++)
      tree["hearth.recents." + entitySeg(recentRows[q].entity_id)] = leaf(path, recentRows[q])
  }
  return tree
}
