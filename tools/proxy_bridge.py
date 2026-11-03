"""Loopback HTTP CONNECT proxy for clients that cannot consume SOCKS URLs."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import select
import selectors
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit

import socks


PROXY_KEYS = ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy")


def proxy_fingerprint(url):
    return hashlib.sha256(url.encode()).hexdigest()


def connect_target(upstream, host, port):
    parsed = urlsplit(upstream)
    kind = socks.SOCKS4 if parsed.scheme.startswith("socks4") else socks.SOCKS5
    return socks.create_connection((host, port), timeout=20, proxy_type=kind,
                                   proxy_addr=parsed.hostname, proxy_port=parsed.port or 1080,
                                   proxy_rdns=parsed.scheme in {"socks5h", "socks4a"},
                                   proxy_username=unquote(parsed.username) if parsed.username else None,
                                   proxy_password=unquote(parsed.password) if parsed.password else None)


def relay(left, right):
    left.settimeout(None)
    right.settimeout(None)
    while True:
        readable, _, _ = select.select([left, right], [], [], 120)
        if not readable:
            return
        for source in readable:
            data = source.recv(65536)
            if not data:
                return
            (right if source is left else left).sendall(data)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_CONNECT(self):
        self.close_connection = True
        target = urlsplit("//" + self.path)
        connected = False
        try:
            port = target.port or 443
            if not target.hostname:
                raise ValueError("Missing CONNECT host")
            with connect_target(self.server.upstream, target.hostname, port) as remote:
                self.send_response(200, "Connection Established")
                self.end_headers()
                self.wfile.flush()
                connected = True
                relay(self.connection, remote)
        except (OSError, ValueError):
            if not connected:
                self.send_error(502, "SOCKS upstream connection failed")

    def do_GET(self):
        if self.path == "/__genai_proxy_health":
            body = json.dumps({"service": "genai-socks-bridge", "fingerprint": proxy_fingerprint(self.server.upstream)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.forward_http()

    def forward_http(self):
        self.close_connection = True
        target = urlsplit(self.path)
        if target.scheme != "http" or not target.hostname:
            self.send_error(400, "Use an absolute HTTP URL or CONNECT for HTTPS")
            return
        if self.headers.get("Transfer-Encoding"):
            self.send_error(501, "Use CONNECT for streaming requests")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 8_000_000:
                raise ValueError("Request body exceeds the limit")
            with connect_target(self.server.upstream, target.hostname, target.port or 80) as remote:
                path = target.path or "/"
                if target.query:
                    path += "?" + target.query
                headers = [f"{self.command} {path} HTTP/1.1", f"Host: {target.netloc}", "Connection: close"]
                headers += [f"{key}: {value}" for key, value in self.headers.items() if key.lower() not in {"host", "connection", "proxy-connection", "proxy-authorization"}]
                remote.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("latin-1"))
                if length:
                    remote.sendall(self.rfile.read(length))
                relay(self.connection, remote)
        except (OSError, ValueError):
            self.send_error(502, "SOCKS upstream connection failed")

    do_HEAD = do_POST = do_PUT = do_DELETE = do_OPTIONS = forward_http


def ensure_http_proxy(project, environment=None):
    environment = os.environ if environment is None else environment
    upstream = next((environment[key] for key in PROXY_KEYS if environment.get(key)), "")
    if urlsplit(upstream).scheme not in {"socks5", "socks5h", "socks4", "socks4a"}:
        return None
    logs = Path(project) / ".logs"
    logs.mkdir(exist_ok=True)
    state_path = logs / "proxy.json"
    fingerprint = proxy_fingerprint(upstream)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            port = state["port"]
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Invalid proxy port")
            with opener.open(f"http://127.0.0.1:{port}/__genai_proxy_health", timeout=1) as response:
                info = json.load(response)
            if info.get("service") == "genai-socks-bridge" and info.get("fingerprint") == fingerprint:
                return f"http://127.0.0.1:{port}"
        except (OSError, ValueError, KeyError):
            pass
    with (logs / "proxy.log").open("a") as logfile:
        child = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve())],
                                 env={**environment, "GENAI_UPSTREAM_PROXY": upstream},
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=logfile,
                                 text=True, start_new_session=True)
    with selectors.DefaultSelector() as ready:
        ready.register(child.stdout, selectors.EVENT_READ)
        if not ready.select(timeout=5):
            child.terminate()
            raise RuntimeError("Local HTTP proxy did not start; see .logs/proxy.log")
    line = child.stdout.readline()
    child.stdout.close()
    if not line:
        raise RuntimeError("Local HTTP proxy exited; see .logs/proxy.log")
    state = json.loads(line)
    state_path.write_text(json.dumps(state) + "\n")
    return f"http://127.0.0.1:{state['port']}"


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    server.daemon_threads = True
    server.upstream = os.environ["GENAI_UPSTREAM_PROXY"]
    print(json.dumps({"port": server.server_port, "fingerprint": proxy_fingerprint(server.upstream)}), flush=True)
    server.serve_forever()
