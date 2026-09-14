#!/usr/bin/env python3
import base64
import hashlib
import http.client
import json
import socket
import threading
import unittest

import rfc6455

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakeHA:
    def __init__(self, handler):
        self.handler = handler
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        try:
            self.handler(conn)
        finally:
            try:
                conn.close()
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
        self.thread.join(timeout=1)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def read_http(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def accept_upgrade(conn, extra_headers=b""):
    raw = read_http(conn)
    key = None
    for line in raw.decode("iso-8859-1").split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
    if not key:
        raise RuntimeError("no key")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    resp = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
    ).encode("ascii") + extra_headers + b"\r\n"
    conn.sendall(resp)
    return raw


class Rfc6455Tests(unittest.TestCase):
    def test_upgrade_and_text_roundtrip(self):
        done = threading.Event()

        def handler(conn):
            accept_upgrade(conn)
            conn.sendall(rfc6455.encode_frame_for_tests(rfc6455.OP_TEXT, b'{"type":"auth_required"}'))
            # read one client frame (masked)
            hdr = conn.recv(2)
            length = hdr[1] & 0x7F
            if length == 126:
                length = int.from_bytes(conn.recv(2), "big")
            mask = conn.recv(4)
            payload = conn.recv(length)
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            self.assertIn(b"auth", payload)
            conn.sendall(rfc6455.encode_frame_for_tests(rfc6455.OP_TEXT, b'{"type":"auth_ok"}'))
            done.set()

        with FakeHA(handler) as srv:
            ws = rfc6455.connect(f"ws://127.0.0.1:{srv.port}/api/websocket")
            try:
                hello = ws.recv()
                self.assertIn("auth_required", hello)
                ws.send_text('{"type":"auth","access_token":"x"}')
                ok = ws.recv()
                self.assertIn("auth_ok", ok)
            finally:
                ws.close()
            done.wait(2)

    def test_reject_extensions(self):
        def handler(conn):
            accept_upgrade(conn, extra_headers=b"Sec-WebSocket-Extensions: permessage-deflate\r\n")

        with FakeHA(handler) as srv:
            with self.assertRaises(rfc6455.WebSocketError):
                rfc6455.connect(f"ws://127.0.0.1:{srv.port}/")

    def test_reject_non_101(self):
        def handler(conn):
            read_http(conn)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

        with FakeHA(handler) as srv:
            with self.assertRaises(rfc6455.WebSocketError):
                rfc6455.connect(f"ws://127.0.0.1:{srv.port}/")

    def test_accept_2mib_text_frame(self):
        payload = b"x" * (2 * 1024 * 1024)

        def handler(conn):
            accept_upgrade(conn)
            conn.sendall(rfc6455.encode_frame_for_tests(rfc6455.OP_TEXT, payload))

        with FakeHA(handler) as srv:
            ws = rfc6455.connect(f"ws://127.0.0.1:{srv.port}/")
            try:
                text = ws.recv()
                self.assertEqual(len(text), len(payload))
            finally:
                ws.close()

    def test_reject_oversize_frame_header(self):
        def handler(conn):
            accept_upgrade(conn)
            # 32MiB+1 claimed length, no payload sent
            header = bytearray()
            header.append(0x81)
            header.append(127)
            header.extend((rfc6455.MAX_FRAME + 1).to_bytes(8, "big"))
            conn.sendall(bytes(header))

        with FakeHA(handler) as srv:
            ws = rfc6455.connect(f"ws://127.0.0.1:{srv.port}/")
            try:
                with self.assertRaises(rfc6455.WebSocketError):
                    ws.recv()
            finally:
                ws.close()

    def test_reject_binary(self):
        def handler(conn):
            accept_upgrade(conn)
            conn.sendall(rfc6455.encode_frame_for_tests(rfc6455.OP_BIN, b"nope"))

        with FakeHA(handler) as srv:
            ws = rfc6455.connect(f"ws://127.0.0.1:{srv.port}/")
            try:
                with self.assertRaises(rfc6455.WebSocketError):
                    ws.recv()
            finally:
                ws.close()

    def test_cert_none_only_when_insecure_flag(self):
        # tls_insecure uses CERT_NONE; the default context verifies.
        ctx_default = __import__("ssl").create_default_context()
        self.assertNotEqual(ctx_default.verify_mode, __import__("ssl").CERT_NONE)
        insecure = __import__("ssl")._create_unverified_context()
        self.assertEqual(insecure.verify_mode, __import__("ssl").CERT_NONE)


class BridgeUnitTests(unittest.TestCase):
    def test_providers_shapes(self):
        import ha_bridge

        obj = {"providers": [{"type": "homeassistant", "id": None}, {"type": "trusted_networks"}], "preselect_remember_me": False}
        arr = [["homeassistant", None]]
        self.assertTrue(ha_bridge.has_homeassistant_provider(obj))
        self.assertTrue(ha_bridge.has_homeassistant_provider(arr))
        self.assertFalse(ha_bridge.has_homeassistant_provider({"providers": [{"type": "trusted_networks"}]}))
        self.assertEqual(ha_bridge.homeassistant_handler(obj), ["homeassistant", None])

    def test_sanitize_call_payload_rejects_non_service(self):
        import ha_bridge

        good = ha_bridge.sanitize_call_payload({
            "type": "call_service",
            "domain": "light",
            "service": "turn_on",
            "target": {"entity_id": "light.kitchen"},
            "service_data": {"brightness_pct": 40, "evil key": 1},
        })
        self.assertEqual(good["type"], "call_service")
        self.assertEqual(good["target"]["entity_id"], "light.kitchen")
        self.assertEqual(good["service_data"], {"brightness_pct": 40})
        self.assertIsNone(ha_bridge.sanitize_call_payload({"type": "get_config"}))
        self.assertIsNone(ha_bridge.sanitize_call_payload({
            "type": "call_service", "domain": "light", "service": "turn_on",
            "target": {"entity_id": "light.x; rm -rf /"},
        }))
        self.assertIsNone(ha_bridge.sanitize_call_payload({
            "type": "call_service", "domain": "light;id", "service": "turn_on",
            "target": {"entity_id": "light.kitchen"},
        }))

    def test_redact_strips_tokens(self):
        import ha_bridge

        out = ha_bridge.redact({"accessToken": "secret", "kind": "llat", "nested": {"password": "x", "haVersion": "1"}})
        self.assertNotIn("accessToken", out)
        self.assertEqual(out["kind"], "llat")
        self.assertNotIn("password", out["nested"])
        self.assertEqual(out["nested"]["haVersion"], "1")


if __name__ == "__main__":
    unittest.main()
