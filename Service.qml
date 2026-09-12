import QtQuick
import Quickshell
import Quickshell.Io
import "js/Url.js" as Url
import "js/Config.js" as Config
import "js/Entities.js" as Entities

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
  property int lightsOn: 0
  property var _cmdQueue: []
  property bool helperReady: false
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
  readonly property string pillLabel: {
    if (!configured) return "Hearth"
    var st = state && state.instances ? state.instances[config.activeInstanceId] : null
    if (st && st.energy && isFinite(Number(st.energy.solarPowerW)) && Number(st.energy.solarPowerW) > 0) {
      var w = Number(st.energy.solarPowerW)
      if (w >= 1000) return (Math.round(w / 100) / 10) + " kW"
      return Math.round(w) + " W"
    }
    if (root.lightsOn > 0) return root.lightsOn + " on"
    return "Hearth"
  }
  readonly property string statusText: configured ? (activeName + " · " + connectionState) : "Hearth — not connected"

  function fileUrlToPath(url) {
    var s = String(url || "")
    if (s.indexOf("file://") === 0) s = s.substring(7)
    return s
  }

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
    pending[id] = cb || null
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
      var cb = root._pending[rid]
      if (!cb && rid !== undefined && rid !== null) cb = root._pending[String(rid)] || root._pending[Number(rid)]
      delete root._pending[rid]
      delete root._pending[String(rid)]
      delete root._pending[Number(rid)]
      if (cb) cb(msg)
      else console.warn("hearth: result with no waiter id=" + rid)
      return
    }
    if (msg.event === "connection") {
      connectionState = String(msg.state || "idle")
      if (msg.haVersion) haVersion = String(msg.haVersion)
      if (msg.locationName) locationName = String(msg.locationName)
      if (msg.state === "connected") lastError = ""
      if (msg.error) lastError = String(msg.error)
      return
    }
    if (msg.event === "log" && msg.level === "error") {
      lastError = String(msg.message || "")
      return
    }
    if (msg.event === "snapshot") {
      snapFile.reload()
      return
    }
    if (msg.event === "state_changed" && msg.entity) {
      root.rooms = Entities.patch(root.rooms, msg.entity)
      root.bumpRooms()
      root.lightsOn = Entities.lightsOnCount(root.rooms)
    }
  }

  function bumpRooms() {
    var next = []
    var list = root.rooms || []
    for (var i = 0; i < list.length; i++) {
      var r = list[i]
      next.push({
        area_id: r.area_id,
        name: r.name,
        count: r.entities ? r.entities.length : (r.count || 0),
        entities: r.entities ? r.entities.slice() : []
      })
    }
    root.rooms = next
  }

  function applySnapshot(raw) {
    var snap
    try { snap = JSON.parse(String(raw || "{}")) } catch (e) { return }
    var built = Entities.build(root.config, snap)
    root.rooms = built.rooms || []
    root.lightsOn = built.lightsOn || 0
  }

  function actOnEntity(entityId, serviceName) {
    var domain = Entities.domainOf(entityId)
    var kind = Entities.kindOf(domain)
    var svc = serviceName || Entities.primaryService(domain, kind)
    if (!svc || !root.config.activeInstanceId) return { ok: false, error: "Nothing to call." }
    if (kind === "toggle") {
      root.rooms = Entities.optimisticToggle(root.rooms, entityId)
      root.bumpRooms()
      root.lightsOn = Entities.lightsOnCount(root.rooms)
    }
    sendCmd({
      cmd: "call",
      instanceId: root.config.activeInstanceId,
      payload: {
        type: "call_service",
        domain: domain,
        service: svc,
        target: { entity_id: String(entityId) }
      }
    }, null)
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
      } else {
        connectionState = "failed"
        lastError = msg && msg.error ? String(msg.error) : "Connect failed."
      }
    })
    pendingInstanceId = ""
    return { ok: true, instanceId: inst.id }
  }

  function cancelOnboard() {
    if (!pendingInstanceId) return
    sendCmd({ cmd: "forget", instanceId: pendingInstanceId }, null)
    pendingInstanceId = ""
    pendingAreas = []
  }

  function refresh() {
    if (!configured) return
    sendCmd({ cmd: "connect", instanceId: config.activeInstanceId }, null)
  }

  function refreshEnergy() {
    if (!configured) return
    sendCmd({ cmd: "energy", instanceId: config.activeInstanceId }, null)
  }

  function writeConfig() {
    configFile.setText(JSON.stringify(config, null, 2) + "\n")
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
    return JSON.stringify(root.actOnEntity(fields.entity_id || fields.entityId, fields.service))
  }

  function setActiveId(id) {
    if (!Config.findInstance(config, id)) return JSON.stringify({ ok: false, error: "Unknown instance." })
    config.activeInstanceId = String(id)
    writeConfig()
    sendCmd({ cmd: "connect", instanceId: String(id) }, null)
    return JSON.stringify({ ok: true })
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
    return JSON.stringify({ ok: false, error: "Favorites land in a later slice." })
  }

  function setSelectionJson(payload) {
    return JSON.stringify({ ok: false, error: "Selection lands in a later slice." })
  }

  function menuSyncNow() {
    return JSON.stringify({ ok: true, skipped: true })
  }

  function reloadFiles() {
    configFile.reload()
    stateFile.reload()
    return "ok"
  }

  Component.onCompleted: {
    mkdir.command = ["mkdir", "-p", "-m", "0700", configDir, stateDir, cacheDir + "/entities"]
    mkdir.running = true
    helper.running = true
  }

  Process {
    id: mkdir
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
        if (line) console.warn("hearth helper: " + line)
      }
    }
    onStarted: {
      root.helperReady = true
      root._restartMs = 1000
      root.flushCmdQueue()
      if (root.configured && root.config.activeInstanceId)
        root.sendCmd({ cmd: "connect", instanceId: root.config.activeInstanceId }, null)
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
    }
    onLoadFailed: {
      root.configLoaded = true
      root.config = Config.emptyConfig()
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
      if (loaded.ok) root.state = loaded.state
    }
    onLoadFailed: root.state = Config.emptyState()
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
    function reload(): string { return root.reloadFiles() }
    function openPanel(): string {
      return (root.shell && root.shell.summon && root.shell.summon("hearth", "{}")) ? "ok" : "error"
    }
  }
}
