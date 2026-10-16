import gzip
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from monitors.web import WebServer, backend_path, proxy_parts


class FakeApi(BaseHTTPRequestHandler):
    seen: list[tuple[str, str, dict[str, str], bytes]] = []

    def do_GET(self) -> None:
        self._answer()

    def do_POST(self) -> None:
        self._answer()

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        FakeApi.seen.append((self.command, self.path, dict(self.headers), body))
        payload = json.dumps({"ok": True, "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args) -> None:
        pass


class BackendPathTest(unittest.TestCase):
    def test_maps_like_the_old_next_route(self) -> None:
        self.assertEqual(backend_path([]), "/api/status")
        self.assertEqual(backend_path(["docker"]), "/api/docker")
        self.assertEqual(backend_path(["actions", "docker", "restart"]), "/api/actions/docker/restart")
        self.assertEqual(backend_path(["metrics"]), "/metrics")

    def test_only_proxy_prefixes_are_api_paths(self) -> None:
        self.assertEqual(proxy_parts("/api/sheltie"), [])
        self.assertEqual(proxy_parts("/api/sheltie/health"), ["health"])
        self.assertEqual(proxy_parts("/api/meerkat/docker"), ["docker"])
        self.assertIsNone(proxy_parts("/api/sheltiex/health"))
        self.assertIsNone(proxy_parts("/containers/"))


class WebServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / "web"
        (root / "containers").mkdir(parents=True)
        (root / "_next" / "static").mkdir(parents=True)
        (root / "index.html").write_text("<html>home</html>")
        (root / "404.html").write_text("<html>lost</html>")
        (root / "containers" / "index.html").write_text("<html>containers</html>")
        (root / "_next" / "static" / "app.js").write_text("console.log('x');" * 200)
        (Path(self.tmp.name) / "secret.txt").write_text("outside the web root")

        FakeApi.seen = []
        self.api = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=self.api.serve_forever, daemon=True).start()
        api_base = f"http://127.0.0.1:{self.api.server_address[1]}"

        with patch.dict(os.environ, {"SHELTIE_WEB_ROOT": str(root), "SHELTIE_API_BASE": api_base}, clear=True):
            self.server = WebServer({"web": {"host": "127.0.0.1", "port": 0}})
        self.server.start()
        assert self.server.server is not None
        self.port = self.server.server.server_address[1]

    def tearDown(self) -> None:
        self.server.stop()
        self.api.shutdown()
        self.tmp.cleanup()

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response, data

    def test_serves_pages_and_redirects_to_trailing_slash(self) -> None:
        response, body = self.request("GET", "/")
        self.assertEqual((response.status, body), (200, b"<html>home</html>"))
        self.assertEqual(response.getheader("Cache-Control"), "no-cache")

        response, _ = self.request("GET", "/containers?name=hearth")
        self.assertEqual(response.status, 308)
        self.assertEqual(response.getheader("Location"), "/containers/?name=hearth")

        response, body = self.request("GET", "/containers/")
        self.assertEqual((response.status, body), (200, b"<html>containers</html>"))

    def test_missing_page_gets_404_page(self) -> None:
        response, body = self.request("GET", "/nope/")
        self.assertEqual((response.status, body), (404, b"<html>lost</html>"))

    def test_never_serves_files_outside_the_root(self) -> None:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
            response, body = self.request("GET", path)
            self.assertNotIn(b"outside the web root", body, path)
            self.assertEqual(response.status, 404, path)

    def test_static_assets_are_immutable_and_gzipped(self) -> None:
        response, body = self.request("GET", "/_next/static/app.js", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "public, max-age=31536000, immutable")
        self.assertEqual(response.getheader("Content-Encoding"), "gzip")
        self.assertTrue(response.getheader("Content-Type").startswith("text/javascript"))
        self.assertEqual(gzip.decompress(body), b"console.log('x');" * 200)

    def test_proxies_get_with_query(self) -> None:
        response, body = self.request("GET", "/api/sheltie/docker?all=1")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body)["path"], "/api/docker?all=1")
        self.assertEqual(response.getheader("Cache-Control"), "no-store")

    def test_proxy_forwards_only_allowed_headers(self) -> None:
        payload = json.dumps({"container": "hearth"}).encode()
        response, _ = self.request(
            "POST",
            "/api/sheltie/actions/docker/restart",
            body=payload,
            headers={
                "Content-Type": "application/json",
                "X-Sheltie-Action-Token": "t0ken",
                "Cookie": "session=1",
                "Authorization": "Basic eA==",
            },
        )
        self.assertEqual(response.status, 200)
        method, path, headers, body = FakeApi.seen[-1]
        self.assertEqual((method, path, body), ("POST", "/api/actions/docker/restart", payload))
        self.assertEqual(headers.get("X-Sheltie-Action-Token"), "t0ken")
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("Authorization", headers)

    def test_legacy_proxy_path_still_works(self) -> None:
        _, body = self.request("GET", "/api/meerkat/health")
        self.assertEqual(json.loads(body)["path"], "/api/health")

    def test_api_down_gives_503(self) -> None:
        self.api.shutdown()
        self.api.server_close()
        response, body = self.request("GET", "/api/sheltie/status")
        self.assertEqual(response.status, 503)
        self.assertFalse(json.loads(body)["ok"])

    def test_post_to_a_page_is_refused(self) -> None:
        response, _ = self.request("POST", "/containers/", body=b"x")
        self.assertEqual(response.status, 405)


class WebServerWithoutFilesTest(unittest.TestCase):
    def test_does_not_start_without_a_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"SHELTIE_WEB_ROOT": tmp}, clear=True):
            server = WebServer({})
            server.start()
        self.assertIsNone(server.server)
        self.assertEqual((server.host, server.port), ("0.0.0.0", 8710))


if __name__ == "__main__":
    unittest.main()
