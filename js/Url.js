.pragma library

function trim(s) {
  return String(s || "").replace(/^\s+|\s+$/g, "")
}

function isNabuCasa(host) {
  var h = String(host || "").toLowerCase()
  return h === "ui.nabu.casa" || h.slice(-13) === ".ui.nabu.casa"
}

function isIPv6Literal(host) {
  return String(host || "").indexOf(":") !== -1
}

function slug(name) {
  var s = String(name || "home").toLowerCase()
  s = s.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")
  return s || "home"
}

function uniqueInstanceId(base, taken) {
  var id = base
  var n = 2
  var used = taken || []
  function has(x) {
    for (var i = 0; i < used.length; i++) if (used[i] === x) return true
    return false
  }
  while (has(id)) {
    id = base + "-" + n
    n++
  }
  return id
}

function parse(raw) {
  var input = trim(raw)
  var result = {
    ok: false,
    error: "",
    origin: "",
    scheme: "http",
    host: "",
    port: 8123,
    plaintextHttp: true,
    nabuCasa: false,
    hideTlsInsecure: false
  }
  if (!input) {
    result.error = "Enter a Home Assistant address."
    return result
  }
  if (/\s/.test(input)) {
    result.error = "URL cannot contain spaces."
    return result
  }
  if (input.indexOf("/") !== -1 && input.indexOf("://") === -1 && input.charAt(0) !== "[") {
    // Bare host with a path — v0.1 origin-only.
  }

  var scheme = ""
  var rest = input
  var m = input.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//)
  if (m) {
    scheme = m[1].toLowerCase()
    rest = input.slice(m[0].length)
  }
  if (scheme && scheme !== "http" && scheme !== "https") {
    result.error = "Use http or https."
    return result
  }

  var hostport = rest
  var slash = rest.indexOf("/")
  if (slash !== -1) hostport = rest.slice(0, slash)

  var host = ""
  var portStr = ""
  if (hostport.charAt(0) === "[") {
    var close = hostport.indexOf("]")
    if (close < 1) {
      result.error = "IPv6 addresses need brackets, e.g. [fd12::1]:8123."
      return result
    }
    host = hostport.slice(1, close)
    var after = hostport.slice(close + 1)
    if (after && after.charAt(0) === ":") portStr = after.slice(1)
    else if (after) {
      result.error = "IPv6 addresses need brackets, e.g. [fd12::1]:8123."
      return result
    }
  } else if (!scheme && hostport.indexOf(":") !== -1 && hostport.split(":").length > 2) {
    result.error = "IPv6 addresses need brackets, e.g. [fd12::1]:8123."
    return result
  } else {
    var colon = hostport.lastIndexOf(":")
    if (colon !== -1 && hostport.indexOf(":") === colon) {
      host = hostport.slice(0, colon)
      portStr = hostport.slice(colon + 1)
    } else {
      host = hostport
    }
  }

  host = trim(host)
  if (!host) {
    result.error = "Enter a hostname or IP."
    return result
  }

  var port = 0
  if (portStr) {
    if (!/^[0-9]+$/.test(portStr)) {
      result.error = "Port must be a number."
      return result
    }
    port = parseInt(portStr, 10)
    if (port < 1 || port > 65535) {
      result.error = "Port must be between 1 and 65535."
      return result
    }
  }

  if (!scheme) scheme = "http"
  if (!port) port = scheme === "https" ? 443 : 8123

  var hostForUrl = isIPv6Literal(host) ? "[" + host + "]" : host
  var origin = scheme + "://" + hostForUrl
  if (!(scheme === "http" && port === 80) && !(scheme === "https" && port === 443))
    origin += ":" + port

  result.ok = true
  result.origin = origin
  result.scheme = scheme
  result.host = host
  result.port = port
  result.plaintextHttp = scheme === "http"
  result.nabuCasa = isNabuCasa(host)
  result.hideTlsInsecure = result.nabuCasa
  return result
}
