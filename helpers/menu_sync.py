"""Fail-closed merge of hearth* keys into omarchy-menu.jsonc."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date
from typing import Any, Optional

HEARTH_KEY = re.compile(r"^hearth(\.|$)")
MENU_DIR = os.path.join(os.environ.get("HOME", ""), ".config", "omarchy", "extensions")
MENU_PATH = os.path.join(MENU_DIR, "omarchy-menu.jsonc")
BAK_PATH = os.path.join(MENU_DIR, "omarchy-menu.jsonc.bak")
STATE_DIR = os.path.join(os.environ.get("HOME", ""), ".local", "state", "omarchy", "hearth")
ETAG_PATH = os.path.join(STATE_DIR, "menu-etag")
TREE_PATH = os.path.join(os.environ.get("HOME", ""), ".cache", "omarchy", "hearth", "menu-tree.json")


def strip_jsonc(raw: str) -> str:
    text = re.sub(r"^\s*//[^\n]*(\n|$)", "", raw or "", flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def is_hearth_key(key: str) -> bool:
    return bool(HEARTH_KEY.match(str(key)))


def parse_object(raw: str) -> Optional[dict[str, Any]]:
    stripped = strip_jsonc(raw).strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or isinstance(parsed, list):
        return None
    return parsed


def file_sha(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def load_etag(path: str = ETAG_PATH) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def atomic_write(path: str, data: str, mode: int = 0o644) -> None:
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
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def merge_hearth(existing: dict[str, Any], tree: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in existing.items():
        if not is_hearth_key(key):
            out[key] = value
    for key, value in tree.items():
        if is_hearth_key(str(key)) and isinstance(value, dict):
            out[str(key)] = value
    return out


def disconnected_tree(cli: str) -> dict[str, Any]:
    return {
        "hearth": {"icon": "󰋜", "label": "Hearth", "aliases": ["home assistant", "ha"]},
        "hearth.open": {"icon": "󰏥", "label": "Open Hearth", "action": "omarchy-shell shell summon io.github.primo-marino.hearth"},
        "hearth.add": {"icon": "", "label": "Add Home Assistant", "action": "%s onboard" % cli},
        "hearth.status": {
            "icon": "󰋜",
            "label": "Hearth is not connected",
            "action": 'omarchy-notification-send -g 󰋜 "Hearth is not connected"',
        },
    }


def load_tree(cli: str) -> dict[str, Any]:
    try:
        with open(TREE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return {str(k): v for k, v in data.items() if is_hearth_key(str(k)) and isinstance(v, dict)}
    except (OSError, json.JSONDecodeError):
        pass
    return disconnected_tree(cli)


def sync(tree: Optional[dict[str, Any]] = None, cli: str = "", menu_path: str = MENU_PATH,
         etag_path: Optional[str] = None, bak_path: Optional[str] = None) -> dict[str, Any]:
    cli = cli or os.path.realpath(os.path.join(os.path.dirname(__file__), "hearth"))
    etag_path = etag_path or ETAG_PATH
    bak_path = bak_path or (BAK_PATH if menu_path == MENU_PATH else menu_path + ".bak")
    tree = tree if tree is not None else load_tree(cli)
    tree_hash = file_sha(json.dumps(tree, sort_keys=True, separators=(",", ":")))
    etag = load_etag(etag_path)

    if not os.path.exists(menu_path):
        os.makedirs(os.path.dirname(menu_path), mode=0o700, exist_ok=True)
        raw = "{}\n"
    else:
        try:
            with open(menu_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            return {"ok": False, "error": "read_failed", "detail": str(e), "wrote": False}

    parsed = parse_object(raw)
    if parsed is None:
        return {"ok": False, "error": "parse_failed", "wrote": False}

    now = time.time()
    last_file = str(etag.get("fileHash") or "")
    current_hash = file_sha(raw)
    if etag.get("treeHash") == tree_hash and current_hash == last_file:
        return {"ok": True, "skipped": "etag", "wrote": False}
    # Same Hearth tree, but the user edited the file. Leave it until our tree changes.
    if etag.get("treeHash") == tree_hash and last_file and current_hash != last_file:
        return {"ok": True, "skipped": "user_edit", "wrote": False}

    merged = merge_hearth(parsed, tree)
    out = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"

    bak_day = str(etag.get("bakDay") or "")
    today = date.today().isoformat()
    if os.path.exists(menu_path) and bak_day != today:
        try:
            with open(menu_path, "r", encoding="utf-8") as f:
                bak_raw = f.read()
            atomic_write(bak_path, bak_raw, 0o644)
        except OSError:
            pass
        bak_day = today

    atomic_write(menu_path, out, 0o644)
    atomic_write(etag_path, json.dumps({
        "treeHash": tree_hash,
        "fileHash": file_sha(out),
        "writtenAt": now,
        "bakDay": bak_day,
    }, indent=2) + "\n", 0o644)
    return {"ok": True, "wrote": True, "keys": sum(1 for k in merged if is_hearth_key(k))}


def uninstall(menu_path: str = MENU_PATH) -> dict[str, Any]:
    return sync(tree={}, cli="", menu_path=menu_path)
