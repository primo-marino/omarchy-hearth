.pragma library

function empty() {
  return {
    enabled: false,
    reason: "",
    solarKwh: null,
    gridImportKwh: null,
    gridExportKwh: null,
    solarPowerW: null,
    powerIds: []
  }
}

function formatKwh(value) {
  if (value === null || value === undefined || value === "") return ""
  var n = Number(value)
  if (!isFinite(n)) return ""
  var abs = Math.abs(n)
  if (abs >= 10) return (Math.round(n * 10) / 10) + " kWh"
  if (abs >= 1) return (Math.round(n * 10) / 10) + " kWh"
  return (Math.round(n * 100) / 100) + " kWh"
}

function toWatts(state, attrs) {
  var n = Number(state)
  if (!isFinite(n)) return NaN
  var unit = String(attrs && attrs.unit_of_measurement ? attrs.unit_of_measurement : "").toLowerCase()
  if (unit === "kw" || unit === "kilowatt") return n * 1000
  if (unit === "mw" || unit === "megawatt") return n * 1000000
  return n
}

function formatPower(value) {
  var n = Number(value)
  if (!isFinite(n) || n <= 0) return ""
  if (n >= 1000) return (Math.round(n / 100) / 10) + " kW"
  return Math.round(n) + " W"
}

function fromHelper(data) {
  if (!data || data.enabled !== true) {
    var off = empty()
    off.reason = data && data.reason ? String(data.reason) : "hidden"
    off.fetchedAt = data && data.fetchedAt ? String(data.fetchedAt) : ""
    return off
  }
  return {
    enabled: true,
    reason: "",
    solarKwh: data.solarKwh,
    gridImportKwh: data.gridImportKwh,
    gridExportKwh: data.gridExportKwh,
    solarPowerW: data.solarPowerW,
    powerIds: data.powerIds || [],
    fetchedAt: data.fetchedAt || ""
  }
}

function isPowerEntity(energy, entityId) {
  if (!energy || !energy.powerIds) return false
  var eid = String(entityId || "")
  for (var i = 0; i < energy.powerIds.length; i++)
    if (String(energy.powerIds[i]) === eid) return true
  return false
}
