"""Parse HA Energy prefs and today's statistic changes. No guessed sensors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _add(ids: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in ids:
        ids.append(value)


def parse_prefs(prefs: Any) -> Optional[dict[str, list[str]]]:
    """Return solar/import/export/power statistic ids, or None to hide the strip."""
    if prefs is None:
        return None
    if not isinstance(prefs, dict):
        return None
    sources = prefs.get("energy_sources")
    if not isinstance(sources, list) or len(sources) == 0:
        return None

    solar: list[str] = []
    imports: list[str] = []
    exports: list[str] = []
    power: list[str] = []

    for src in sources:
        if not isinstance(src, dict):
            continue
        kind = src.get("type")
        if kind == "solar":
            _add(solar, src.get("stat_energy_from"))
            _add(power, src.get("stat_rate") or src.get("stat_power"))
        elif kind == "grid":
            for flow in src.get("flow_from") or []:
                if isinstance(flow, dict):
                    _add(imports, flow.get("stat_energy_from"))
                    _add(power, flow.get("stat_rate") or flow.get("stat_power"))
            for flow in src.get("flow_to") or []:
                if isinstance(flow, dict):
                    _add(exports, flow.get("stat_energy_to"))
                    _add(power, flow.get("stat_rate") or flow.get("stat_power"))
            for item in src.get("power") or []:
                if isinstance(item, str):
                    _add(power, item)
                elif isinstance(item, dict):
                    _add(power, item.get("stat_rate") or item.get("stat_power") or item.get("stat_energy_from"))
            _add(imports, src.get("stat_energy_from"))
            _add(exports, src.get("stat_energy_to"))
            _add(power, src.get("stat_rate") or src.get("stat_power"))

    if not solar and not imports and not exports:
        return None
    return {"solar": solar, "import": imports, "export": exports, "power": power}


def sum_changes(result: Any, ids: list[str]) -> Optional[float]:
    if not isinstance(result, dict) or not ids:
        return None
    total = 0.0
    found = False
    for sid in ids:
        rows = result.get(sid)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("change") is None:
                continue
            try:
                total += float(row["change"])
                found = True
            except (TypeError, ValueError):
                continue
    return total if found else None


def sum_delta(result: Any, ids: list[str]) -> Optional[float]:
    """Today = last cumulative `sum` minus first, when `change` is missing."""
    if not isinstance(result, dict) or not ids:
        return None
    total = 0.0
    found = False
    for sid in ids:
        rows = result.get(sid)
        if not isinstance(rows, list) or len(rows) == 0:
            continue
        first = last = None
        for row in rows:
            if not isinstance(row, dict) or row.get("sum") is None:
                continue
            try:
                value = float(row["sum"])
            except (TypeError, ValueError):
                continue
            if first is None:
                first = value
            last = value
        if first is None or last is None:
            continue
        total += last - first
        found = True
    return total if found else None


def today_kwh(result: Any, ids: list[str]) -> Optional[float]:
    change = sum_changes(result, ids)
    if change is not None:
        return change
    return sum_delta(result, ids)


def stats_payload(start_iso: str, ids: list[str]) -> dict[str, Any]:
    """Hour buckets converted to kWh — Envoy lifetime production is stored in MWh."""
    return {
        "type": "recorder/statistics_during_period",
        "start_time": start_iso,
        "period": "hour",
        "types": ["change", "sum"],
        "statistic_ids": ids,
        "units": {"energy": "kWh"},
    }


def local_midnight_iso(time_zone: str, now: Optional[datetime] = None) -> str:
    try:
        tz = ZoneInfo(time_zone) if time_zone else timezone.utc
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    stamp = now.astimezone(tz) if now is not None else datetime.now(tz)
    start = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def live_power_w(states: Any, power_ids: list[str]) -> Optional[float]:
    """First numeric get_states value among collected live-W ids. No name guessing."""
    if not power_ids:
        return None
    by_id = {}
    if isinstance(states, list):
        for st in states:
            if isinstance(st, dict) and st.get("entity_id"):
                by_id[str(st["entity_id"])] = st
    for sid in power_ids:
        st = by_id.get(sid)
        if not st:
            continue
        try:
            value = float(st.get("state"))
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        unit = str((st.get("attributes") or {}).get("unit_of_measurement") or "").lower()
        if unit in ("kw", "kilowatt"):
            value *= 1000.0
        elif unit in ("mw", "megawatt"):
            value *= 1_000_000.0
        return value
    return None


def disabled(reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "reason": reason,
        "solarKwh": None,
        "gridImportKwh": None,
        "gridExportKwh": None,
        "solarPowerW": None,
        "powerIds": [],
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


def pack(groups: dict[str, list[str]], stats: Any, states: Any) -> dict[str, Any]:
    solar = today_kwh(stats, groups["solar"])
    imported = today_kwh(stats, groups["import"])
    exported = today_kwh(stats, groups["export"])
    if solar is None and imported is None and exported is None:
        return disabled("no_statistics")
    power = live_power_w(states, groups["power"])
    return {
        "enabled": True,
        "reason": "",
        "solarKwh": solar,
        "gridImportKwh": imported,
        "gridExportKwh": exported,
        "solarPowerW": power,
        "powerIds": list(groups["power"]),
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }
