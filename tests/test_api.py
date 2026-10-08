import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from monitors import __version__
from monitors.actions import ActionService
from monitors.alerts import clear_silence, set_silence, silence_active
from monitors.api import GENERATED_TOKEN_KEY, LEGACY_ACTION_TOKEN_HEADER, ApiServer, metrics_payload, resolve_action_token
from monitors.autofix import USER_STOPPED_KEY
from monitors.status import StatusService
from monitors.telegram import TelegramNotifier
from monitors.config import ConfigError, validate_config


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True

    def snapshot(self):
        return dict(self.data)


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
        with patch.dict(os.environ, {"SHELTIE_ACTION_TOKEN": "from-env"}, clear=True):
            self.assertEqual(resolve_action_token({"actions": {"token": "from-config"}}, FakeState()), "from-env")

    def test_legacy_meerkat_env_var_still_works(self):
        with patch.dict(os.environ, {"MEERKAT_ACTION_TOKEN": "legacy"}, clear=True):
            self.assertEqual(resolve_action_token({}, FakeState()), "legacy")

    def test_new_env_var_wins_over_legacy(self):
        with patch.dict(os.environ, {"SHELTIE_ACTION_TOKEN": "new", "MEERKAT_ACTION_TOKEN": "legacy"}, clear=True):
            self.assertEqual(resolve_action_token({}, FakeState()), "new")


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

    def request(self, path, method="GET", token=None, header="X-Sheltie-Action-Token"):
        request = urllib.request.Request(f"{self.base}{path}", method=method, data=b"{}" if method == "POST" else None)
        if token:
            request.add_header(header, token)
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

    def test_actions_accept_legacy_token_header(self):
        token = self.server.action_token
        status, _body = self.request("/api/actions/clear-ram-cache", method="POST", token=token, header=LEGACY_ACTION_TOKEN_HEADER)

        self.assertEqual(status, 200)
        self.assertEqual(self.actions.cleared, 1)


class MetricsTests(unittest.TestCase):
    def test_emits_new_and_deprecated_metric_names(self):
        service = type(
            "Status",
            (),
            {
                "health": lambda self: {"cpu_percent": 10, "ram_percent": 20, "disk_percent": 30},
                "status": lambda self: {"internet_up": True, "active_alerts": []},
                "network": lambda self: {"interfaces": {}},
                "sites": lambda self: {"up": 1, "down": 0, "sites": [{"name": "sheltie_site", "up": True, "latency_ms": 12}]},
            },
        )()

        payload = metrics_payload(service)

        self.assertIn("sheltie_cpu_percent 10", payload)
        self.assertIn("meerkat_cpu_percent 10", payload)
        self.assertIn("# TYPE meerkat_sites_up gauge", payload)
        # Only the metric prefix is renamed, never label values.
        self.assertIn('meerkat_site_up{name="sheltie_site"} 1', payload)


class SilenceTests(unittest.TestCase):
    def test_timed_silence_expires(self):
        state = FakeState()
        with patch("monitors.alerts.time.time", return_value=1000.0):
            until = set_silence(state, 30)
            self.assertEqual(until, 1000.0 + 30 * 60)
            self.assertTrue(silence_active(state))
        with patch("monitors.alerts.time.time", return_value=1000.0 + 31 * 60):
            self.assertFalse(silence_active(state))
        self.assertFalse(state.get("alerts.silenced"))
        self.assertIsNone(state.get("alerts.silenced_until"))

    def test_silence_until_resumed(self):
        state = FakeState()
        set_silence(state, None)
        self.assertTrue(silence_active(state))
        clear_silence(state)
        self.assertFalse(silence_active(state))

    def test_action_service_validates_minutes(self):
        service = ActionService({"actions": {"enabled": True}}, FakeState(), None)

        self.assertFalse(service.silence_alerts("soon")["ok"])
        self.assertFalse(service.silence_alerts(-5)["ok"])
        result = service.silence_alerts(60)
        self.assertTrue(result["ok"])
        self.assertIsNotNone(result["silenced_until"])
        self.assertTrue(service.resume_alerts()["ok"])

    def test_notifier_reads_legacy_env_vars(self):
        with patch.dict(os.environ, {"MEERKAT_TELEGRAM_BOT_TOKEN": "t", "MEERKAT_TELEGRAM_CHAT_ID": "1"}, clear=True):
            notifier = TelegramNotifier({}, FakeState())
        self.assertTrue(notifier.enabled)

    def test_notifier_skips_messages_while_silenced(self):
        state = FakeState()
        set_silence(state, 10)
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}, clear=True):
            notifier = TelegramNotifier({}, state)
        with patch("monitors.telegram.requests.post") as post:
            notifier.send("hello")
            notifier.send("forced", force=True)
        self.assertEqual(post.call_count, 1)


class StatusPayloadTests(unittest.TestCase):
    def test_status_includes_product_fields(self):
        state = FakeState()
        history = type("History", (), {"recent": lambda self, limit: []})()
        notifier = type("Notifier", (), {"enabled": True})()
        service = StatusService({}, state, history, notifier)
        set_silence(state, 5)

        status = service.status()

        self.assertEqual(status["version"], __version__)
        self.assertTrue(status["telegram_enabled"])
        self.assertTrue(status["alerts_silenced"])
        self.assertIsNotNone(status["alerts_silenced_until"])
        self.assertIn("started_at", status)

    def test_docker_flags_blocked_stopped_and_tracked(self):
        state = FakeState()
        state.set(USER_STOPPED_KEY, ["db"])
        state.set("auto_heal.containers.active", ["web"])
        service = StatusService({"actions": {"blocked_containers": ["sheltie"]}}, state, None)
        containers = [
            type("C", (), {"name": name, "status": "running", "image": type("I", (), {"tags": ["x:1"]})()})()
            for name in ("sheltie", "db", "web")
        ]
        with patch("monitors.status.docker.from_env") as from_env:
            from_env.return_value.containers.list.return_value = containers
            payload = service.docker()

        flags = {c["name"]: (c["blocked"], c["user_stopped"], c["auto_heal_tracked"]) for c in payload["containers"]}
        self.assertEqual(flags["sheltie"], (True, False, False))
        self.assertEqual(flags["db"], (False, True, False))
        self.assertEqual(flags["web"], (False, False, True))


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
