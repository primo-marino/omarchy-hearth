import QtQuick
import qs.Commons
import qs.Ui
import "../js/Url.js" as Url

Column {
  id: root
  spacing: Style.space(12)

  property var service: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color urgent: Color.urgent

  property string instanceName: "Home"
  property string urlText: ""
  property string tokenText: ""
  property string usernameText: ""
  property string passwordText: ""
  property string authMethod: "token"
  property bool tlsInsecure: false
  property bool httpAcknowledged: false
  property bool passwordAvailable: false
  property bool probingProviders: false
  property bool testing: false
  property bool testedOk: false
  property string statusMessage: ""
  property string statusKind: ""
  property string haVersion: ""
  property string locationName: ""
  property var pendingAreas: []
  property bool allRooms: false
  property var selectedAreaIds: []
  property bool showDevices: false

  readonly property var parsedUrl: Url.parse(urlText)
  readonly property bool urlOk: parsedUrl.ok === true
  readonly property bool httpNeedsAck: urlOk && parsedUrl.plaintextHttp && !httpAcknowledged
  readonly property bool showTls: urlOk && parsedUrl.scheme === "https" && !parsedUrl.hideTlsInsecure
  readonly property bool hasCredential: authMethod === "token" ? tokenText.length > 0
                                                              : (usernameText.length > 0 && passwordText.length > 0)
  readonly property bool canTest: urlOk && hasCredential && !httpNeedsAck && !testing
  readonly property bool fieldFocused: nameField.activeFocus || urlField.activeFocus || tokenField.activeFocus
                                       || userField.activeFocus || passField.activeFocus

  function reset() {
    instanceName = "Home"
    urlText = ""
    tokenText = ""
    usernameText = ""
    passwordText = ""
    authMethod = "token"
    tlsInsecure = false
    httpAcknowledged = false
    passwordAvailable = false
    probingProviders = false
    testing = false
    testedOk = false
    statusMessage = ""
    statusKind = ""
    haVersion = ""
    locationName = ""
    pendingAreas = []
    allRooms = false
    selectedAreaIds = []
    showDevices = false
  }

  function toggleArea(areaId) {
    var next = []
    var found = false
    for (var i = 0; i < selectedAreaIds.length; i++) {
      if (selectedAreaIds[i] === areaId) {
        found = true
        continue
      }
      next.push(selectedAreaIds[i])
    }
    if (!found) next.push(areaId)
    selectedAreaIds = next
    allRooms = false
  }

  function selectAllRooms() {
    var ids = []
    for (var i = 0; i < pendingAreas.length; i++) ids.push(pendingAreas[i].area_id)
    selectedAreaIds = ids
    allRooms = true
  }

  function applyLoginResult(result) {
    if (!result || result.pending) return
    testTimeout.stop()
    testing = false
    if (!result.ok) {
      testedOk = false
      statusKind = "error"
      statusMessage = result.error || "Connection failed."
      return
    }
    testedOk = true
    statusKind = "ok"
    haVersion = result.haVersion || ""
    locationName = result.locationName || ""
    pendingAreas = result.areas || []
    statusMessage = (locationName || "Home Assistant") + (haVersion ? (" · " + haVersion) : "")
  }

  function test() {
    if (!canTest || !service || !service.testConnection) return
    testing = true
    testedOk = false
    statusKind = ""
    statusMessage = "Testing connection…"
    testTimeout.restart()
    var cred = authMethod === "token" ? tokenText : passwordText
    service.testConnection({
      name: instanceName,
      url: parsedUrl.origin,
      tlsInsecure: showTls ? tlsInsecure : false,
      authMethod: authMethod,
      token: authMethod === "token" ? cred : "",
      username: authMethod === "username" ? usernameText : "",
      password: authMethod === "username" ? cred : ""
    })
    tokenText = ""
    passwordText = ""
  }

  function save() {
    if (!testedOk || !service || !service.completeOnboard) return
    var result = service.completeOnboard({
      name: instanceName,
      url: parsedUrl.origin,
      tlsInsecure: showTls ? tlsInsecure : false,
      plaintextHttp: parsedUrl.plaintextHttp === true,
      httpAcknowledged: httpAcknowledged,
      allRooms: allRooms,
      selectedAreaIds: selectedAreaIds.slice(),
      includeAllEntities: true,
      selectedEntityIds: []
    })
    if (!result || !result.ok) {
      statusKind = "error"
      statusMessage = (result && result.error) ? result.error : "Could not save."
    }
  }

  function cancel() {
    if (service && service.cancelOnboard) service.cancelOnboard()
    reset()
  }

  onUrlTextChanged: {
    passwordAvailable = false
    testedOk = false
    probeDebounce.restart()
  }

  Timer {
    id: probeDebounce
    interval: 400
    repeat: false
    onTriggered: {
      if (!root.parsedUrl.ok) return
      if (!root.service || !root.service.probeProviders) return
      root.probingProviders = true
      root.service.probeProviders(root.parsedUrl.origin, root.showTls ? root.tlsInsecure : false)
    }
  }

  Timer {
    id: testTimeout
    interval: 25000
    repeat: false
    onTriggered: {
      if (!root.testing) return
      root.testing = false
      root.testedOk = false
      root.statusKind = "error"
      root.statusMessage = "Timed out reaching Home Assistant. Check the address, HTTP vs HTTPS, and that port 8123 is open."
    }
  }

  Connections {
    target: root.service
    function onLoginFinished(result) { root.applyLoginResult(result) }
    function onLastLoginResultChanged() { root.applyLoginResult(root.service ? root.service.lastLoginResult : null) }
    function onPasswordAvailableChanged() {
      root.passwordAvailable = !!(root.service && root.service.passwordAvailable)
      root.probingProviders = false
      if (root.authMethod === "username" && !root.passwordAvailable) root.authMethod = "token"
    }
  }

  PanelHero {
    width: parent.width
    title: "Hearth"
    meta: "Connect a Home Assistant"
    foreground: root.foreground
    fontFamily: root.fontFamily
    iconComponent: Component {
      Text {
        textFormat: Text.PlainText
        text: "󰋜"
        color: root.foreground
        font.pixelSize: Style.font.display
      }
    }
  }

  Text {
    width: parent.width
    text: "Name"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }
  TextField {
    id: nameField
    width: parent.width
    text: root.instanceName
    foreground: root.foreground
    onTextChanged: root.instanceName = text
  }

  Text {
    width: parent.width
    text: "Address"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }
  TextField {
    id: urlField
    width: parent.width
    text: root.urlText
    placeholderText: "homeassistant.local:8123"
    foreground: root.foreground
    onTextChanged: root.urlText = text
  }
  Text {
    visible: urlText.length > 0 && !urlOk
    width: parent.width
    text: parsedUrl.error || ""
    color: root.urgent
    wrapMode: Text.WordWrap
    font.family: root.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  ButtonGroup {
    width: parent.width
    foreground: root.foreground
    options: root.passwordAvailable
      ? [{ value: "token", label: "Token" }, { value: "username", label: "Username & password" }]
      : [{ value: "token", label: "Token" }]
    value: root.authMethod
    onChanged: function(v) { root.authMethod = v }
  }

  TextField {
    id: tokenField
    visible: root.authMethod === "token"
    width: parent.width
    password: true
    text: root.tokenText
    placeholderText: "Long-lived access token"
    foreground: root.foreground
    onTextChanged: root.tokenText = text
  }
  TextField {
    id: userField
    visible: root.authMethod === "username"
    width: parent.width
    text: root.usernameText
    placeholderText: "Username"
    foreground: root.foreground
    onTextChanged: root.usernameText = text
  }
  TextField {
    id: passField
    visible: root.authMethod === "username"
    width: parent.width
    password: true
    text: root.passwordText
    placeholderText: "Password"
    foreground: root.foreground
    onTextChanged: root.passwordText = text
  }

  Toggle {
    visible: root.showTls
    width: parent.width
    label: "Allow insecure TLS (this instance)"
    description: "For a local self-signed certificate."
    checked: root.tlsInsecure
    foreground: root.foreground
    onClicked: root.tlsInsecure = !root.tlsInsecure
  }

  Column {
    visible: urlOk && parsedUrl.plaintextHttp
    width: parent.width
    spacing: Style.space(6)
    Text {
      width: parent.width
      text: "This URL is unencrypted HTTP. Tokens will travel in the clear on the path to Home Assistant."
      color: root.urgent
      wrapMode: Text.WordWrap
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
    Toggle {
      width: parent.width
      label: "I understand this is unencrypted"
      checked: root.httpAcknowledged
      foreground: root.foreground
      onClicked: root.httpAcknowledged = !root.httpAcknowledged
    }
  }

  Button {
    width: parent.width
    text: root.testing ? "Testing…" : "Test connection"
    enabled: root.canTest
    foreground: root.foreground
    onClicked: root.test()
  }

  Text {
    visible: statusMessage !== ""
    width: parent.width
    text: statusMessage
    color: statusKind === "error" ? root.urgent : root.dim
    wrapMode: Text.WordWrap
    font.family: root.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Column {
    visible: testedOk
    width: parent.width
    spacing: Style.space(8)

    PanelSectionHeader {
      text: "ROOMS"
      foreground: root.foreground
      fontFamily: root.fontFamily
    }
    Text {
      width: parent.width
      text: pendingAreas.length === 0 ? "No areas on this instance. You can still save and add rooms later in Settings." : "Pick rooms to control. All rooms includes Unassigned."
      color: root.dim
      wrapMode: Text.WordWrap
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
    Button {
      visible: pendingAreas.length > 0
      text: "All rooms"
      selected: root.allRooms
      foreground: root.foreground
      onClicked: root.selectAllRooms()
    }
    Repeater {
      model: pendingAreas
      Toggle {
        required property var modelData
        width: root.width
        label: modelData.name || modelData.area_id
        checked: {
          for (var i = 0; i < root.selectedAreaIds.length; i++)
            if (root.selectedAreaIds[i] === modelData.area_id) return true
          return false
        }
        foreground: root.foreground
        onClicked: root.toggleArea(modelData.area_id)
      }
    }

    Button {
      width: parent.width
      text: "Save"
      enabled: true
      foreground: root.foreground
      onClicked: root.save()
    }
  }
}
