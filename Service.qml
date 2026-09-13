import QtQuick
import Quickshell
import Quickshell.Io
import "js/Url.js" as Url
import "js/Config.js" as Config
import "js/Entities.js" as Entities
import "js/Energy.js" as EnergyJs
import "js/MenuSync.js" as MenuSync

Item {
  id: root

  property var shell: null
  property var manifest: null
  property var pluginRegistry: null
  property var barWidgetRegistry: null
  property string omarchyPath: ""

  readonly property string home: Quickshell.env("HOME")
  readonly property string configDir: home + "/.config/omarchy/hearth"
  readonly property string stateDir: home + "/.local/state/omarchy/hearth"
  readonly property string cacheDir: home + "/.cache/omarchy/hearth"
  readonly property string configPath: configDir + "/config.json"
  readonly property string statePath: stateDir + "/state.json"
  readonly property string helperPath: {
    var url = String(Qt.resolvedUrl("helpers/ha_bridge.py"))
    if (url.indexOf("file://") === 0) url = url.substring(7)
    return url
  }
  readonly property string cliPath: {
    var url = String(Qt.resolvedUrl("helpers/hearth"))
    if (url.indexOf("file://") === 0) url = url.substring(7)
    return url
  }

  property var config: Config.emptyConfig()
  property var state: Config.emptyState()
  property bool configLoaded: false
  property bool configNewer: false
  property string configError: ""
  property string pendingInstanceId: ""
  property string connectionState: "idle"
  property string lastError: ""
  property string haVersion: ""
  property string locationName: ""
  property bool showSettings: false
  property bool addingInstance: false
  property string _prevConnection: "idle"
  property int _cmdId: 1
  property var _pending: ({})
  property string _stdoutBuf: ""
  property int _restartMs: 1000
  property var pendingAreas: []
  property bool loginBusy: false
  property bool providersBusy: false
  property bool passwordAvailable: false
  property var lastLoginResult: null
  property var rooms: []
  property var allAreas: []
  property var favoriteEntities: []
  property var recentEntities: []
  property int lightsOn: 0
  property var _cmdQueue: []
  property bool helperReady: false
  property string pendingOpenAreaId: ""
  property var pendingActs: ({})
  property bool pendingWatch: false
  signal loginFinished(var result)

  readonly property bool configured: {
    if (!config || !config.instances) return false
    return config.instances.length > 0 && String(config.activeInstanceId || "") !== ""
  }
  readonly property bool connected: connectionState === "connected"
  readonly property string activeName: {
    var inst = Config.findInstance(config, config.activeInstanceId)
    return inst && inst.name ? inst.name : "Hearth"
  }
  readonly property var energy: {
    var st = state && state.instances ? state.instances[config.activeInstanceId] : null
    if (st && st.energy) return st.energy
    return EnergyJs.empty()
  }
  readonly property string pillLabel: {
    if (!configured) return "Hearth"
    var power = EnergyJs.formatPower(root.energy && root.energy.solarPowerW)
    if (power) return power
    if (root.lightsOn > 0) return root.lightsOn + " on"
    return "Hearth"
  }
  readonly property string statusText: configured ? (activeName + " · " + connectionState) : "Hearth — not connected"

  function nextId() {
    root._cmdId += 1
    return root._cmdId
  }

  function flushCmdQueue() {
    if (!helperReady || !helper.running) return
    var q = root._cmdQueue
    root._cmdQueue = []
    for (var i = 0; i < q.length; i++) helper.write(q[i])
  }

  function sendCmd(obj, cb) {
    var id = nextId()
    obj.id = id
    var line = JSON.stringify(obj)
    if (line.length > 256 * 1024) {
      console.warn("hearth: dropping oversize command")
      if (cb) cb({ ok: false, error: "Command too large." })
      return -1
    }
    var pending = root._pending
    pending[id] = { cb: cb || null }
    root._pending = pending
    if (!helper.running) helper.running = true
    if (helperReady) helper.write(line + "\n")
    else root._cmdQueue = root._cmdQueue.concat([line + "\n"])
    if (obj.token) obj.token = ""
    if (obj.password) obj.password = ""
    if (obj.username) obj.username = ""
    return id
  }

  function handleLine(line) {
    if (!line) return
    if (line.length > 256 * 1024) {
      console.warn("hearth: dropping oversize helper line")
      return
    }
    var msg
    try { msg = JSON.parse(line) } catch (e) {
      console.warn("hearth: helper non-JSON line")
      return
    }
    if (!msg || typeof msg !== "object") return
    if (msg.event === "result") {
      var rid = msg.id
      var rec = root._pending[rid]
      if (!rec && rid !== undefined && rid !== null)
        rec = root._pending[String(rid)] || root._pending[Number(rid)]
      delete root._pending[rid]
      delete root._pending[String(rid)]
      delete root._pending[Number(rid)]
      if (rec && rec.cb) rec.cb(msg)
      return
    }
    if (msg.event === "connection") {
      var nextState = String(msg.state || "idle")
      var wasUp = root._prevConnection === "connected"
      connectionState = nextState
      if (msg.haVersion) haVersion = String(msg.haVersion)
      if (msg.locationName) locationName = String(msg.locationName)
      if (nextState === "connected") lastError = ""
      if (msg.error) lastError = String(msg.error)
      if (wasUp && nextState !== "connected") root.notifyLoss()
      root._prevConnection = nextState
      return
    }
    if (msg.event === "log" && msg.level === "error") {
      lastError = String(msg.message || "")
      return
    }
    if (msg.event === "snapshot") {
      snapFile.reload()
      Qt.callLater(function() { root.applySnapshot(snapFile.text()) })
      root.refreshEnergy(true)
      return
    }
    if (msg.event === "state_changed" && msg.entity) {
      var eid = String(msg.entity.entity_id || "")
      root.rooms = Entities.patch(root.rooms, msg.entity)
      if (eid && root.pendingActs[eid]) {
        var rec = root.pendingActs[eid]
        var nextPending = root.pendingActs
        delete nextPending[eid]
        root.pendingActs = nextPending
        root.pendingWatch = root.hasPendingActs()
        if (rec && rec.kind === "toggle") root.recordRecent(eid)
      }
      if (EnergyJs.isPowerEntity(root.energy, eid)) {
        var w = EnergyJs.toWatts(msg.entity.state, msg.entity.attributes)
        if (isFinite(w)) root.patchEnergyPower(w)
      }
      root.refreshLists()
    }
  }

  function copyEntity(e) {
    if (!e) return e
    return {
      entity_id: e.entity_id,
      name: e.name,
      domain: e.domain,
      kind: e.kind,
      state: e.state,
      area_id: e.area_id,
      service: e.service,
      attrs: e.attrs || {},
      favorite: !!e.favorite,
      pending: !!e.pending,
      lastError: e.lastError || ""
    }
  }

  function bumpRooms() {
    var next = []
    var list = root.rooms || []
    for (var i = 0; i < list.length; i++) {
      var r = list[i]
      var ents = []
      var src = r.entities || []
      for (var j = 0; j < src.length; j++) ents.push(root.copyEntity(src[j]))
      next.push({
        area_id: r.area_id,
        name: r.name,
        count: ents.length,
        entities: ents
      })
    }
    root.rooms = next
  }

  function activeFavorites() {
    return Config.instanceState(root.state, root.config.activeInstanceId).favorites
  }

  function refreshLists() {
    var inst = Config.instanceState(root.state, root.config.activeInstanceId)
    root.rooms = Entities.markFavorites(root.rooms, inst.favorites)
    root.bumpRooms()
    root.favoriteEntities = Entities.favoritesList(root.rooms, inst.favorites)
    root.recentEntities = Entities.recentsList(root.rooms, inst.recents)
    root.lightsOn = Entities.lightsOnCount(root.rooms)
    root.scheduleMenuSync()
  }

  function applySnapshot(raw) {
    var snap
    try { snap = JSON.parse(String(raw || "{}")) } catch (e) { return }
    var areas = []
    var rawAreas = snap.areas || []
    for (var i = 0; i < rawAreas.length; i++) {
      if (!rawAreas[i]) continue
      var aid = String(rawAreas[i].area_id || rawAreas[i].id || "")
      if (!aid) continue
      areas.push({ area_id: aid, name: String(rawAreas[i].name || aid) })
    }
    areas.sort(function(a, b) { return a.name.localeCompare(b.name) })
    root.allAreas = areas
    var built = Entities.build(root.config, snap)
    root.rooms = built.rooms || []
    root.refreshLists()
  }

  function hasPendingActs() {
    var pa = root.pendingActs
    for (var k in pa) {
      if (Object.prototype.hasOwnProperty.call(pa, k) && pa[k]) return true
    }
    return false
  }

  function failAct(entityId, err) {
    var eid = String(entityId || "")
    var pa = root.pendingActs
    var rec = pa[eid]
    if (rec && rec.kind === "toggle")
      root.rooms = Entities.optimisticToggle(root.rooms, eid)
    if (rec && rec.kind === "fan" && rec.prevIdx !== undefined)
      root.rooms = Entities.optimisticFan(root.rooms, eid, rec.prevIdx)
    root.rooms = Entities.setPending(root.rooms, eid, false, err || "Call failed.")
    delete pa[eid]
    root.pendingActs = pa
    root.pendingWatch = root.hasPendingActs()
    root.refreshLists()
  }

  function expirePending() {
    var now = Date.now()
    var pa = root.pendingActs
    var stale = []
    for (var k in pa) {
      if (!Object.prototype.hasOwnProperty.call(pa, k) || !pa[k]) continue
      var ttl = pa[k].ttl || 2000
      if (now - pa[k].at >= ttl) stale.push(k)
    }
    for (var i = 0; i < stale.length; i++) root.failAct(stale[i], "No response")
  }

  function recordRecent(entityId) {
    if (!root.config.activeInstanceId) return
    root.state = Config.pushRecent(root.state, root.config.activeInstanceId, entityId)
    root.writeState()
    root.refreshLists()
  }

  function writeState() {
    stateFile.setText(JSON.stringify(root.state, null, 2) + "\n")
  }

  function isFavorite(entityId) {
    var favs = root.activeFavorites()
    var eid = String(entityId || "")
    for (var i = 0; i < favs.length; i++) if (String(favs[i]) === eid) return true
    return false
  }

  function toggleFavorite(entityId) {
    var eid = String(entityId || "")
    if (!Entities.validEntityId(eid)) return { ok: false, error: "Bad entity id." }
    if (!root.config.activeInstanceId) return { ok: false, error: "No instance." }
    var result = Config.toggleFavorite(root.state, root.config.activeInstanceId, eid)
    root.state = result.state
    root.writeState()
    root.refreshLists()
    return { ok: true, starred: result.starred, favorites: result.favorites }
  }

  function patchEnergyPower(watts) {
    if (!root.config.activeInstanceId) return
    var next = Config.ensureInstanceState(root.state, root.config.activeInstanceId)
    var bag = next.instances[root.config.activeInstanceId]
    var en = bag.energy && typeof bag.energy === "object" ? bag.energy : EnergyJs.empty()
    en.solarPowerW = watts
    bag.energy = en
    root.state = next
    root.writeState()
  }

  function applyEnergy(data) {
    if (!root.config.activeInstanceId) return
    var parsed = EnergyJs.fromHelper(data)
    var next = Config.ensureInstanceState(root.state, root.config.activeInstanceId)
    next.instances[root.config.activeInstanceId].energy = parsed
    root.state = next
    root.writeState()
  }

  function actOnEntity(entityId, serviceName, data) {
    var eid = String(entityId || "")
    if (!Entities.validEntityId(eid)) return { ok: false, error: "Bad entity id." }
    var domain = Entities.domainOf(eid)
    var kind = Entities.kindOf(domain)
    var found = Entities.findEntity(root.rooms, eid)
    var svc = serviceName || Entities.primaryService(domain, kind, found ? found.state : "")
    if (!svc || !root.config.activeInstanceId) return { ok: false, error: "Nothing to call." }
    var pa = root.pendingActs
    pa[eid] = { kind: kind, at: Date.now(), ttl: kind === "toggle" ? 2000 : 16000 }
    root.pendingActs = pa
    root.pendingWatch = true
    if (kind === "toggle") {
      root.rooms = Entities.optimisticToggle(root.rooms, eid)
      root.refreshLists()
    }
    if (kind === "fan") {
      var pct = data && data.percentage !== undefined ? Number(data.percentage) : (svc === "turn_off" ? 0 : NaN)
      var idx = (!isFinite(pct) || pct <= 0 || svc === "turn_off") ? 0 : Entities.fanSpeedIndex("on", {
        percentage: pct,
        percentage_step: found && found.attrs ? found.attrs.percentage_step : undefined
      })
      pa[eid] = { kind: kind, at: Date.now(), ttl: 16000, prevIdx: found ? Entities.fanSpeedIndex(found.state, found.attrs) : 0 }
      root.pendingActs = pa
      root.rooms = Entities.optimisticFan(root.rooms, eid, idx)
      root.refreshLists()
    }
    var payload = {
      type: "call_service",
      domain: domain,
      service: svc,
      target: { entity_id: eid }
    }
    if (data && typeof data === "object") payload.service_data = data
    sendCmd({
      cmd: "call",
      instanceId: root.config.activeInstanceId,
      payload: payload
    }, function(msg) {
      if (msg && msg.ok) {
        if (kind !== "toggle") {
          var done = root.pendingActs
          delete done[eid]
          root.pendingActs = done
          root.pendingWatch = root.hasPendingActs()
          root.recordRecent(eid)
        }
      } else {
        root.failAct(eid, msg && msg.error ? String(msg.error) : "Call failed.")
      }
    })
    return { ok: true }
  }

  function testConnection(fields) {
    var name = (fields && fields.name) ? String(fields.name) : "Home"
    var parsed = Url.parse(fields && fields.url ? fields.url : "")
    if (!parsed.ok) {
      lastLoginResult = { ok: false, error: parsed.error }
      return lastLoginResult
    }
    var taken = Config.instanceIds(config)
    if (!pendingInstanceId) pendingInstanceId = Url.uniqueInstanceId(Url.slug(name), taken)
    var cmd = {
      cmd: "login",
      instanceId: pendingInstanceId,
      url: parsed.origin,
      tlsInsecure: !!(fields && fields.tlsInsecure)
    }
    if (fields && fields.authMethod === "username") {
      cmd.username = String(fields.username || "")
      cmd.password = String(fields.password || "")
    } else {
      cmd.token = String(fields && fields.token ? fields.token : "")
    }
    loginBusy = true
    lastLoginResult = null
    sendCmd(cmd, function(msg) {
      var reply = {
        ok: msg && msg.ok === true,
        error: msg && msg.error ? String(msg.error) : (msg && msg.ok ? "" : "Login failed."),
        instanceId: pendingInstanceId,
        haVersion: msg && msg.data ? String(msg.data.haVersion || "") : "",
        locationName: msg && msg.data ? String(msg.data.locationName || "") : "",
        kind: msg && msg.data ? String(msg.data.kind || "") : "",
        areas: msg && msg.data && msg.data.areas ? msg.data.areas : []
      }
      if (reply.ok) {
        haVersion = reply.haVersion
        locationName = reply.locationName
        pendingAreas = reply.areas
      }
      lastError = reply.ok ? "" : reply.error
      lastLoginResult = reply
      loginBusy = false
      loginFinished(reply)
    })
    cmd.token = ""
    cmd.password = ""
    cmd.username = ""
    return { ok: true, pending: true, instanceId: pendingInstanceId }
  }

  function probeProviders(origin, tlsInsecure) {
    providersBusy = true
    sendCmd({ cmd: "providers", url: origin, tlsInsecure: !!tlsInsecure }, function(msg) {
      passwordAvailable = !!(msg && msg.data && msg.data.passwordAvailable)
      providersBusy = false
    })
    return { ok: true, pending: true }
  }

  function completeOnboard(fields) {
    if (!pendingInstanceId) return { ok: false, error: "Test connection first." }
    var parsed = Url.parse(fields && fields.url ? fields.url : "")
    if (!parsed.ok) return { ok: false, error: parsed.error }
    var inst = {
      id: pendingInstanceId,
      name: String(fields.name || "Home"),
      url: parsed.origin,
      tlsInsecure: !!fields.tlsInsecure,
      plaintextHttp: !!fields.plaintextHttp,
      httpAcknowledged: !!fields.httpAcknowledged,
      allRooms: !!fields.allRooms,
      selectedAreaIds: fields.selectedAreaIds || [],
      includeAllEntities: fields.includeAllEntities !== false,
      selectedEntityIds: fields.selectedEntityIds || []
    }
    config = Config.upsertInstance(config, inst)
    writeConfig()
    sendCmd({ cmd: "connect", instanceId: pendingInstanceId, url: parsed.origin, tlsInsecure: !!inst.tlsInsecure }, function(msg) {
      if (msg && msg.ok) {
        connectionState = "connected"
        lastError = ""
        root.refreshEnergy(true)
      } else {
        connectionState = "failed"
        lastError = msg && msg.error ? String(msg.error) : "Connect failed."
      }
    })
    pendingInstanceId = ""
    root.addingInstance = false
    return { ok: true, instanceId: inst.id }
  }

  function cancelOnboard() {
    if (pendingInstanceId)
      sendCmd({ cmd: "forget", instanceId: pendingInstanceId }, null)
    pendingInstanceId = ""
    pendingAreas = []
    root.addingInstance = false
  }

  function refresh() {
    if (!configured) return
    sendCmd({ cmd: "connect", instanceId: config.activeInstanceId }, null)
  }

  function refreshEnergy(force) {
    if (!configured) return
    if (!force) {
      var en = root.energy
      if (en && en.enabled === false && en.fetchedAt) {
        var t = Date.parse(en.fetchedAt)
        if (isFinite(t) && (Date.now() - t) < 3600000) return
      }
    }
    sendCmd({ cmd: "energy", instanceId: config.activeInstanceId }, function(msg) {
      if (msg && msg.ok && msg.data) root.applyEnergy(msg.data)
      else root.applyEnergy(EnergyJs.empty())
    })
  }

  function writeConfig() {
    configFile.setText(JSON.stringify(config, null, 2) + "\n")
  }

  function activeInstance() {
    return Config.findInstance(root.config, root.config.activeInstanceId)
  }

  function setSelection(fields) {
    var inst = root.activeInstance()
    if (!inst) return { ok: false, error: "No instance." }
    var next = {
      id: inst.id,
      name: inst.name,
      url: inst.url,
      tlsInsecure: !!inst.tlsInsecure,
      plaintextHttp: !!inst.plaintextHttp,
      httpAcknowledged: !!inst.httpAcknowledged,
      allRooms: !!(fields && fields.allRooms),
      selectedAreaIds: (fields && fields.selectedAreaIds) ? fields.selectedAreaIds : [],
      includeAllEntities: fields && fields.includeAllEntities !== undefined ? !!fields.includeAllEntities : inst.includeAllEntities !== false,
      selectedEntityIds: inst.selectedEntityIds || []
    }
    root.config = Config.upsertInstance(root.config, next)
    root.writeConfig()
    snapFile.reload()
    return { ok: true }
  }

  function replaceToken(token) {
    var inst = root.activeInstance()
    if (!inst) return { ok: false, error: "No instance." }
    var tok = String(token || "")
    if (!tok) return { ok: false, error: "Paste a token." }
    root.pendingInstanceId = String(inst.id)
    return root.testConnection({
      name: inst.name,
      url: inst.url,
      token: tok,
      tlsInsecure: !!inst.tlsInsecure,
      authMethod: "token"
    })
  }

  function removeActiveInstance() {
    var id = String(root.config.activeInstanceId || "")
    if (!id) return { ok: false, error: "No instance." }
    root.sendCmd({ cmd: "forget", instanceId: id }, null)
    root.config = Config.removeInstance(root.config, id)
    root.state = Config.removeInstanceState(root.state, id)
    root.writeConfig()
    root.writeState()
    root.showSettings = false
    root.rooms = []
    root.favoriteEntities = []
    root.recentEntities = []
    root.lightsOn = 0
    root.allAreas = []
    if (root.configured && root.config.activeInstanceId)
      root.sendCmd({ cmd: "connect", instanceId: root.config.activeInstanceId }, null)
    else
      root.connectionState = "idle"
    return { ok: true }
  }

  function statusJson() {
    return JSON.stringify({
      configured: configured,
      connected: connected,
      connectionState: connectionState,
      activeInstanceId: config.activeInstanceId || "",
      name: activeName,
      lastError: lastError,
      hasToken: configured,
      pillLabel: pillLabel
    })
  }

  function actJson(payload) {
    var fields
    try { fields = JSON.parse(payload) } catch (e) { return JSON.stringify({ ok: false, error: "Bad JSON." }) }
    return JSON.stringify(root.actOnEntity(fields.entity_id || fields.entityId, fields.service, fields.service_data || fields.data))
  }

  function setActiveId(id) {
    if (!Config.findInstance(config, id)) return JSON.stringify({ ok: false, error: "Unknown instance." })
    var prev = String(config.activeInstanceId || "")
    var next = String(id)
    if (prev === next) return JSON.stringify({ ok: true, skipped: "same" })
    if (prev && prev !== next) sendCmd({ cmd: "disconnect", instanceId: prev }, null)
    config.activeInstanceId = next
    writeConfig()
    sendCmd({ cmd: "connect", instanceId: next }, null)
    root.scheduleMenuSync()
    return JSON.stringify({ ok: true })
  }

  function beginAddInstance() {
    root.pendingInstanceId = ""
    root.addingInstance = true
    root.showSettings = false
    if (root.shell && root.shell.summon) root.shell.summon("hearth", "{}")
  }

  function finishAddInstance() {
    root.addingInstance = false
  }

  function notifyLoss() {
    var detail = root.lastError ? String(root.lastError) : "Reconnecting to Home Assistant"
    notifyProc.command = ["omarchy-notification-send", "-g", "󰋜", "-u", "normal", "Hearth disconnected", detail]
    notifyProc.running = false
    notifyProc.running = true
  }

  function listInstancesJson() {
    return JSON.stringify({ instances: config.instances || [], activeInstanceId: config.activeInstanceId || "" })
  }

  function testConnectionJson(payload) {
    var fields
    try { fields = JSON.parse(payload) } catch (e) { return JSON.stringify({ ok: false, error: "Bad JSON." }) }
    return JSON.stringify(testConnection(fields))
  }

  function completeOnboardJson(payload) {
    var fields
    try { fields = JSON.parse(payload) } catch (e) { return JSON.stringify({ ok: false, error: "Bad JSON." }) }
    return JSON.stringify(completeOnboard(fields))
  }

  function toggleFavoriteJson(payload) {
    var fields
    try { fields = JSON.parse(payload) } catch (e) { return JSON.stringify({ ok: false, error: "Bad JSON." }) }
    return JSON.stringify(root.toggleFavorite(fields.entity_id || fields.entityId))
  }

  function setSelectionJson(payload) {
    var fields
    try { fields = JSON.parse(payload) } catch (e) { return JSON.stringify({ ok: false, error: "Bad JSON." }) }
    return JSON.stringify(root.setSelection(fields))
  }

  function scheduleMenuSync() {
    menuDebounce.restart()
  }

  function menuSyncNow() {
    var tree = MenuSync.build(root.config, root.state, root.rooms, root.cliPath, root.connected)
    menuTreeFile.setText(JSON.stringify(tree, null, 2) + "\n")
    menuRun.restart()
    return JSON.stringify({ ok: true, pending: true })
  }

  function reloadFiles() {
    configFile.reload()
    stateFile.reload()
    return "ok"
  }

  Component.onCompleted: {
    mkdir.command = ["mkdir", "-p", "-m", "0700", configDir, stateDir, cacheDir, cacheDir + "/entities"]
    mkdir.running = true
    helper.running = true
  }

  Process {
    id: mkdir
  }

  Process {
    id: menuProc
    running: false
  }

  Process {
    id: notifyProc
    running: false
  }

  Timer {
    id: menuDebounce
    interval: 250
    repeat: false
    onTriggered: root.menuSyncNow()
  }

  Timer {
    id: menuRun
    interval: 120
    repeat: false
    onTriggered: {
      menuProc.command = ["python3", root.cliPath, "menu-sync"]
      menuProc.running = false
      menuProc.running = true
    }
  }

  Timer {
    id: midnightEnergy
    interval: 60000
    repeat: true
    running: root.configured
    property string firedDay: ""
    onTriggered: {
      var d = new Date()
      if (d.getHours() !== 0 || d.getMinutes() > 3) return
      var key = d.toDateString()
      if (midnightEnergy.firedDay === key) return
      midnightEnergy.firedDay = key
      root.refreshEnergy(true)
    }
  }

  Process {
    id: helper
    command: ["python3", "-u", root.helperPath]
    running: false
    stdinEnabled: true
    stdout: SplitParser {
      onRead: function(line) { root.handleLine(line) }
    }
    stderr: SplitParser {
      onRead: function(line) {
        if (!line) return
        if (line.indexOf("Errno 9") !== -1 || line.indexOf("Bad file descriptor") !== -1) return
        if (line.indexOf("Exception ignored") !== -1) return
        console.warn("hearth helper: " + line)
      }
    }
    onStarted: {
      root.helperReady = true
      root._restartMs = 1000
      root.flushCmdQueue()
      if (root.configured && root.config.activeInstanceId) {
        root.sendCmd({ cmd: "connect", instanceId: root.config.activeInstanceId }, null)
        root.refreshEnergy(true)
      }
    }
    onExited: function() {
      root.helperReady = false
      root.connectionState = "idle"
      restartTimer.interval = root._restartMs
      restartTimer.restart()
      root._restartMs = Math.min(30000, root._restartMs * 2)
      if (root._restartMs < 1000) root._restartMs = 1000
    }
    onRunningChanged: {
      if (running) root._restartMs = 1000
      else root.helperReady = false
    }
  }

  Timer {
    id: restartTimer
    interval: 1000
    repeat: false
    onTriggered: helper.running = true
  }

  Timer {
    id: pendingWatchTimer
    interval: 500
    repeat: true
    running: root.pendingWatch
    onTriggered: root.expirePending()
  }

  Timer {
    id: energyTimer
    interval: 600000
    repeat: true
    running: root.configured
    onTriggered: root.refreshEnergy(false)
  }

  FileView {
    id: configFile
    path: root.configPath
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onLoaded: {
      var loaded = Config.loadConfig(text())
      root.configLoaded = true
      if (!loaded.ok) {
        root.configNewer = loaded.error.indexOf("newer") !== -1
        root.configError = loaded.error
        return
      }
      root.config = loaded.config
      root.configError = ""
      if (root.helperReady && root.configured && root.config.activeInstanceId)
        root.sendCmd({ cmd: "connect", instanceId: root.config.activeInstanceId }, null)
      root.scheduleMenuSync()
    }
    onLoadFailed: {
      root.configLoaded = true
      root.config = Config.emptyConfig()
      root.scheduleMenuSync()
    }
  }

  FileView {
    id: snapFile
    path: root.config && root.config.activeInstanceId ? root.cacheDir + "/entities/" + root.config.activeInstanceId + ".json" : ""
    watchChanges: true
    printErrors: false
    onLoaded: root.applySnapshot(text())
    onLoadFailed: { root.rooms = []; root.lightsOn = 0 }
  }

  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onLoaded: {
      var loaded = Config.loadState(text())
      if (loaded.ok) {
        root.state = loaded.state
        root.refreshLists()
      }
    }
    onLoadFailed: {
      root.state = Config.emptyState()
      root.refreshLists()
    }
  }

  FileView {
    id: menuTreeFile
    path: root.cacheDir + "/menu-tree.json"
    atomicWrites: true
    printErrors: false
  }

  FileView {
    id: pendingRoomFile
    path: root.cacheDir + "/pending-room"
    watchChanges: true
    printErrors: false
    onLoaded: {
      var t = String(text() || "").replace(/^\s+|\s+$/g, "")
      if (t) {
        root.pendingOpenAreaId = t
        pendingRoomFile.setText("")
      }
    }
  }

  IpcHandler {
    target: "hearth"

    function ping(): string { return "ok" }
    function status(): string { return root.statusJson() }
    function act(payload: string): string { return root.actJson(payload) }
    function setActive(id: string): string { return root.setActiveId(id) }
    function listInstances(): string { return root.listInstancesJson() }
    function testConnection(payload: string): string { return root.testConnectionJson(payload) }
    function completeOnboard(payload: string): string { return root.completeOnboardJson(payload) }
    function toggleFavorite(payload: string): string { return root.toggleFavoriteJson(payload) }
    function setSelection(payload: string): string { return root.setSelectionJson(payload) }
    function menuSync(): string { return root.menuSyncNow() }
    function addInstance(): string { root.beginAddInstance(); return "ok" }
    function reload(): string { return root.reloadFiles() }
    function openPanel(): string {
      return (root.shell && root.shell.summon && root.shell.summon("hearth", "{}")) ? "ok" : "error"
    }
  }
}
