import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from monitors.api import GENERATED_TOKEN_KEY, ApiServer, resolve_action_token
from monitors.config import ConfigError, validate_config


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

    health = network = docker = sites = status


class FakeActionService:
    def __init__(self) -> None:
        self.cleared = 0

    def clear_ram_cache(self):
        self.cleared += 1
        return {"ok": True, "message": "cleared"}


class ResolveActionTokenTests(unittest.TestCase):
    def test_generates_and_persists_token_when_none_configured(self):
        state = FakeState()
        with patch.dict(os.environ, {}, clear=True):
            first = resolve_action_token({}, state)
            second = resolve_action_token({}, state)

        self.assertTrue(first)
        self.assertEqual(first, second)
        self.assertEqual(state.get(GENERATED_TOKEN_KEY), first)

    def test_prefers_configured_token(self):
        with patch.dict(os.environ, {"MEERKAT_ACTION_TOKEN": "from-env"}, clear=True):
            self.assertEqual(resolve_action_token({"actions": {"token": "from-config"}}, FakeState()), "from-env")


class ApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actions = FakeActionService()
        config = {"api": {"host": "127.0.0.1", "port": 0}}
        with patch.dict(os.environ, {}, clear=True):
            self.server = ApiServer(config, FakeStatusService(), self.actions)
            self.server.start()
        host, port = self.server.server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.stop()
        self.server.server.server_close()

    def request(self, path, method="GET", token=None):
        request = urllib.request.Request(f"{self.base}{path}", method=method, data=b"{}" if method == "POST" else None)
        if token:
            request.add_header("X-Meerkat-Action-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_dashboard_pages_render(self):
        for path in ("/", "/monitoring", "/settings"):
            status, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertIn(b"<!doctype html>", body)

    def test_actions_rejected_without_token(self):
        status, body = self.request("/api/actions/clear-ram-cache", method="POST")

        self.assertEqual(status, 403)
        self.assertFalse(json.loads(body)["ok"])
        self.assertEqual(self.actions.cleared, 0)

    def test_actions_allowed_with_generated_token(self):
        status, _body = self.request("/api/actions/clear-ram-cache", method="POST", token=self.server.action_token)

        self.assertEqual(status, 200)
        self.assertEqual(self.actions.cleared, 1)


class ConfigValidationTests(unittest.TestCase):
    BASE = {
        "cpu": {"threshold": 90},
        "ram": {"threshold": 90},
        "disk": {"threshold": 90},
        "temperature": {"threshold": 80},
        "internet": {"hosts": ["1.1.1.1"]},
    }

    def test_network_interfaces_are_optional(self):
        validate_config(dict(self.BASE))

    def test_rejects_bad_interval(self):
        with self.assertRaises(ConfigError):
            validate_config({**self.BASE, "interval": 1})


if __name__ == "__main__":
    unittest.main()
