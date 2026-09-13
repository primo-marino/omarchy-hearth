#!/usr/bin/env python3
"""Hearth Home Assistant JSON-lines helper. No third-party packages."""

from __future__ import annotations

import json
import os
import queue
import socket
import ssl
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
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
LLAT_LIFESPAN_DAYS = 3650

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


def ensure_dirs() -> None:
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    os.makedirs(CACHE_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
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
    data = load_secrets()
    data.setdefault("instances", {})[instance_id] = rec
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
    dropped = [k for k in list(inst.keys()) if k not in keep]
    if not dropped:
        return
    for k in dropped:
        del inst[k]
        log("info", "hearth: dropped orphan secret id %s" % k)
    write_secrets(data)


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
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        code = e.code
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
        self.waiters: dict[int, tuple[threading.Event, dict[str, Any]]] = {}
        self._id_lock = threading.Lock()

    def next_id(self) -> int:
        with self._id_lock:
            self.msg_id += 1
            return self.msg_id

    def rpc(self, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
        if self.stop.is_set():
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
        if self.ws:
            try:
                self.ws.close()
            except Exception:
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
            self.ws.send_text(json.dumps(body))

    def _run(self) -> None:
        backoff = 1
        while not self.stop.is_set():
            try:
                self.ws, self.ha_version = ws_auth(self.origin, self.token, self.tls_insecure)
                backoff = 1
                cfg = ws_get_config(self.ws, self.next_id)
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
                ping_at = time.monotonic() + 30
                while not self.stop.is_set():
                    self.ws.sock.settimeout(0.2)
                    try:
                        self._flush_outbox()
                        raw = self.ws.recv()
                    except TimeoutError:
                        if self.stop.is_set():
                            break
                        self._flush_outbox()
                        if self._need_snapshot and time.monotonic() >= self._snap_at:
                            self._need_snapshot = False
                            self._snapshot(include_services=False)
                        if time.monotonic() >= ping_at:
                            self.call({"type": "ping"})
                            self._flush_outbox()
                            ping_at = time.monotonic() + 30
                        continue
                    msg = json.loads(raw)
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
                                    "entity": {
                                        "entity_id": entity.get("entity_id"),
                                        "state": entity.get("state"),
                                        "attributes": entity.get("attributes") or {},
                                    },
                                })
                        elif et in ("entity_registry_updated", "area_registry_updated", "device_registry_updated"):
                            self._need_snapshot = True
                            self._snap_at = time.monotonic() + 0.4
                    elif msg.get("type") == "pong":
                        ping_at = time.monotonic() + 30
            except WebSocketClosed as e:
                emit({"event": "connection", "instanceId": self.instance_id, "state": "reconnecting",
                      "error": str(e)})
            except Exception as e:
                emit({"event": "connection", "instanceId": self.instance_id, "state": "reconnecting",
                      "error": str(e)})
            if self.stop.is_set():
                break
            time.sleep(backoff)
            backoff = min(30, backoff * 2 if backoff >= 2 else (2 if backoff == 1 else 5))
        emit({"event": "connection", "instanceId": self.instance_id, "state": "disconnected"})

    def _snapshot(self, include_services: bool = True) -> None:
        if not self.ws:
            return
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
                msg = json.loads(self.ws.recv())
                if msg.get("id") == mid:
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
        path = os.path.join(CACHE_DIR, "%s.json" % self.instance_id)
        payload = {
            "instanceId": self.instance_id,
            "areas": areas,
            "devices": devices,
            "entities": entities[:5000],
            "states": states[:5000],
            "services": services,
        }
        atomic_write(path, json.dumps(payload), 0o600)
        emit({
            "event": "snapshot",
            "instanceId": self.instance_id,
            "path": path,
            "entityCount": min(len(states), 5000),
            "areaCount": len(areas),
        })
        # extra registry subscriptions happen once after first snapshot in _run


def cmd_providers(cmd: dict[str, Any]) -> dict[str, Any]:
    origin = cmd.get("url") or ""
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
    flow_id = flow["flow_id"]
    code, step = http_json(
        "POST",
        origin.rstrip("/") + "/auth/login_flow/" + flow_id,
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
    if not instance_id:
        return {"ok": False, "error": "login requires instanceId"}
    if not origin:
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


def cmd_connect(cmd: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(cmd.get("instanceId") or "")
    if not instance_id:
        return {"ok": False, "error": "connect requires instanceId"}
    rec = secret_for(instance_id)
    token = (rec or {}).get("accessToken") or os.environ.get("HEARTH_TOKEN")
    if not token:
        return {"ok": False, "error": "No token for this instance."}
    cfg = load_config()
    inst = None
    for row in cfg.get("instances") or []:
        if row and str(row.get("id")) == instance_id:
            inst = row
            break
    origin = str(cmd.get("url") or (inst or {}).get("url") or "")
    tls = bool(cmd.get("tlsInsecure") if "tlsInsecure" in cmd else (inst or {}).get("tlsInsecure"))
    if not origin:
        return {"ok": False, "error": "No URL for this instance."}
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
    if not sess:
        return {"ok": False, "error": "not connected"}
    payload = cmd.get("payload") or {}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "bad payload"}
    sess.call(payload)
    return {"ok": True}


def cmd_list_secrets(_cmd: dict[str, Any]) -> dict[str, Any]:
    ids = list((load_secrets().get("instances") or {}).keys())
    return {"ok": True, "data": {"ids": ids}}


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
