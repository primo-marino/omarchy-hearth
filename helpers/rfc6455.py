"""Minimal RFC6455 client: masked text frames, no extensions.

v0.1 Hearth transport. Not a general-purpose WebSocket stack.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
from typing import Optional
from urllib.parse import urlparse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_FRAME = 32 * 1024 * 1024
OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class WebSocketError(Exception):
    pass


class WebSocketClosed(WebSocketError):
    def __init__(self, code: int = 1000, reason: str = ""):
        super().__init__(f"closed {code} {reason}".strip())
        self.code = code
        self.reason = reason


def _accept_key(key: str) -> str:
    digest = hashlib.sha1((key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _mask_key() -> bytes:
    return os.urandom(4)


def _apply_mask(key: bytes, data: bytes) -> bytes:
    return bytes(b ^ key[i % 4] for i, b in enumerate(data))


class WebSocketClient:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = bytearray()
        self.closed = False

    def _sendall(self, data: bytes) -> None:
        sock = self.sock
        if self.closed or sock is None:
            raise WebSocketClosed(1006, "closed")
        sock.sendall(data)

    def _recv_more(self) -> bytes:
        sock = self.sock
        if self.closed or sock is None:
            raise WebSocketClosed(1006, "closed")
        try:
            chunk = sock.recv(65536)
        except OSError as e:
            if e.errno in (9, 104, 32, 107):  # EBADF, ECONNRESET, EPIPE, ENOTCONN
                raise WebSocketClosed(1006, "socket %s" % e.errno) from e
            raise
        if not chunk:
            raise WebSocketClosed(1006, "peer closed")
        return chunk

    def _need(self, n: int) -> bytes:
        while len(self._buf) < n:
            self._buf.extend(self._recv_more())
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def send_frame(self, opcode: int, payload: bytes = b"") -> None:
        if len(payload) > MAX_FRAME:
            raise WebSocketError("outbound frame exceeds 32 MiB")
        key = _mask_key()
        masked = _apply_mask(key, payload)
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        n = len(masked)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        header.extend(key)
        self._sendall(bytes(header) + masked)

    def send_text(self, text: str) -> None:
        self.send_frame(OP_TEXT, text.encode("utf-8"))

    def ping(self, payload: bytes = b"") -> None:
        self.send_frame(OP_PING, payload)

    def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        sock = self.sock
        self.sock = None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def recv(self) -> str:
        while True:
            opcode, payload = self._recv_frame()
            if opcode == OP_TEXT:
                return payload.decode("utf-8")
            if opcode == OP_PING:
                self.send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                code = 1000
                reason = ""
                if len(payload) >= 2:
                    code = struct.unpack("!H", payload[:2])[0]
                    reason = payload[2:].decode("utf-8", "replace")
                self.close(code, reason)
                raise WebSocketClosed(code, reason)
            raise WebSocketError(f"unsupported opcode {opcode}")

    def _recv_frame(self) -> tuple[int, bytes]:
        b1, b2 = self._need(2)
        fin = (b1 & 0x80) != 0
        rsv = b1 & 0x70
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if rsv:
            raise WebSocketError("RSV bits must be zero (no extensions)")
        if not fin:
            raise WebSocketError("fragmented frames are not supported")
        if opcode in (OP_CONT, OP_BIN):
            raise WebSocketError("only text frames are accepted")
        if length == 126:
            length = struct.unpack("!H", self._need(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._need(8))[0]
        if opcode in (OP_CLOSE, OP_PING, OP_PONG) and length > 125:
            raise WebSocketError("control frame exceeds 125 bytes")
        if length > MAX_FRAME:
            raise WebSocketError(f"inbound frame {length} exceeds 32 MiB")
        mask = self._need(4) if masked else b""
        payload = self._need(length)
        if masked:
            payload = _apply_mask(mask, payload)
        return opcode, payload


def _parse_headers(raw: bytes) -> tuple[str, dict[str, str]]:
    text = raw.decode("iso-8859-1")
    lines = text.split("\r\n")
    if not lines:
        raise WebSocketError("empty upgrade response")
    status = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        headers[k.strip().lower()] = v.strip()
    return status, headers


def connect(url: str, tls_insecure: bool = False, timeout: float = 15.0) -> WebSocketClient:
    parsed = urlparse(url)
    if parsed.scheme not in ("ws", "wss"):
        raise WebSocketError("URL must be ws:// or wss://")
    host = parsed.hostname
    if not host:
        raise WebSocketError("missing host")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        return _upgrade(sock, parsed, host, port, path, tls_insecure, timeout)
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise


def _upgrade(sock, parsed, host, port, path, tls_insecure, timeout):
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if parsed.scheme == "wss":
        ctx = ssl.create_default_context()
        if tls_insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        sock = ctx.wrap_socket(sock, server_hostname=host)

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    host_header = f"[{host}]:{port}" if ":" in str(host) else f"{host}:{port}"
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(req.encode("ascii"))

    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise WebSocketError("connection closed during upgrade")
        buf.extend(chunk)
        if len(buf) > 65536:
            raise WebSocketError("upgrade response too large")
    head, rest = bytes(buf).split(b"\r\n\r\n", 1)
    status, headers = _parse_headers(head)
    if " 101 " not in status and not status.upper().startswith("HTTP/1.1 101"):
        raise WebSocketError(f"expected HTTP 101, got {status!r}")
    if headers.get("upgrade", "").lower() != "websocket":
        raise WebSocketError("missing Upgrade: websocket")
    if "upgrade" not in headers.get("connection", "").lower():
        raise WebSocketError("missing Connection: Upgrade")
    if headers.get("sec-websocket-accept") != _accept_key(key):
        raise WebSocketError("bad Sec-WebSocket-Accept")
    if headers.get("sec-websocket-extensions"):
        raise WebSocketError("server offered WebSocket extensions")

    client = WebSocketClient(sock)
    if rest:
        client._buf.extend(rest)
    sock.settimeout(timeout)
    return client


def encode_frame_for_tests(opcode: int, payload: bytes, masked: bool = False, rsv: int = 0, fin: bool = True) -> bytes:
    """Build a (usually server-to-client, unmasked) frame for unit tests."""
    header = bytearray()
    header.append((0x80 if fin else 0) | (rsv & 0x70) | (opcode & 0x0F))
    n = len(payload)
    mask_bit = 0x80 if masked else 0
    if n < 126:
        header.append(mask_bit | n)
    elif n < 65536:
        header.append(mask_bit | 126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack("!Q", n))
    if masked:
        key = _mask_key()
        header.extend(key)
        payload = _apply_mask(key, payload)
    return bytes(header) + payload
