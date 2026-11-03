import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

import requests

from tools.proxy_bridge import ProxyHandler, ensure_http_proxy


class OriginHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        body = b"PROXY_ORIGIN_OK"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


class ProxyBridgeTests(unittest.TestCase):
    def setUp(self):
        self.origin = ThreadingHTTPServer(("127.0.0.1", 0), OriginHandler)
        self.proxy = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
        self.proxy.upstream = "socks5h://127.0.0.1:1080"
        for server in (self.origin, self.proxy):
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self):
        for server in (self.proxy, self.origin):
            server.shutdown()
            server.server_close()

    def connect_origin(self, *_args):
        return socket.create_connection(self.origin.server_address, timeout=3)

    def test_absolute_http_request_is_forwarded(self):
        client = requests.Session()
        client.trust_env = False
        with patch("tools.proxy_bridge.connect_target", side_effect=self.connect_origin):
            r = client.get("http://example.com/page", proxies={"http": f"http://127.0.0.1:{self.proxy.server_port}"}, timeout=3)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, "PROXY_ORIGIN_OK")

    def test_connect_tunnel_transports_bytes(self):
        with patch("tools.proxy_bridge.connect_target", side_effect=self.connect_origin), socket.create_connection(self.proxy.server_address, timeout=3) as client:
            client.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
            response = b""
            while b"\r\n\r\n" not in response:
                response += client.recv(1024)
            self.assertIn(b"200 Connection Established", response)
            client.sendall(b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")
            response = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response += chunk
            self.assertIn(b"PROXY_ORIGIN_OK", response)

    def test_failed_connect_returns_502(self):
        with patch("tools.proxy_bridge.connect_target", side_effect=OSError("offline")), socket.create_connection(self.proxy.server_address, timeout=3) as client:
            client.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n")
            self.assertIn(b"502", client.recv(4096))

    def test_http_proxy_does_not_start_an_unneeded_bridge(self):
        with tempfile.TemporaryDirectory() as temp, patch("tools.proxy_bridge.subprocess.Popen") as spawn:
            self.assertIsNone(ensure_http_proxy(Path(temp), {"HTTPS_PROXY": "http://127.0.0.1:8080"}))
            spawn.assert_not_called()

    def test_existing_matching_bridge_is_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            logs = Path(temp) / ".logs"
            logs.mkdir()
            (logs / "proxy.json").write_text(json.dumps({"port": self.proxy.server_port}))
            with patch("tools.proxy_bridge.subprocess.Popen") as spawn:
                url = ensure_http_proxy(Path(temp), {"ALL_PROXY": self.proxy.upstream})
            self.assertEqual(url, f"http://127.0.0.1:{self.proxy.server_port}")
            spawn.assert_not_called()
