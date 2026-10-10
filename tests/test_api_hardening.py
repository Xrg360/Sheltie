import http.client
import json
import os
import unittest
from unittest.mock import patch

from monitors.api import ApiServer, dashboard_html, metrics_payload


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True


class FakeStatusService:
    def __init__(self) -> None:
        self.state = FakeState()

    def status(self):
        return {"ok": True}

    def health(self):
        return {"cpu_percent": 1, "ram_percent": 1, "disk_percent": 1}

    def docker(self):
        raise OSError("docker socket is gone")

    def network(self):
        return {"interfaces": {"ethernet": {"name": 'eth"0\nfake_metric 1', "up": True}}}

    def sites(self):
        return {"up": 1, "down": 0, "sites": [{"name": 'evil"}\nfake_metric 1', "up": True, "latency_ms": 5}]}



class FakeActionService:
    def add_site(self, site):
        if not isinstance(site, dict):
            raise AssertionError("handler must pass a dict")
        return {"ok": False, "error": "site name is required"}

    def restart_container(self, name):
        raise RuntimeError("docker exploded")


class ApiHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.server = ApiServer({"api": {"host": "127.0.0.1", "port": 0}}, FakeStatusService(), FakeActionService())
            self.server.start()
        self.host, self.port = self.server.server.server_address[:2]

    def tearDown(self) -> None:
        self.server.stop()
        self.server.server.server_close()

    def raw(self, method, path, body=b"", headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.putrequest(method, path)
        for key, value in (headers or {}).items():
            connection.putheader(key, value)
        connection.endheaders(body or None)
        response = connection.getresponse()
        result = response.status, response.getheader("Content-Type"), response.read()
        connection.close()
        return result

    def post(self, path, body):
        headers = {"Content-Length": str(len(body)), "X-Sheltie-Action-Token": self.server.action_token}
        return self.raw("POST", path, body, headers)

    def test_invalid_content_length_gets_400(self):
        status, _type, body = self.raw("POST", "/api/actions/sites/add", headers={"Content-Length": "lots"})
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["ok"])

    def test_non_object_json_body_is_treated_as_empty(self):
        status, _type, body = self.post("/api/actions/sites/add", b"[1, 2, 3]")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "site name is required")

    def test_action_exception_returns_json_500(self):
        with self.assertLogs(level="ERROR"):
            status, _type, body = self.post("/api/actions/docker/restart", b'{"container": "x"}')
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body)["error"], "internal error")

    def test_get_exception_returns_json_500(self):
        with self.assertLogs(level="ERROR"):
            status, content_type, body = self.raw("GET", "/api/docker")
        self.assertEqual(status, 500)
        self.assertEqual(content_type, "application/json")
        self.assertFalse(json.loads(body)["ok"])

    def test_metrics_with_query_string_is_plain_text(self):
        status, content_type, _body = self.raw("GET", "/metrics?format=prometheus")
        self.assertEqual(status, 200)
        self.assertTrue(content_type.startswith("text/plain"))

    def test_default_bind_is_localhost(self):
        with patch.dict(os.environ, {}, clear=True):
            server = ApiServer({}, FakeStatusService(), FakeActionService())
        self.assertEqual((server.host, server.port), ("127.0.0.1", 8711))


class MetricsEscapingTests(unittest.TestCase):
    def test_label_values_cannot_inject_lines(self):
        payload = metrics_payload(
            type(
                "Status",
                (),
                {
                    "health": lambda self: {"cpu_percent": 1, "ram_percent": 1, "disk_percent": 1},
                    "status": lambda self: {"internet_up": True, "active_alerts": []},
                    "network": FakeStatusService.network,
                    "sites": FakeStatusService.sites,
                },
            )()
        )
        for line in payload.splitlines():
            self.assertFalse(line.startswith("fake_metric"), line)
        self.assertIn('sheltie_site_up{name="evil\\"}\\nfake_metric 1"} 1', payload)


class LegacyDashboardTests(unittest.TestCase):
    def test_site_names_are_not_interpolated_into_javascript(self):
        html = dashboard_html("monitoring")
        self.assertNotIn("selectSite('", html)
        self.assertNotIn("togglePin('", html)
        self.assertIn("selectSite(this.dataset.name)", html)


if __name__ == "__main__":
    unittest.main()
