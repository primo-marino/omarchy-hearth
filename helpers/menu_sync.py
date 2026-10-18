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
    text = raw or ""
    out = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < n:
            nxt = text[i + 1]
            if nxt == '/':
                i += 2
                while i < n and text[i] != '\n':
                    i += 1
                continue
            if nxt == '*':
                i += 2
                while i < n:
                    if text[i] == '*' and i + 1 < n and text[i + 1] == '/':
                        i += 2
                        break
                    if text[i] == '\n':
                        out.append('\n')
                    i += 1
                continue
        if ch == ',':
            j = i + 1
            while j < n:
                c = text[j]
                if c in ' \t\r\n':
                    j += 1
                    continue
                if c == '/' and j + 1 < n:
                    if text[j + 1] == '/':
                        j += 2
                        while j < n and text[j] != '\n':
                            j += 1
                        continue
                    if text[j + 1] == '*':
                        j += 2
                        while j < n:
                            if text[j] == '*' and j + 1 < n and text[j + 1] == '/':
                                j += 2
                                break
                            j += 1
                        continue
                break
            if j < n and text[j] in '}]':
                i += 1
                continue
        out.append(ch)
        i += 1
    return ''.join(out)


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


def skip_ws_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\r\n':
            i += 1
            continue
        if c == '/' and i + 1 < n:
            if text[i + 1] == '/':
                i += 2
                while i < n and text[i] != '\n':
                    i += 1
                continue
            if text[i + 1] == '*':
                i += 2
                while i < n:
                    if text[i] == '*' and i + 1 < n and text[i + 1] == '/':
                        i += 2
                        break
                    i += 1
                continue
        break
    return i


def skip_string(text: str, i: int) -> int:
    n = len(text)
    i += 1
    while i < n:
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return i


def skip_container(text: str, i: int, open_ch: str, close_ch: str) -> int:
    n = len(text)
    depth = 0
    while i < n:
        c = text[i]
        if c == '"':
            i = skip_string(text, i)
            continue
        if c == '/' and i + 1 < n:
            if text[i + 1] == '/':
                i += 2
                while i < n and text[i] != '\n':
                    i += 1
                continue
            if text[i + 1] == '*':
                i += 2
                while i < n:
                    if text[i] == '*' and i + 1 < n and text[i + 1] == '/':
                        i += 2
                        break
                    i += 1
                continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def skip_value(text: str, i: int) -> int:
    n = len(text)
    if i >= n:
        return i
    c = text[i]
    if c == '"':
        return skip_string(text, i)
    if c == '{':
        return skip_container(text, i, '{', '}')
    if c == '[':
        return skip_container(text, i, '[', ']')
    while i < n:
        c = text[i]
        if c in ' \t\r\n,}]':
            break
        if c == '/' and i + 1 < n and text[i + 1] in '/*':
            break
        i += 1
    return i


def _member_spans(text: str):
    n = len(text)
    i = skip_ws_comments(text, 0)
    if i >= n or text[i] != '{':
        return None
    root_open = i
    i += 1
    members = []
    while True:
        i = skip_ws_comments(text, i)
        if i >= n:
            return None
        if text[i] == '}':
            root_close = i
            break
        if text[i] != '"':
            return None
        key_start = i
        i = skip_string(text, i)
        key_end = i
        try:
            key = json.loads(text[key_start:key_end])
        except json.JSONDecodeError:
            return None
        i = skip_ws_comments(text, i)
        if i >= n or text[i] != ':':
            return None
        i += 1
        i = skip_ws_comments(text, i)
        i = skip_value(text, i)
        value_end = i
        j = skip_ws_comments(text, value_end)
        comma = j if j < n and text[j] == ',' else -1
        i = comma + 1 if comma >= 0 else j
        members.append({
            'key': key,
            'key_start': key_start,
            'value_end': value_end,
            'comma': comma,
        })
    return (root_open, root_close, members)


def _removal_span(text: str, m: dict) -> tuple[int, int]:
    s = m['key_start']
    ls = text.rfind('\n', 0, s) + 1
    if text[ls:s].strip(' \t') == '':
        s = ls
    e = m['comma'] + 1 if m['comma'] >= 0 else m['value_end']
    k = e
    while k < len(text) and text[k] in ' \t':
        k += 1
    if k < len(text) and text[k] == '\n' and s == ls:
        e = k + 1
    elif k >= len(text) or text[k] in '\r':
        e = k
    return s, e


def splice_hearth(raw: str, tree: dict[str, Any]) -> Optional[str]:
    parsed = parse_object(raw)
    if parsed is None:
        return None
    spans = _member_spans(raw)
    if spans is None:
        return None
    root_open, root_close, members = spans

    hearth_members = [m for m in members if is_hearth_key(m['key'])]
    kept_members = [m for m in members if not is_hearth_key(m['key'])]

    # Was the last kept member originally followed by a hearth member?
    last_kept_followed_by_hearth = False
    if kept_members:
        last_kept = kept_members[-1]
        for m in members:
            if m is last_kept:
                continue
            if m['key_start'] > last_kept['key_start'] and is_hearth_key(m['key']):
                last_kept_followed_by_hearth = True
                break

    removals = [_removal_span(raw, m) for m in hearth_members]
    removals.sort(key=lambda x: x[0], reverse=True)
    text2 = raw
    for s, e in removals:
        text2 = text2[:s] + text2[e:]

    spans2 = _member_spans(text2)
    if spans2 is None:
        return None
    root_open2, root_close2, members2 = spans2
    kept2 = [m for m in members2 if not is_hearth_key(m['key'])]

    new_member_texts = []
    for key, value in tree.items():
        if not is_hearth_key(key):
            continue
        value_str = json.dumps(value, indent=2, ensure_ascii=False).replace('\n', '\n  ')
        new_member_texts.append('  ' + json.dumps(key) + ': ' + value_str)

    if kept2:
        last = kept2[-1]
        has_comma = last['comma'] >= 0
        if new_member_texts and not has_comma:
            text2 = text2[:last['value_end']] + ',' + text2[last['value_end']:]
            spans2 = _member_spans(text2)
            if spans2 is None:
                return None
            root_open2, root_close2, members2 = spans2
            kept2 = [m for m in members2 if not is_hearth_key(m['key'])]
        elif not new_member_texts and has_comma and last_kept_followed_by_hearth:
            text2 = text2[:last['comma']] + text2[last['comma'] + 1:]
            spans2 = _member_spans(text2)
            if spans2 is None:
                return None
            root_open2, root_close2, members2 = spans2

    if not new_member_texts:
        parsed_new = parse_object(text2)
        if parsed_new is None:
            return None
        if parsed_new != merge_hearth(parsed, tree):
            return None
        return text2

    before = text2[:root_close2]
    after = text2[root_close2:]
    insertion = ''
    if before and not before.endswith('\n'):
        insertion += '\n'
    insertion += ',\n'.join(new_member_texts) + '\n'
    new_text = before + insertion + after
    parsed_new = parse_object(new_text)
    if parsed_new is None:
        return None
    if parsed_new != merge_hearth(parsed, tree):
        return None
    return new_text


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

    if not raw.strip():
        raw = "{}\n"

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

    out = splice_hearth(raw, tree)
    if out is None:
        return {"ok": False, "error": "splice_failed", "wrote": False}

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
    return {"ok": True, "wrote": True, "keys": sum(1 for k in tree if is_hearth_key(k))}


def uninstall(menu_path: str = MENU_PATH) -> dict[str, Any]:
    return sync(tree={}, cli="", menu_path=menu_path)
