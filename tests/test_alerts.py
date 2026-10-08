import time
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from monitors.actions import ActionService
from monitors.alerts import AlertManager
from monitors.autofix import USER_STOPPED_KEY, AutoHealMonitor
from monitors.commands import TelegramCommandMonitor
from monitors.docker import DockerEventMonitor
from monitors.network import InterfaceStatus


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True


class FakeHistory:
    def __init__(self) -> None:
        self.alerts = []

    def record(self, alert):
        self.alerts.append(alert)


class FakeNotifier:
    def __init__(self) -> None:
        self.alerts = []

    def send_alert(self, alert, force=False):
        self.alerts.append((alert, force))


class FakeAutoHealAlerts:
    def __init__(self) -> None:
        self.events = []

    def event(self, **kwargs):
        self.events.append(kwargs)


class FakeAutoHealActions:
    def __init__(self) -> None:
        self.blocked_containers = {"labwarden"}
        self.started = []
        self.restarted_interfaces = []

    def start_container(self, name):
        self.started.append(name)
        return {"ok": True, "message": f"started {name}"}

    def restart_network_interface(self, interface):
        self.restarted_interfaces.append(interface)
        return {"ok": True, "message": f"restarted {interface}"}


@dataclass
class FakeContainer:
    name: str
    status: str


class AlertManagerTests(unittest.TestCase):
    def make_manager(self):
        state = FakeState()
        history = FakeHistory()
        notifier = FakeNotifier()
        manager = AlertManager({"alerting": {"duration": 0, "cooldown": 900}}, state, notifier, history)
        return manager, state, notifier, history

    def test_condition_alert_and_recovery(self):
        manager, _state, notifier, history = self.make_manager()

        manager.condition("cpu.high", "cpu", True, "warning", "CPU high", "bad", "ok")
        manager.condition("cpu.high", "cpu", False, "warning", "CPU high", "bad", "ok")

        self.assertEqual([entry[0].status for entry in notifier.alerts], ["active", "recovered"])
        self.assertEqual([alert.status for alert in history.alerts], ["active", "recovered"])

    def test_event_dedupe(self):
        manager, _state, notifier, history = self.make_manager()

        manager.event("docker.foo.start", "docker", "info", "started", "body", dedupe_id="same")
        manager.event("docker.foo.start", "docker", "info", "started", "body", dedupe_id="same")

        self.assertEqual(len(notifier.alerts), 1)
        self.assertEqual(len(history.alerts), 1)

    def test_force_event_reaches_notifier(self):
        manager, _state, notifier, _history = self.make_manager()

        manager.event("labwarden.boot", "labwarden", "info", "boot", "body", force=True)

        self.assertTrue(notifier.alerts[0][1])


class ActionServiceTests(unittest.TestCase):
    def test_blocks_labwarden_restart_by_default(self):
        service = ActionService({"actions": {"enabled": True}}, FakeState(), None)

        result = service.restart_container("labwarden")

        self.assertFalse(result["ok"])
        self.assertIn("blocked", result["error"])

    def test_blocks_legacy_meerkat_container_by_default(self):
        service = ActionService({"actions": {"enabled": True}}, FakeState(), None)

        result = service.restart_container("meerkat")

        self.assertFalse(result["ok"])
        self.assertIn("blocked", result["error"])


class AutoHealMonitorTests(unittest.TestCase):
    def make_monitor(self):
        state = FakeState()
        alerts = FakeAutoHealAlerts()
        actions = FakeAutoHealActions()
        config = {
            "network": {"ethernet": "eth0", "wifi": "wlan0"},
            "auto_heal": {"enabled": True, "interval": 300, "repair_cooldown": 0},
        }
        monitor = AutoHealMonitor(config, state, alerts, actions)
        return monitor, state, alerts, actions

    def test_tracks_running_containers_before_restarting_down_ones(self):
        monitor, state, alerts, actions = self.make_monitor()

        with patch("monitors.autofix.docker.from_env") as docker_from_env:
            docker_from_env.return_value.containers.list.return_value = [
                FakeContainer("web", "running"),
                FakeContainer("db", "exited"),
            ]
            monitor._heal_containers()
            docker_from_env.return_value.containers.list.return_value = [
                FakeContainer("web", "exited"),
                FakeContainer("db", "exited"),
            ]
            monitor._heal_containers()

        self.assertEqual(actions.started, ["web"])
        self.assertEqual(state.get("auto_heal.containers.active"), ["web"])
        self.assertEqual(alerts.events[0]["alert_id"], "auto_heal.container.web")

    def test_does_not_restart_blocked_container(self):
        monitor, state, _alerts, actions = self.make_monitor()
        state.set("auto_heal.containers.active", ["labwarden"])

        with patch("monitors.autofix.docker.from_env") as docker_from_env:
            docker_from_env.return_value.containers.list.return_value = [FakeContainer("labwarden", "exited")]
            monitor._heal_containers()

        self.assertEqual(actions.started, [])

    def test_restarts_previously_active_network_interface(self):
        monitor, state, _alerts, actions = self.make_monitor()

        with patch("monitors.autofix.get_interface_status") as interface_status:
            interface_status.side_effect = [
                InterfaceStatus("eth0", "up", True, True, True),
                InterfaceStatus("wlan0", "missing", False, False, False),
                InterfaceStatus("eth0", "up", True, False, False),
                InterfaceStatus("wlan0", "missing", False, False, False),
            ]
            monitor._heal_network()
            monitor._heal_network()

        self.assertEqual(actions.restarted_interfaces, ["eth0"])
        self.assertEqual(state.get("auto_heal.network.active"), ["eth0"])

    def test_does_not_bounce_unplugged_ethernet(self):
        monitor, state, alerts, actions = self.make_monitor()
        state.set("auto_heal.network.active", ["eth0"])

        with patch("monitors.autofix.get_interface_status") as interface_status:
            interface_status.side_effect = [
                InterfaceStatus("eth0", "down", False, False, False),
                InterfaceStatus("wlan0", "missing", False, False, False),
            ]
            monitor._heal_network()

        self.assertEqual(actions.restarted_interfaces, [])
        self.assertEqual(alerts.events, [])

    def test_does_not_restart_user_stopped_container(self):
        monitor, state, _alerts, actions = self.make_monitor()
        state.set("auto_heal.containers.active", ["web"])
        state.set(USER_STOPPED_KEY, ["web"])

        with patch("monitors.autofix.docker.from_env") as docker_from_env:
            docker_from_env.return_value.containers.list.return_value = [FakeContainer("web", "exited")]
            monitor._heal_containers()

        self.assertEqual(actions.started, [])

    def test_repair_messages_respect_silence(self):
        monitor, state, alerts, _actions = self.make_monitor()
        state.set("auto_heal.containers.active", ["web"])

        with patch("monitors.autofix.docker.from_env") as docker_from_env:
            docker_from_env.return_value.containers.list.return_value = [FakeContainer("web", "exited")]
            monitor._heal_containers()

        self.assertFalse(alerts.events[0].get("force", False))


class DockerEventTrackingTests(unittest.TestCase):
    @staticmethod
    def event(action, name="web"):
        return {"Action": action, "Actor": {"ID": "abc", "Attributes": {"name": name}}, "time": 0}

    def test_user_stop_is_tracked_and_cleared_on_start(self):
        state = FakeState()
        monitor = DockerEventMonitor(state, FakeAutoHealAlerts())

        for action in ("kill", "die", "stop"):
            monitor._handle_event(self.event(action))
        self.assertEqual(state.get(USER_STOPPED_KEY), ["web"])

        monitor._handle_event(self.event("start"))
        self.assertEqual(state.get(USER_STOPPED_KEY), [])

    def test_crash_is_not_treated_as_user_stop(self):
        state = FakeState()
        monitor = DockerEventMonitor(state, FakeAutoHealAlerts())

        monitor._handle_event(self.event("die"))

        self.assertIsNone(state.get(USER_STOPPED_KEY))


class FakeTelegramNotifier:
    enabled = True
    chat_id = "42"
    bot_token = "token"

    def __init__(self) -> None:
        self.sent = []

    def send(self, text, force=False):
        self.sent.append(text)


class FakeCommandActions:
    def __init__(self) -> None:
        self.restarted = []

    def restart_container(self, name):
        self.restarted.append(name)
        return {"ok": True, "message": f"Container restarted: {name}"}


class TelegramCommandTests(unittest.TestCase):
    def make_monitor(self):
        notifier = FakeTelegramNotifier()
        actions = FakeCommandActions()
        monitor = TelegramCommandMonitor({}, FakeState(), notifier, None, actions)
        return monitor, notifier, actions

    @staticmethod
    def update(text, age_seconds):
        return {"message": {"chat": {"id": 42}, "text": text, "date": int(time.time() - age_seconds)}}

    def test_runs_fresh_destructive_command(self):
        monitor, _notifier, actions = self.make_monitor()

        monitor._handle_update(self.update("/restart web", 5))

        self.assertEqual(actions.restarted, ["web"])

    def test_ignores_stale_destructive_command(self):
        monitor, notifier, actions = self.make_monitor()

        monitor._handle_update(self.update("/restart web", 3 * 3600))

        self.assertEqual(actions.restarted, [])
        self.assertEqual(len(notifier.sent), 1)
        self.assertIn("Ignored /restart", notifier.sent[0])

    def test_drops_stale_read_only_command_silently(self):
        monitor, notifier, _actions = self.make_monitor()

        monitor._handle_update(self.update("/status", 3 * 3600))

        self.assertEqual(notifier.sent, [])


if __name__ == "__main__":
    unittest.main()
