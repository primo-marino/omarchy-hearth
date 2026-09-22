#!/usr/bin/env python3
"""Hearth Home Assistant JSON-lines helper. No third-party packages."""

from __future__ import annotations

import errno
import json
import os
import queue
from datetime import datetime, timezone
import socket
import ssl
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import re
from typing import Any, Optional

from rfc6455 import MAX_FRAME, WebSocketClosed, WebSocketError, connect as ws_connect
import energy as energy_lib

SERVICE_DOMAINS = (
    "vacuum",
    "remote",
    "humidifier",
    "water_heater",
    "lawn_mower",
    "alarm_control_panel",
    "climate",
    "media_player",
)


def slim_services(result: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not isinstance(result, dict):
        return out
    for domain in SERVICE_DOMAINS:
        spec = result.get(domain)
        if not isinstance(spec, dict):
            continue
        svcs = spec.get("services")
        if isinstance(svcs, dict):
            out[domain] = list(svcs.keys())
    return out

HOME = os.environ.get("HOME", "")
CONFIG_DIR = os.path.join(HOME, ".config", "omarchy", "hearth")
STATE_DIR = os.path.join(HOME, ".local", "state", "omarchy", "hearth")
CACHE_DIR = os.path.join(HOME, ".cache", "omarchy", "hearth", "entities")
SECRETS_PATH = os.path.join(CONFIG_DIR, "secrets.json")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
JSON_LINE_CAP = 256 * 1024
HTTP_BODY_CAP = 2 * 1024 * 1024
ENTITY_CAP = 5000
LLAT_LIFESPAN_DAYS = 3650
ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
INSTANCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ALLOWED_DOMAINS = frozenset({
    "light", "switch", "fan", "input_boolean", "siren",
    "scene", "script", "button", "automation", "input_button",
    "cover", "valve", "lock",
    "climate", "media_player",
    "vacuum", "remote", "humidifier", "water_heater", "lawn_mower",
    "alarm_control_panel",
})
ATTR_KEEP = (
    "friendly_name",
    "brightness",
    "brightness_pct",
    "supported_color_modes",
    "color_mode",
    "percentage",
    "percentage_step",
    "preset_modes",
    "preset_mode",
    "supported_features",
    "temperature",
    "target_temp",
    "current_temperature",
    "target_temp_step",
    "min_temp",
    "max_temp",
    "temperature_unit",
    "hvac_modes",
    "hvac_mode",
    "volume_level",
    "volume_step",
    "humidity",
    "current_humidity",
    "min_humidity",
    "max_humidity",
    "code_arm_required",
    "code_disarm_required",
    "unit_of_measurement",
)

lock = threading.Lock()
emit_lock = threading.Lock()
sessions: dict[str, "HaSession"] = {}
stdin_closed = False


def log(level: str, message: str) -> None:
    emit({"event": "log", "level": level, "message": message})


def emit(obj: dict[str, Any]) -> None:
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    if len(line) > JSON_LINE_CAP:
        # Avoid recursion through log() if this is already a log event.
        if obj.get("event") != "log":
            log("warn", "dropping oversize stdout event %s" % obj.get("event"))
        return
    with emit_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in ("accesstoken", "access_token", "refreshtoken", "refresh_token",
                      "password", "token", "authorization"):
                continue
            out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def valid_instance_id(instance_id: str) -> bool:
    if not INSTANCE_RE.match(instance_id or ""):
        return False
    return "/" not in instance_id and "\\" not in instance_id and ".." not in instance_id


def service_for_state(entity_id: str, state: str) -> str:
    """Pick lock/cover/valve service from HA state. Empty if unknown."""
    domain = str(entity_id or "").split(".", 1)[0]
    st = str(state or "")
    if domain == "lock":
        if not st:
            return ""
        return "lock" if st in ("unlocked", "unlocking") else "unlock"
    if domain == "cover":
        if not st:
            return ""
        return "close_cover" if st in ("open", "opening") else "open_cover"
    if domain == "valve":
        if not st:
            return ""
        return "close_valve" if st in ("open", "opening") else "open_valve"
    return ""


FLOW_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def valid_origin(origin: str) -> bool:
    """http(s) origin only. No userinfo, path, query, or control characters."""
    if not origin or any(ord(ch) < 33 or ch in "\\" for ch in origin):
        return False
    parsed = urllib.parse.urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.username or parsed.password or "@" in origin:
        return False
    if not parsed.hostname:
        return False
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False
    return True


def safe_flow_id(value: Any) -> str:
    text = str(value or "")
    if not FLOW_ID_RE.match(text):
        raise RuntimeError("login_flow failed")
    return text


def registry_hidden(reg: Any) -> bool:
    if not isinstance(reg, dict):
        return False
    if reg.get("disabled_by") or reg.get("hidden_by"):
        return True
    return reg.get("entity_category") in ("config", "diagnostic")


def filter_actionable_states(states: Any, entities: Any, cap: int = ENTITY_CAP) -> tuple[list, list]:
    """Hide-filters first, then cap. Sensors and other non-actionable domains drop out."""
    regs: dict[str, dict[str, Any]] = {}
    if isinstance(entities, list):
        for ent in entities:
            if isinstance(ent, dict) and ent.get("entity_id"):
                regs[str(ent["entity_id"])] = ent
    out_states: list[dict[str, Any]] = []
    if not isinstance(states, list):
        return [], []
    for st in states:
        if not isinstance(st, dict):
            continue
        eid = str(st.get("entity_id") or "")
        if not ENTITY_RE.match(eid):
            continue
        domain = eid.split(".", 1)[0]
        if domain not in ALLOWED_DOMAINS:
            continue
        if registry_hidden(regs.get(eid)):
            continue
        out_states.append(st)
        if len(out_states) >= cap:
            break
    keep = {str(s.get("entity_id")) for s in out_states}
    out_regs = [regs[k] for k in keep if k in regs]
    return out_states, out_regs


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def read_capped(fp, cap: int = HTTP_BODY_CAP) -> bytes:
    if fp is None:
        return b""
    data = fp.read(cap + 1)
    if data is None:
        return b""
    if len(data) > cap:
        raise RuntimeError("HTTP response too large")
    return data


def ensure_dirs() -> None:
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    os.makedirs(CACHE_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    if os.path.isfile(SECRETS_PATH):
        try:
            os.chmod(SECRETS_PATH, 0o600)
        except OSError:
            pass


def atomic_write(path: str, data: str, mode: int) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, mode)


def read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError):
        return default


def load_secrets() -> dict[str, Any]:
    data = read_json(SECRETS_PATH, {"version": 1, "instances": {}})
    if not isinstance(data, dict):
        data = {"version": 1, "instances": {}}
    data.setdefault("version", 1)
    data.setdefault("instances", {})
    return data


def write_secrets(data: dict[str, Any]) -> None:
    atomic_write(SECRETS_PATH, json.dumps(data, indent=2) + "\n", 0o600)


def load_config() -> dict[str, Any]:
    data = read_json(CONFIG_PATH, {"version": 1, "instances": [], "activeInstanceId": ""})
    if not isinstance(data, dict):
        data = {"version": 1, "instances": [], "activeInstanceId": ""}
    data.setdefault("instances", [])
    return data


def secret_for(instance_id: str) -> Optional[dict[str, Any]]:
    inst = load_secrets().get("instances", {}).get(instance_id)
    return inst if isinstance(inst, dict) else None


def put_secret(instance_id: str, rec: dict[str, Any]) -> None:
    stored = dict(rec)
    stored.setdefault("writtenAt", time.time())
    data = load_secrets()
    data.setdefault("instances", {})[instance_id] = stored
    write_secrets(data)


def delete_secret(instance_id: str) -> None:
    data = load_secrets()
    inst = data.get("instances", {})
    if instance_id in inst:
        del inst[instance_id]
        write_secrets(data)


def sweep_orphans() -> None:
    cfg = load_config()
    keep = {str(i.get("id")) for i in cfg.get("instances", []) if i and i.get("id")}
    data = load_secrets()
    inst = data.get("instances", {})
    now = time.time()
    dropped = []
    for k in list(inst.keys()):
        if k in keep:
            continue
        rec = inst.get(k)
        written = rec.get("writtenAt") if isinstance(rec, dict) else None
        # Keep a just-tested token until Save writes config.json.
        if isinstance(written, (int, float)) and now - float(written) < 1800:
            continue
        dropped.append(k)
    if not dropped:
        return
    for k in dropped:
        del inst[k]
        log("info", "hearth: dropped orphan secret id %s" % k)
    write_secrets(data)


def slim_entity(entity: dict[str, Any]) -> dict[str, Any]:
    attrs = entity.get("attributes") or {}
    slim = {}
    if isinstance(attrs, dict):
        for key in ATTR_KEEP:
            if key in attrs:
                slim[key] = attrs[key]
    return {
        "entity_id": entity.get("entity_id"),
        "state": entity.get("state"),
        "attributes": slim,
    }


def safe_service_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if not SLUG_RE.match(str(key)):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value
        elif isinstance(value, list) and all(isinstance(x, (str, int, float, bool)) or x is None for x in value):
            out[str(key)] = value
    return out


def sanitize_call_payload(payload: Any) -> Optional[dict[str, Any]]:
    """Only authenticated call_service for one entity_id. No other WS types."""
    if not isinstance(payload, dict):
        return None
    if str(payload.get("type") or "") != "call_service":
        return None
    domain = str(payload.get("domain") or "")
    service = str(payload.get("service") or "")
    if not SLUG_RE.match(domain) or not SLUG_RE.match(service):
        return None
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    entity_id = str((target or {}).get("entity_id") or payload.get("entity_id") or "")
    if not ENTITY_RE.match(entity_id):
        return None
    entity_domain = entity_id.split(".", 1)[0]
    if domain != entity_domain or domain not in ALLOWED_DOMAINS:
        return None
    clean: dict[str, Any] = {
        "type": "call_service",
        "domain": domain,
        "service": service,
        "target": {"entity_id": entity_id},
    }
    data = safe_service_data(payload.get("service_data"))
    if data:
        clean["service_data"] = data
    return clean


def ssl_context(tls_insecure: bool) -> Optional[ssl.SSLContext]:
    if not tls_insecure:
        return ssl.create_default_context()
    ctx = ssl._create_unverified_context()
    return ctx


def http_json(method: str, url: str, tls_insecure: bool = False, headers: Optional[dict] = None,
              body: Any = None, form: Optional[dict] = None, timeout: float = 15.0) -> tuple[int, Any]:
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    ctx = ssl_context(tls_insecure) if url.startswith("https:") else None
    handlers: list[Any] = [NoRedirectHandler()]
    if ctx is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = read_capped(resp)
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        try:
            raw = read_capped(e) if e.fp else b""
            code = e.code
        finally:
            try:
                e.close()
            except Exception:
                pass
    except urllib.error.URLError as e:
        raise RuntimeError("connection failed: %s" % e.reason) from e
    text = raw.decode("utf-8", "replace") if raw else ""
    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = text
    return code, parsed


def origin_to_ws(origin: str) -> str:
    if origin.startswith("https://"):
        return "wss://" + origin[len("https://"):] + "/api/websocket"
    if origin.startswith("http://"):
        return "ws://" + origin[len("http://"):] + "/api/websocket"
    raise RuntimeError("bad origin")


def providers_list(body: Any) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and isinstance(body.get("providers"), list):
        return body["providers"]
    return []


def has_homeassistant_provider(body: Any) -> bool:
    for p in providers_list(body):
        if isinstance(p, dict) and p.get("type") == "homeassistant":
            return True
        if isinstance(p, (list, tuple)) and p and p[0] == "homeassistant":
            return True
    return False


def homeassistant_handler(body: Any) -> Optional[list]:
    for p in providers_list(body):
        if isinstance(p, dict) and p.get("type") == "homeassistant":
            return ["homeassistant", p.get("id")]
        if isinstance(p, (list, tuple)) and p and p[0] == "homeassistant":
            return [p[0], p[1] if len(p) > 1 else None]
    return None


def client_id_for(origin: str) -> str:
    return origin.rstrip("/") + "/"


def fetch_areas_via_ws(ws, next_id) -> list[dict[str, str]]:
    msg_id = next_id()
    ws.send_text(json.dumps({"id": msg_id, "type": "config/area_registry/list"}))
    while True:
        raw = ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            if not msg.get("success"):
                return []
            areas = []
            for a in msg.get("result") or []:
                if not isinstance(a, dict):
                    continue
                areas.append({"area_id": a.get("area_id") or a.get("id") or "", "name": a.get("name") or ""})
            areas.sort(key=lambda x: x["name"].lower())
            return areas


def ws_auth(origin: str, token: str, tls_insecure: bool):
    ws = ws_connect(origin_to_ws(origin), tls_insecure=tls_insecure, timeout=20.0)
    hello = json.loads(ws.recv())
    if hello.get("type") != "auth_required":
        ws.close()
        raise RuntimeError("expected auth_required")
    ws.send_text(json.dumps({"type": "auth", "access_token": token}))
    reply = json.loads(ws.recv())
    if reply.get("type") == "auth_invalid":
        ws.close()
        raise RuntimeError(reply.get("message") or "auth_invalid")
    if reply.get("type") != "auth_ok":
        ws.close()
        raise RuntimeError("expected auth_ok")
    return ws, reply.get("ha_version") or ""


def ws_get_config(ws, next_id) -> dict[str, Any]:
    msg_id = next_id()
    ws.send_text(json.dumps({"id": msg_id, "type": "get_config"}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == msg_id:
            if not msg.get("success"):
                return {}
            return msg.get("result") or {}


def ws_call(ws, next_id, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    msg_id = next_id()
    body = dict(payload)
    body["id"] = msg_id
    ws.sock.settimeout(timeout)
    ws.send_text(json.dumps(body))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == msg_id:
            return msg


def rest_states(origin: str, token: str, tls_insecure: bool, entity_ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    headers = {"Authorization": "Bearer " + token}
    for eid in entity_ids:
        if not eid:
            continue
        url = origin.rstrip("/") + "/api/states/" + urllib.parse.quote(eid, safe="._")
        try:
            code, body = http_json("GET", url, tls_insecure=tls_insecure, headers=headers, timeout=8.0)
        except Exception:
            continue
        if code == 200 and isinstance(body, dict):
            out.append(body)
    return out


def mint_llat(ws, next_id) -> Optional[str]:
    msg_id = next_id()
    ws.send_text(json.dumps({
        "id": msg_id,
        "type": "auth/long_lived_access_token",
        "client_name": "Hearth",
        "lifespan": LLAT_LIFESPAN_DAYS,
    }))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == msg_id:
            if msg.get("success") and isinstance(msg.get("result"), str):
                return msg["result"]
            return None


class HaSession:
    def __init__(self, instance_id: str, origin: str, tls_insecure: bool, token: str):
        self.instance_id = instance_id
        self.origin = origin
        self.tls_insecure = tls_insecure
        self.token = token
        self._refresh_tried = False
        self.ws = None
        self.msg_id = 1
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.ha_version = ""
        self.time_zone = ""
        self.last_states: list[Any] = []
        self.last_services: dict[str, list[str]] = {}
        self._need_snapshot = False
        self._snap_at = 0.0
        self.outbox: queue.Queue = queue.Queue()
        self._send_failed = None
        self.waiters: dict[int, tuple[threading.Event, dict[str, Any]]] = {}
        self._id_lock = threading.Lock()

    def _is_current(self) -> bool:
        with lock:
            return sessions.get(self.instance_id) is self

    def next_id(self) -> int:
        with self._id_lock:
            self.msg_id += 1
            return self.msg_id

    def rpc(self, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
        if self.stop.is_set() or not self.ws:
            return {"success": False, "error": {"code": "not_connected"}}
        mid = self.next_id()
        ev = threading.Event()
        holder: dict[str, Any] = {}
        with self._id_lock:
            self.waiters[mid] = (ev, holder)
        body = dict(payload)
        body["id"] = mid
        self.outbox.put(body)
        if not ev.wait(timeout):
            with self._id_lock:
                self.waiters.pop(mid, None)
            return {"success": False, "error": {"code": "timeout"}}
        return holder.get("msg") or {"success": False, "error": {"code": "empty"}}

    def fetch_energy(self) -> dict[str, Any]:
        # Own short-lived WS so a 1 MiB get_states snapshot cannot starve prefs/stats.
        ws = None
        try:
            ws, _ver = ws_auth(self.origin, self.token, self.tls_insecure)
            n = [1]

            def next_id() -> int:
                n[0] += 1
                return n[0]

            cfg = ws_get_config(ws, next_id)
            tz = str(cfg.get("time_zone") or self.time_zone or "")
            prefs_msg = ws_call(ws, next_id, {"type": "energy/get_prefs"})
            if not prefs_msg.get("success"):
                err = prefs_msg.get("error") or {}
                code = err.get("code") if isinstance(err, dict) else "prefs_failed"
                return energy_lib.disabled(str(code or "prefs_failed"))
            groups = energy_lib.parse_prefs(prefs_msg.get("result"))
            if not groups:
                return energy_lib.disabled("empty_prefs")
            ids = groups["solar"] + groups["import"] + groups["export"]
            if not ids:
                return energy_lib.disabled("no_ids")
            stats_msg = ws_call(ws, next_id, energy_lib.stats_payload(
                energy_lib.local_midnight_iso(tz), ids))
            if not stats_msg.get("success"):
                err = stats_msg.get("error") or {}
                code = err.get("code") if isinstance(err, dict) else "stats_failed"
                return energy_lib.disabled(str(code or "stats_failed"))
            states = self.last_states
            if groups["power"]:
                live = rest_states(self.origin, self.token, self.tls_insecure, groups["power"])
                if live:
                    states = live
            return energy_lib.pack(groups, stats_msg.get("result") or {}, states)
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="hearth-%s" % self.instance_id, daemon=True)
        self.thread.start()

    def disconnect(self) -> None:
        self.stop.set()
        with self._id_lock:
            pending = list(self.waiters.items())
            self.waiters.clear()
        for _mid, (ev, holder) in pending:
            holder["msg"] = {"success": False, "error": {"code": "disconnected"}}
            ev.set()
        ws = self.ws
        self.ws = None
        if ws:
            try:
                ws.close()
            except OSError:
                pass

    def call(self, payload: dict[str, Any]) -> None:
        self.outbox.put(payload)

    def _flush_outbox(self) -> None:
        if not self.ws:
            return
        while True:
            try:
                payload = self.outbox.get_nowait()
            except queue.Empty:
                return
            body = dict(payload)
            if "id" not in body:
                body["id"] = self.next_id()
            try:
                self.ws.send_text(json.dumps(body))
            except OSError as e:
                self._send_failed = e
                return

    def _run(self) -> None:
        backoff = 1
        while not self.stop.is_set():
            try:
                self.ws, self.ha_version = ws_auth(self.origin, self.token, self.tls_insecure)
                if self.stop.is_set() or not self._is_current():
                    ws = self.ws
                    self.ws = None
                    if ws:
                        try:
                            ws.close()
                        except OSError:
                            pass
                    break
                backoff = 1
                cfg = ws_get_config(self.ws, self.next_id)
                if self.stop.is_set() or not self._is_current():
                    ws = self.ws
                    self.ws = None
                    if ws:
                        try:
                            ws.close()
                        except OSError:
                            pass
                    break
                self.time_zone = str(cfg.get("time_zone") or "")
                emit({
                    "event": "connection",
                    "instanceId": self.instance_id,
                    "state": "connected",
                    "haVersion": self.ha_version or cfg.get("version") or "",
                    "locationName": cfg.get("location_name") or "",
                    "timeZone": self.time_zone,
                })
                self._snapshot(include_services=True)
                for ev in ("state_changed", "entity_registry_updated", "area_registry_updated", "device_registry_updated"):
                    self.ws.send_text(json.dumps({
                        "id": self.next_id(),
                        "type": "subscribe_events",
                        "event_type": ev,
                    }))
                ping_at = time.monotonic() + 10
                alive_until = time.monotonic() + 25
                while not self.stop.is_set():
                    self.ws.sock.settimeout(0.2)
                    try:
                        self._flush_outbox()
                        if self._send_failed:
                            err = self._send_failed
                            self._send_failed = None
                            raise WebSocketClosed(1006, "send failed: %s" % err) from err
                        if not self.ws:
                            break
                        raw = self.ws.recv()
                    except TimeoutError:
                        if self.stop.is_set() or not self.ws:
                            break
                        now = time.monotonic()
                        if now >= alive_until:
                            raise WebSocketClosed(1006, "Home Assistant not responding")
                        self._flush_outbox()
                        if self._send_failed:
                            err = self._send_failed
                            self._send_failed = None
                            raise WebSocketClosed(1006, "send failed: %s" % err) from err
                        if self._need_snapshot and now >= self._snap_at:
                            self._need_snapshot = False
                            self._snapshot(include_services=False, reason="registry")
                            alive_until = time.monotonic() + 25
                        if now >= ping_at:
                            self.call({"type": "ping"})
                            self._flush_outbox()
                            ping_at = now + 10
                        continue
                    except OSError as e:
                        if self.stop.is_set():
                            break
                        raise WebSocketClosed(1006, "socket errno %s" % e.errno) from e
                    msg = json.loads(raw)
                    alive_until = time.monotonic() + 25
                    mid = msg.get("id")
                    waiter = None
                    if mid is not None:
                        with self._id_lock:
                            waiter = self.waiters.pop(mid, None)
                    if waiter:
                        waiter[1]["msg"] = msg
                        waiter[0].set()
                        continue
                    if msg.get("type") == "event":
                        et = (msg.get("event") or {}).get("event_type")
                        if et == "state_changed":
                            entity = ((msg.get("event") or {}).get("data") or {}).get("new_state")
                            if entity:
                                emit({
                                    "event": "state_changed",
                                    "instanceId": self.instance_id,
                                    "entity": slim_entity(entity),
                                })
                        elif et in ("entity_registry_updated", "area_registry_updated", "device_registry_updated"):
                            self._need_snapshot = True
                            self._snap_at = time.monotonic() + 2.0
                    elif msg.get("type") == "pong":
                        ping_at = time.monotonic() + 10
                        alive_until = time.monotonic() + 25
            except WebSocketClosed as e:
                if self.stop.is_set() or not self._is_current():
                    break
                emit({"event": "connection", "instanceId": self.instance_id, "state": "reconnecting",
                      "error": str(e)})
            except OSError as e:
                if self.stop.is_set() or not self._is_current():
                    break
                emit({"event": "connection", "instanceId": self.instance_id, "state": "reconnecting",
                      "error": str(e)})
            except Exception as e:
                if self.stop.is_set() or not self._is_current():
                    break
                if (not self._refresh_tried) and "auth_invalid" in str(e).lower():
                    self._refresh_tried = True
                    fresh = secret_for(self.instance_id) or {}
                    fresh["kind"] = fresh.get("kind") or "refresh"
                    fresh["accessExpiresAt"] = ""
                    updated = refresh_secret(self.instance_id, fresh, self.origin, self.tls_insecure)
                    new_token = str(updated.get("accessToken") or "")
                    if new_token and new_token != self.token:
                        self.token = new_token
                        continue
                emit({"event": "connection", "instanceId": self.instance_id, "state": "reconnecting",
                      "error": str(e)})
            if self.stop.is_set() or not self._is_current():
                break
            time.sleep(backoff)
            backoff = min(30, backoff * 2 if backoff >= 2 else (2 if backoff == 1 else 5))
        if self._is_current():
            emit({"event": "connection", "instanceId": self.instance_id, "state": "disconnected"})

    def _set_sock_timeout(self, seconds: float) -> None:
        if not self.ws or not getattr(self.ws, "sock", None):
            return
        try:
            self.ws.sock.settimeout(seconds)
        except OSError:
            pass

    def _snapshot(self, include_services: bool = True, reason: str = "connect") -> None:
        if not self.ws:
            return
        # get_states is ~1 MiB; the idle loop uses 0.2s and would drop the socket.
        self._set_sock_timeout(30.0)
        try:
            self._snapshot_body(include_services, reason)
        finally:
            self._set_sock_timeout(0.2)

    def _snapshot_body(self, include_services: bool, reason: str) -> None:
        areas = []
        devices = []
        entities = []
        states = []
        services: dict[str, list[str]] = dict(self.last_services)
        types = [
            ("config/area_registry/list", "areas"),
            ("config/device_registry/list", "devices"),
            ("config/entity_registry/list", "entities"),
            ("get_states", "states"),
        ]
        if include_services:
            types.append(("get_services", "services"))
        for typ, dest in types:
            mid = self.next_id()
            self.ws.send_text(json.dumps({"id": mid, "type": typ}))
            while True:
                self._flush_outbox()
                msg = json.loads(self.ws.recv())
                got = msg.get("id")
                if got != mid:
                    waiter = None
                    if got is not None:
                        with self._id_lock:
                            waiter = self.waiters.pop(got, None)
                    if waiter:
                        waiter[1]["msg"] = msg
                        waiter[0].set()
                    continue
                if got == mid:
                    if dest == "areas":
                        areas = msg.get("result") or []
                    elif dest == "devices":
                        devices = msg.get("result") or []
                    elif dest == "entities":
                        entities = msg.get("result") or []
                    elif dest == "services":
                        services = slim_services(msg.get("result") or {})
                    else:
                        states = msg.get("result") or []
                    break
        self.last_states = states if isinstance(states, list) else []
        self.last_services = services if isinstance(services, dict) else {}
        cached_states, cached_entities = filter_actionable_states(states, entities)
        path = os.path.join(CACHE_DIR, "%s.json" % self.instance_id)
        fetched = datetime.now(timezone.utc).isoformat()
        payload = {
            "instanceId": self.instance_id,
            "fetchedAt": fetched,
            "areas": areas,
            "devices": devices,
            "entities": cached_entities,
            "states": cached_states,
            "services": services,
        }
        atomic_write(path, json.dumps(payload), 0o600)
        emit({
            "event": "snapshot",
            "instanceId": self.instance_id,
            "path": path,
            "fetchedAt": fetched,
            "reason": reason,
            "entityCount": len(cached_states),
            "areaCount": len(areas),
        })
        # extra registry subscriptions happen once after first snapshot in _run


def cmd_providers(cmd: dict[str, Any]) -> dict[str, Any]:
    origin = str(cmd.get("url") or "")
    if not valid_origin(origin):
        return {"ok": True, "data": {"passwordAvailable": False}}
    tls = bool(cmd.get("tlsInsecure"))
    try:
        code, body = http_json("GET", origin.rstrip("/") + "/auth/providers", tls_insecure=tls)
    except Exception:
        return {"ok": True, "data": {"passwordAvailable": False}}
    if code >= 400 or body is None:
        return {"ok": True, "data": {"passwordAvailable": False}}
    return {"ok": True, "data": {"passwordAvailable": has_homeassistant_provider(body)}}


def login_with_token(origin: str, token: str, tls_insecure: bool) -> dict[str, Any]:
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    code, body = http_json("GET", origin.rstrip("/") + "/api/", tls_insecure=tls_insecure, headers=headers)
    if code == 401:
        raise RuntimeError("Token was rejected. Create a new long-lived token in your HA profile.")
    if code != 200:
        raise RuntimeError("Home Assistant returned HTTP %s" % code)
    ws, version = ws_auth(origin, token, tls_insecure)
    try:
        cfg = ws_get_config(ws, lambda: 1)
        areas = fetch_areas_via_ws(ws, _counter(1))
        location = cfg.get("location_name") or ""
        version = version or cfg.get("version") or ""
    finally:
        ws.close()
    return {"kind": "llat", "haVersion": version, "locationName": location, "areas": areas}


def _counter(start: int):
    n = [start]

    def next_id():
        n[0] += 1
        return n[0]

    return next_id


def login_with_password(origin: str, username: str, password: str, tls_insecure: bool) -> dict[str, Any]:
    code, body = http_json("GET", origin.rstrip("/") + "/auth/providers", tls_insecure=tls_insecure)
    handler = homeassistant_handler(body) if code < 400 else None
    if not handler:
        raise RuntimeError("This instance does not offer username and password. Paste a long-lived token instead.")
    cid = client_id_for(origin)
    code, flow = http_json(
        "POST",
        origin.rstrip("/") + "/auth/login_flow",
        tls_insecure=tls_insecure,
        body={"client_id": cid, "handler": handler, "redirect_uri": cid},
    )
    if code == 400:
        raise RuntimeError(
            "Home Assistant rejected this URL as an OAuth client (public IPs are not allowed). "
            "Paste a long-lived token instead."
        )
    if not isinstance(flow, dict) or not flow.get("flow_id"):
        raise RuntimeError("login_flow failed (HTTP %s)" % code)
    if flow.get("type") == "form" and flow.get("step_id") not in (None, "init"):
        raise RuntimeError("mfa_required")
    flow_id = safe_flow_id(flow.get("flow_id"))
    code, step = http_json(
        "POST",
        origin.rstrip("/") + "/auth/login_flow/" + urllib.parse.quote(flow_id, safe=""),
        tls_insecure=tls_insecure,
        body={"client_id": cid, "username": username, "password": password},
    )
    if isinstance(step, dict) and step.get("type") == "form" and step.get("step_id") != "init":
        raise RuntimeError("mfa_required")
    if not isinstance(step, dict) or step.get("type") != "create_entry" or not step.get("result"):
        raise RuntimeError("Username or password was not accepted.")
    auth_code = step["result"]
    code, token_body = http_json(
        "POST",
        origin.rstrip("/") + "/auth/token",
        tls_insecure=tls_insecure,
        form={"grant_type": "authorization_code", "code": auth_code, "client_id": cid},
    )
    if not isinstance(token_body, dict) or not token_body.get("access_token"):
        raise RuntimeError("Could not exchange the login code for a token.")
    access = token_body["access_token"]
    refresh = token_body.get("refresh_token")
    ws, version = ws_auth(origin, access, tls_insecure)
    kind = "refresh"
    stored_token = access
    try:
        llat = mint_llat(ws, _counter(1))
        if llat:
            kind = "llat"
            stored_token = llat
        cfg = ws_get_config(ws, _counter(10))
        areas = fetch_areas_via_ws(ws, _counter(20))
        location = cfg.get("location_name") or ""
        version = version or cfg.get("version") or ""
    finally:
        ws.close()
    rec = {"kind": kind, "accessToken": stored_token}
    if kind == "refresh":
        rec["refreshToken"] = refresh
        rec["clientId"] = cid
        if token_body.get("expires_in"):
            rec["accessExpiresAt"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(token_body["expires_in"]))
            )
    return {"kind": kind, "haVersion": version, "locationName": location, "areas": areas, "_secret": rec}


def cmd_login(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    origin = str(cmd.get("url") or "")
    tls = bool(cmd.get("tlsInsecure"))
    if not valid_instance_id(instance_id):
        return {"ok": False, "error": "login requires instanceId"}
    if not valid_origin(origin):
        return {"ok": False, "error": "login requires url"}
    try:
        if cmd.get("token"):
            info = login_with_token(origin, str(cmd["token"]), tls)
            put_secret(instance_id, {"kind": "llat", "accessToken": str(cmd["token"])})
        elif cmd.get("username") and cmd.get("password"):
            info = login_with_password(origin, str(cmd["username"]), str(cmd["password"]), tls)
            rec = info.pop("_secret")
            put_secret(instance_id, rec)
        else:
            return {"ok": False, "error": "Provide a token or a username and password."}
    except RuntimeError as e:
        msg = str(e)
        if msg == "mfa_required":
            msg = "This account needs MFA. Create a long-lived token in your HA profile and paste it."
        return {"ok": False, "error": msg}
    return {
        "ok": True,
        "data": {
            "instanceId": instance_id,
            "kind": info["kind"],
            "hasToken": True,
            "haVersion": info.get("haVersion") or "",
            "locationName": info.get("locationName") or "",
            "areas": info.get("areas") or [],
        },
    }


def access_is_stale(rec: dict[str, Any]) -> bool:
    stamp = rec.get("accessExpiresAt")
    if not stamp:
        return rec.get("kind") == "refresh"
    try:
        exp = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    return exp.timestamp() <= time.time() + 60


def refresh_secret(instance_id: str, rec: dict[str, Any], origin: str, tls: bool) -> dict[str, Any]:
    """Exchange a stored refresh token when the access token is missing or near expiry."""
    if rec.get("kind") != "refresh":
        return rec
    if not rec.get("refreshToken") or not rec.get("clientId"):
        return rec
    if rec.get("accessToken") and not access_is_stale(rec):
        return rec
    code, body = http_json(
        "POST",
        origin.rstrip("/") + "/auth/token",
        tls_insecure=tls,
        form={
            "grant_type": "refresh_token",
            "refresh_token": str(rec["refreshToken"]),
            "client_id": str(rec["clientId"]),
        },
    )
    if code >= 400 or not isinstance(body, dict) or not body.get("access_token"):
        return rec
    updated = dict(rec)
    updated["accessToken"] = str(body["access_token"])
    if body.get("refresh_token"):
        updated["refreshToken"] = str(body["refresh_token"])
    if body.get("expires_in"):
        try:
            updated["accessExpiresAt"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(body["expires_in"]))
            )
        except (TypeError, ValueError):
            pass
    put_secret(instance_id, updated)
    return updated


def cmd_connect(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    if not valid_instance_id(instance_id):
        return {"ok": False, "error": "connect requires instanceId"}
    rec = secret_for(instance_id) or {}
    cfg = load_config()
    inst = None
    for row in cfg.get("instances") or []:
        if row and str(row.get("id")) == instance_id:
            inst = row
            break
    origin = str(cmd.get("url") or (inst or {}).get("url") or "")
    tls = bool(cmd.get("tlsInsecure") if "tlsInsecure" in cmd else (inst or {}).get("tlsInsecure"))
    if not valid_origin(origin):
        return {"ok": False, "error": "No URL for this instance."}
    rec = refresh_secret(instance_id, rec, origin, tls)
    token = rec.get("accessToken")
    if not token:
        return {"ok": False, "error": "No token for this instance."}
    with lock:
        old = sessions.get(instance_id)
        if old:
            old.disconnect()
        sess = HaSession(instance_id, origin, tls, str(token))
        sessions[instance_id] = sess
        sess.start()
    return {"ok": True, "data": {"instanceId": instance_id, "hasToken": True, "kind": (rec or {}).get("kind") or "llat"}}


def cmd_forget(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    with lock:
        old = sessions.pop(instance_id, None)
        if old:
            old.disconnect()
    delete_secret(instance_id)
    return {"ok": True, "data": {"instanceId": instance_id}}


def cmd_disconnect(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    with lock:
        old = sessions.pop(instance_id, None)
        if old:
            old.disconnect()
    return {"ok": True}


def cmd_call(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    with lock:
        sess = sessions.get(instance_id)
    if not sess or not sess.ws or sess.stop.is_set():
        return {"ok": False, "error": "not connected", "disconnected": True}
    payload = sanitize_call_payload(cmd.get("payload"))
    if not payload:
        return {"ok": False, "error": "only call_service for a valid entity is allowed"}
    msg = sess.rpc(payload, timeout=15.0)
    if not msg.get("success"):
        err = msg.get("error") or {}
        text = err.get("message") if isinstance(err, dict) else str(err or "call failed")
        return {"ok": False, "error": text or "call failed"}
    return {"ok": True, "data": msg.get("result")}


def cmd_list_secrets(_cmd: dict[str, Any]) -> dict[str, Any]:
    ids = list((load_secrets().get("instances") or {}).keys())
    return {"ok": True, "data": {"ids": ids}}


def cmd_snapshot(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    with lock:
        sess = sessions.get(instance_id)
    if not sess:
        return {"ok": False, "error": "not connected"}
    sess._need_snapshot = True
    sess._snap_at = 0.0
    return {"ok": True}


def cmd_energy(cmd: dict[str, Any]) -> dict[str, Any] | None:
    instance_id = str(cmd.get("instanceId") or "")
    cid = cmd.get("id")
    with lock:
        sess = sessions.get(instance_id)
    if not sess:
        return {"ok": True, "data": energy_lib.disabled("not_connected")}

    def work() -> None:
        try:
            data = sess.fetch_energy()
        except Exception as e:
            data = energy_lib.disabled(str(e))
        emit({"event": "result", "id": cid, "ok": True, "data": redact(data)})

    threading.Thread(target=work, name="hearth-energy", daemon=True).start()
    return None


HANDLERS = {
    "providers": cmd_providers,
    "login": cmd_login,
    "connect": cmd_connect,
    "forget": cmd_forget,
    "disconnect": cmd_disconnect,
    "call": cmd_call,
    "listSecrets": cmd_list_secrets,
    "energy": cmd_energy,
    "snapshot": cmd_snapshot,
}



def handle(cmd: dict[str, Any]) -> None:
    cid = cmd.get("id")
    name = cmd.get("cmd")
    fn = HANDLERS.get(str(name))
    if not fn:
        emit({"event": "result", "id": cid, "ok": False, "error": "unknown cmd"})
        return
    try:
        result = fn(cmd)
    except Exception as e:
        log("error", str(e))
        emit({"event": "result", "id": cid, "ok": False, "error": str(e)})
        return
    if result is None:
        return
    out = {"event": "result", "id": cid, "ok": bool(result.get("ok"))}
    if "error" in result:
        out["error"] = result["error"]
    if "data" in result:
        out["data"] = redact(result["data"])
    if result.get("disconnected"):
        out["disconnected"] = True
    emit(out)


def main() -> None:
    ensure_dirs()
    sweep_orphans()
    # DNS + connect must not block the stdin reader; Test waits on login.
    socket.setdefaulttimeout(15)
    log("info", "ha_bridge ready")
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        line = line.strip()
        if not line:
            continue
        if len(line) > JSON_LINE_CAP:
            log("warn", "dropping oversize stdin line")
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            log("warn", "bad JSON on stdin")
            continue
        if not isinstance(cmd, dict):
            continue
        threading.Thread(target=handle, args=(cmd,), name="hearth-cmd", daemon=True).start()
    with lock:
        for sess in list(sessions.values()):
            sess.disconnect()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
