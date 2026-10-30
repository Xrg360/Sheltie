"""Serves the dashboard (the static `next build` export) and proxies its API calls.

This replaces `next start`: a Node server cost ~90 MB to serve files that never change
and forward /api/sheltie/* to the API on 127.0.0.1. The proxy keeps that boundary: the
browser talks to this server only, and only the headers the API needs are passed on.
"""

import gzip
import http.client
import json
import logging
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from monitors.config import env


# x-meerkat-* is the pre-0.3 name; the backend accepts both.
FORWARDED_HEADERS = ("Content-Type", "X-Sheltie-Action-Token", "X-Meerkat-Action-Token")
# /api/meerkat is the pre-0.3 proxy path; scripts and bookmarks that call it keep working.
PROXY_PREFIXES = ("/api/sheltie", "/api/meerkat")
MAX_BODY = 65536
PROXY_TIMEOUT = 10
# Text worth compressing for phones on Tailscale; images and fonts are already compressed.
COMPRESSIBLE = ("text/", "application/javascript", "application/json", "image/svg+xml", "application/manifest+json")
CONTENT_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".txt": "text/plain", ".webmanifest": "application/manifest+json"}


def backend_path(parts: list[str]) -> str:
    """Maps /api/sheltie/<parts> to the API path, like the old Next.js route did."""
    if parts and parts[0] == "actions":
        return "/api/" + "/".join(parts)
    if parts and parts[0] == "metrics":
        return "/metrics"
    return "/api/" + ("/".join(parts) or "status")


def proxy_parts(path: str) -> list[str] | None:
    """Returns the path parts after a proxy prefix, or None when it is not an API path."""
    for prefix in PROXY_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return [part for part in path[len(prefix):].split("/") if part]
    return None


def content_type(file: Path) -> str:
    kind = CONTENT_TYPES.get(file.suffix) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    return f"{kind}; charset=utf-8" if kind.startswith("text/") or kind == "application/json" else kind


class WebServer:
    def __init__(self, config: dict[str, Any]) -> None:
        web_config = config.get("web", {}) or {}
        self.enabled = bool(web_config.get("enabled", True))
        self.root = Path(env("WEB_ROOT") or web_config.get("root", "web")).resolve()
        self.host = str(env("WEB_HOST") or web_config.get("host", "0.0.0.0"))
        self.port = int(os.getenv("PORT") or web_config.get("port", 8710))
        api = urlsplit(env("API_BASE") or "http://127.0.0.1:8711")
        self.api_host = api.hostname or "127.0.0.1"
        self.api_port = api.port or 80
        self.api_base = f"http://{self.api_host}:{self.api_port}"
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        if not (self.root / "index.html").is_file():
            # A development checkout runs `npm run dev` instead; the API still works.
            logging.warning("Dashboard files not found in %s; the dashboard is not served", self.root)
            return

        root = self.root
        api_host, api_port, api_base = self.api_host, self.api_port, self.api_base

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._handle(head=False)

            def do_HEAD(self) -> None:
                self._handle(head=True)

            def do_POST(self) -> None:
                url = urlsplit(self.path)
                parts = proxy_parts(url.path)
                if parts is None:
                    self._send(405, b"", "text/plain; charset=utf-8")
                    return
                self._proxy("POST", parts, url.query)

            def _handle(self, head: bool) -> None:
                url = urlsplit(self.path)
                parts = proxy_parts(url.path)
                if parts is not None:
                    self._proxy("HEAD" if head else "GET", parts, url.query)
                    return
                self._static(unquote(url.path), url.query, head)

            def _static(self, path: str, query: str, head: bool) -> None:
                target = (root / path.lstrip("/")).resolve()
                if target != root and root not in target.parents:
                    self._send(404, b"", "text/plain; charset=utf-8")
                    return
                if target.is_dir():
                    index = target / "index.html"
                    if index.is_file() and not path.endswith("/"):
                        # The export uses trailing slashes; `next start` redirected the same way.
                        self.send_response(308)
                        self.send_header("Location", path + "/" + (f"?{query}" if query else ""))
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    target = index
                status = 200
                if not target.is_file():
                    status, target = 404, root / "404.html"
                    if not target.is_file():
                        self._send(404, b"", "text/plain; charset=utf-8")
                        return
                immutable = path.startswith("/_next/static/")
                cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
                self._send(status, target.read_bytes(), content_type(target), cache=cache, head=head)

            def _proxy(self, method: str, parts: list[str], query: str) -> None:
                body = b""
                if method == "POST":
                    try:
                        length = int(self.headers.get("Content-Length", "0") or 0)
                    except ValueError:
                        self._send_json({"ok": False, "error": "invalid Content-Length"}, 400)
                        return
                    body = self.rfile.read(min(max(length, 0), MAX_BODY))
                # Forward only what the API needs; never cookies or auth headers from the browser.
                headers = {name: value for name in FORWARDED_HEADERS if (value := self.headers.get(name))}
                target = backend_path(parts) + (f"?{query}" if query else "")
                connection = http.client.HTTPConnection(api_host, api_port, timeout=PROXY_TIMEOUT)
                try:
                    connection.request("GET" if method == "HEAD" else method, target, body=body or None, headers=headers)
                    response = connection.getresponse()
                    payload = response.read()
                    kind = response.getheader("Content-Type") or "application/json"
                    status = response.status
                except (OSError, http.client.HTTPException) as exc:
                    self._send_json(
                        {"ok": False, "error": f"Sheltie API unavailable at {api_base}", "detail": str(exc)},
                        503,
                    )
                    return
                finally:
                    connection.close()
                self._send(status, payload, kind, head=method == "HEAD")

            def _send_json(self, payload: dict[str, Any], status: int) -> None:
                self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

            def _send(self, status: int, body: bytes, kind: str, cache: str = "no-store", head: bool = False) -> None:
                encoding = None
                if (
                    len(body) > 1024
                    and kind.startswith(COMPRESSIBLE)
                    and "gzip" in (self.headers.get("Accept-Encoding") or "")
                ):
                    body, encoding = gzip.compress(body, compresslevel=6), "gzip"
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.send_header("X-Content-Type-Options", "nosniff")
                if kind.startswith(COMPRESSIBLE):
                    self.send_header("Vary", "Accept-Encoding")
                if encoding:
                    self.send_header("Content-Encoding", encoding)
                self.end_headers()
                if not head:
                    self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                logging.debug("web: " + format, *args)

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, name="web-server", daemon=True)
        self.thread.start()
        logging.info("Dashboard listening on %s:%s (files in %s)", self.host, self.port, self.root)

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
